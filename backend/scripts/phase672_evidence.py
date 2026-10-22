"""Read-only validation of the separately approved, local AAPL source receipt.

No requests, settings, credentials or database are used. The supplied receipt
must be checked against actual user consent by the caller; it grants no rights.
"""
from datetime import date, datetime
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re

from scripts.phase671_evidence import _clock, _json, _market_payload, _safe_metadata

CIK = "0000320193"
FMP = "https://financialmodelingprep.com/stable/"
SOURCES = {("fmp", "profile"): (FMP + "profile", {"symbol": "AAPL"}, 1_000_000),
    ("fmp", "quote"): (FMP + "quote", {"symbol": "AAPL"}, 1_000_000),
    ("fmp", "splits"): (FMP + "splits", {"symbol": "AAPL", "limit": 1000}, 1_000_000),
    ("fmp", "historical-price-eod/full"): (FMP + "historical-price-eod/full", {"symbol": "AAPL", "from": "2020-01-01"}, 5_000_000),
    ("sec", "submissions"): ("https://data.sec.gov/submissions/CIK0000320193.json", {}, 2_000_000),
    ("sec", "companyfacts"): ("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json", {}, 12_000_000)}
_ORDER = [*SOURCES, ("sec", "annual-primary")]
_TOP = {"schema_version", "authorization_question_id", "authorization", "maximum_requests", "maximum_bytes", "timeout_seconds",
        "retries", "redirects", "concurrency", "started_at", "requests", "complete", "selected_annual_filing", "finished_at", "actual_requests", "actual_bytes", "stopped_providers"}
_FIELDS = {"provider", "endpoint", "url", "parameters", "symbol", "cik", "byte_limit", "started_at", "status", "http_status", "file", "bytes", "sha256", "retrieved_at", "error_type"}


def _fail(reason):
    raise ValueError("Invalid local Phase 6.7.2 evidence: " + reason + ".")


def _day(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        _fail("invalid original source date")


def _annual_from_submissions(payload, audit_day):
    try:
        recent = payload["filings"]["recent"]
        fields = ("form", "accessionNumber", "filingDate", "reportDate", "primaryDocument")
        if not all(isinstance(recent[field], list) for field in fields):
            _fail("invalid submissions metadata")
        if len({len(recent[field]) for field in fields}) != 1:
            _fail("unaligned submissions columns")
        rows = [dict(zip(fields, values)) for values in zip(*(recent[field] for field in fields))]
    except (KeyError, TypeError):
        _fail("missing original submissions metadata")
    candidates = []
    for row in rows:
        if row["form"] not in {"10-K", "10-K/A"}:
            continue
        filed, period = _day(row["filingDate"]), _day(row["reportDate"])
        if not period <= filed <= audit_day:
            continue
        if (not re.fullmatch(r"\d{10}-\d{2}-\d{6}", row["accessionNumber"])
                or not re.fullmatch(r"[A-Za-z0-9_.-]{1,180}\.html?", row["primaryDocument"])):
            _fail("unsafe annual document identity")
        candidates.append(row)
    if not candidates:
        _fail("no eligible original annual metadata")
    newest = max((row["reportDate"], row["filingDate"]) for row in candidates)
    chosen = [row for row in candidates if (row["reportDate"], row["filingDate"]) == newest]
    if len({(row["accessionNumber"], row["primaryDocument"]) for row in chosen}) != 1:
        _fail("ambiguous latest annual metadata")
    return {key: chosen[0][key] for key in fields if key != "form"}


class _AnnualIdentity(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active, self.depth, self.facts = None, 0, {}

    def handle_starttag(self, tag, attrs):
        concept = dict(attrs).get("name", "")
        if tag == "ix:nonnumeric":
            if self.active:
                self.depth += 1
            elif concept in {"dei:EntityCentralIndexKey", "dei:DocumentPeriodEndDate"}:
                self.active, self.depth = (concept, []), 1

    def handle_data(self, data):
        if self.active:
            self.active[1].append(data)

    def handle_endtag(self, tag):
        if tag == "ix:nonnumeric" and self.active:
            self.depth -= 1
            if self.depth:
                return
            concept, parts = self.active
            self.facts.setdefault(concept, set()).add("".join(parts).strip())
            self.active = None


def _inline_periods(values):
    result = set()
    for value in values:
        value = " ".join(value.split())
        for pattern in ("%Y-%m-%d", "%B %d, %Y", "%B %d %Y"):
            try:
                result.add(datetime.strptime(value, pattern).date().isoformat())
                break
            except ValueError:
                continue
        else:
            _fail("unsupported original annual date transformation")
    return result


def load_aapl_manifest(path, *, audit_clock, authorization_receipt):
    """Return validated local ``inventory`` payloads plus export-safe metadata."""
    path = Path(path).resolve()
    if not path.is_file() or path.stat().st_size > 100_000:
        _fail("missing or oversized acquisition receipt")
    manifest = _json(path.read_bytes())
    if not isinstance(manifest, dict) or set(manifest) - _TOP:
        _fail("unsupported receipt metadata")
    _safe_metadata(manifest)
    if (manifest.get("schema_version") != "phase672-aapl-acquisition-1" or manifest.get("complete") is not True
            or not isinstance(authorization_receipt, str) or not re.fullmatch(r"call_[A-Za-z0-9_-]{8,100}", authorization_receipt)
            or manifest.get("authorization_question_id") != authorization_receipt or not manifest.get("authorization")):
        _fail("incomplete receipt or caller authorization mismatch")
    expected = {"maximum_requests": 7, "maximum_bytes": 30_000_000, "timeout_seconds": 30, "retries": 0, "redirects": False, "concurrency": 1}
    if any(manifest.get(key) != value for key, value in expected.items()):
        _fail("acquisition limits differ from approval")
    clock, began, finished = (_clock(value) for value in (audit_clock, manifest.get("started_at"), manifest.get("finished_at")))
    if not began <= finished <= clock:
        _fail("future or inverted acquisition clocks")
    requests = manifest.get("requests")
    if not isinstance(requests, list) or not 1 <= len(requests) <= 7:
        _fail("request budget exceeded")
    inventory, stopped, last_time, last_order, total, annual = [], set(), None, -1, 0, None
    for record in requests:
        if (not isinstance(record, dict) or set(record) - _FIELDS or record.get("symbol") != "AAPL" or record.get("cik") != CIK):
            _fail("unexpected request or security identity")
        key = record.get("provider"), record.get("endpoint")
        if key not in _ORDER or _ORDER.index(key) <= last_order or key[0] in stopped:
            _fail("unapproved request, repeat, order, or provider denial")
        last_order = _ORDER.index(key)
        if key == ("sec", "annual-primary"):
            if annual is None or manifest.get("selected_annual_filing") != annual:
                _fail("annual document lacks matching original submissions proof")
            url = f"https://www.sec.gov/Archives/edgar/data/320193/{annual['accessionNumber'].replace('-', '')}/{annual['primaryDocument']}"
            expected_source = url, {}, 8_000_000
        else:
            expected_source = SOURCES[key]
        if (record.get("url"), record.get("parameters"), record.get("byte_limit")) != expected_source:
            _fail("endpoint, original parameters, or response limit mismatch")
        start, end = _clock(record.get("started_at")), _clock(record.get("retrieved_at"))
        if not began <= start <= end <= finished or last_time and (start - last_time).total_seconds() < 1:
            _fail("invalid sequential source clocks")
        last_time = end
        size = record.get("bytes")
        if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= expected_source[2]:
            _fail("response exceeds its byte limit")
        total += size
        if total > 30_000_000 or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256", ""))):
            _fail("total transfer budget or source hash invalid")
        filename = record.get("file")
        if not isinstance(filename, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+\.raw", filename):
            _fail("unsafe local source filename")
        source = (path.parent / filename).resolve()
        try:
            source.relative_to(path.parent)
        except ValueError:
            _fail("source path escapes receipt directory")
        if not source.is_file() or source.stat().st_size != size:
            _fail("source byte count differs from receipt")
        content = source.read_bytes()
        if hashlib.sha256(content).hexdigest() != record["sha256"]:
            _fail("source hash differs from receipt")
        status, code = record.get("status"), record.get("http_status")
        if status not in {"received", "http_error", "provider_error", "invalid_json", "transport_error", "size_limit_exceeded"}:
            _fail("invalid acquisition outcome")
        if code is not None and (isinstance(code, bool) or not isinstance(code, int) or not 100 <= code <= 599):
            _fail("invalid original HTTP status")
        if (status in {"received", "provider_error", "invalid_json"} and code != 200
                or status == "http_error" and (not isinstance(code, int) or code == 200)):
            _fail("inconsistent provider outcome")
        payload, summary = None, {"status": "unavailable_provider_response"}
        if status == "received":
            if key == ("sec", "annual-primary"):
                try:
                    payload = content.decode("utf-8-sig")
                except UnicodeError:
                    _fail("annual document decoding failed")
                parser = _AnnualIdentity()
                parser.feed(payload)
                if (parser.facts.get("dei:EntityCentralIndexKey") != {CIK}
                        or _inline_periods(parser.facts.get("dei:DocumentPeriodEndDate", set())) != {annual["reportDate"]}):
                    _fail("annual source issuer or reporting period mismatch")
                summary = {"status": "validated_original_annual_identity", **annual}
            else:
                payload = _json(content)
                if key[0] == "fmp":
                    if key[1] == "profile" and (not isinstance(payload, list) or len(payload) != 1
                            or not isinstance(payload[0], dict)
                            or str(payload[0].get("cik", "")).zfill(10) != CIK):
                        _fail("profile original issuer identity unverified")
                    summary = {"status": "validated_raw_market_inventory", **_market_payload(payload, record, end)}
                else:
                    if not isinstance(payload, dict) or str(payload.get("cik", "")).zfill(10) != CIK:
                        _fail("SEC original issuer identity mismatch")
                    if key[1] == "submissions":
                        annual = _annual_from_submissions(payload, end.date())
                        summary = {"status": "validated_original_submissions", "selected_annual": annual}
                    elif not isinstance(payload.get("facts"), dict):
                        _fail("companyfacts original structure unavailable")
                    else:
                        summary = {"status": "validated_original_companyfacts", "cik": CIK}
        if code in {401, 402, 403, 429} or status in {"provider_error", "invalid_json", "transport_error", "size_limit_exceeded"}:
            stopped.add(key[0])
        inventory.append({**record, "payload": payload, "source_summary": summary})
    if (manifest.get("actual_requests") != len(requests) or manifest.get("actual_bytes") != total
            or manifest.get("stopped_providers") != sorted(stopped)):
        _fail("receipt totals or denial stops disagree")
    safe = {key: value for key, value in manifest.items() if key != "requests"}
    safe["requests"] = [{key: value for key, value in record.items() if key != "payload"} for record in inventory]
    return {"contract_version": "phase672-local-evidence-1", "inventory": inventory, "safe_metadata": safe,
            "authorization_verification": "caller_supplied_receipt_not_independent_consent",
            "actual_requests": len(requests), "actual_bytes": total,
            "limitations": ["Validated original source bytes do not establish eligible financial inputs, current listing, complete splits, or public display rights.",
                            "Raw payloads stay local; no HTTP or database import is performed."]}
