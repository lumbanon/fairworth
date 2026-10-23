"""Bind one retained MSFT listing/reference pair without changing the registry.

The package supports only an explicitly dated scenario. It is not a registry
refresh, a financial ownership reassignment, or current publication evidence.
"""
from datetime import UTC, datetime, time, timedelta
import hashlib
import json
from pathlib import Path

from app.registry.importers import sec_reference_records
from app.registry.listing_sources import SOURCES, exchange_mic, parse_nasdaq_directory
from app.registry.verification import sec_issuer_linkage
from app.repositories.financial_repository import content_hash
from app.services.financial_import_audit import _target, instant

VERSION = "phase68-archived-security-package-1"
SEC_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
CIK = "0000789019"
RECEIPT = "call_5bac25295829451a94f814a3c0674f98"


def _load_json(path, cap):
    file = Path(path).resolve()
    if not file.is_file() or not 0 < file.stat().st_size <= cap:
        raise ValueError("A bounded original archived security file is required.")
    content = file.read_bytes()
    return file, content, json.loads(content)


def _proof(source, observed, retrieved, url):
    anchor = datetime.combine(datetime.fromisoformat(observed).date(), time.min, tzinfo=UTC)
    return {"state": "verified", "source": source, "source_url": url, "observed_on": observed,
        "published_at": None, "source_timezone": None, "retrieved_at": retrieved,
        "policy_anchor_at": anchor.isoformat(), "expires_at": (anchor + timedelta(days=1)).isoformat(),
        "ttl_seconds": 86400, "reason": "Original archived observation; valid only at an explicitly selected evidence clock."}


def build_archived_security_package(connection, spec_path, *, as_of):
    """Reparse exact retained bytes, and bind their symbol/venue to stable IDs."""
    spec_file, spec_bytes, spec = _load_json(spec_path, 100_000)
    expected = {"version", "ticker", "instrument_id", "listing_id", "acquisition_manifest",
                "authorization_question_id", "sources"}
    if (set(spec) != expected or spec.get("version") != VERSION or spec.get("ticker") != "MSFT"
            or spec.get("authorization_question_id") != RECEIPT
            or set(spec.get("sources", {})) != {"nasdaqlisted", "company_tickers_exchange"}
            or not spec.get("instrument_id") or not spec.get("listing_id")):
        raise ValueError("Archived security scope is restricted to the exact retained MSFT listing and SEC reference pair.")
    target, _owners, _company_id = _target(connection, "MSFT", CIK, spec["instrument_id"], spec["listing_id"], issuer_owned=True)
    if target["exchange_mic"] != "XNAS":
        raise ValueError("The selected MSFT listing does not match the archived Nasdaq venue.")
    manifest_path, manifest_bytes, manifest = _load_json(spec["acquisition_manifest"], 1_000_000)
    if manifest.get("authorization_question_id") != RECEIPT or manifest.get("schema_version") != "phase671-acquisition-1":
        raise ValueError("The original archived acquisition receipt is not the reviewed retained receipt.")
    clock = instant(as_of)
    inventory, parsed = [], {}
    for kind, source_path in spec["sources"].items():
        path = Path(source_path).resolve()
        if path.parent != manifest_path.parent or not path.is_file() or not 0 < path.stat().st_size <= 5_000_000:
            raise ValueError("Archived directory source must be bounded and beside its original acquisition manifest.")
        content = path.read_bytes()
        records = [row for row in manifest.get("requests", []) if row.get("file") == path.name]
        source_url = SOURCES["nasdaqlisted"] if kind == "nasdaqlisted" else SEC_URL
        provider = "nasdaq" if kind == "nasdaqlisted" else "sec"
        if len(records) != 1:
            raise ValueError("Exactly one original archived acquisition record must identify each source.")
        record = records[0]
        if (record.get("provider") != provider or record.get("endpoint") != kind
                or record.get("url") != source_url or record.get("status") != "received"
                or record.get("http_status") != 200 or record.get("bytes") != len(content)
                or record.get("sha256") != hashlib.sha256(content).hexdigest()
                or instant(record.get("retrieved_at")) > clock):
            raise ValueError("Archived source identity, successful acquisition, exact hash, or original clock does not match.")
        metadata = {"kind": kind, "file": path.name, "source_url": source_url, "sha256": record["sha256"],
                    "bytes": len(content), "retrieved_at": instant(record["retrieved_at"]).isoformat()}
        inventory.append(metadata)
        if kind == "nasdaqlisted":
            bundle = parse_nasdaq_directory(content, kind, retrieved_at=metadata["retrieved_at"])
            selected = [row for row in bundle["records"] if row["ticker"] == "MSFT"]
            if (len(selected) != 1 or selected[0]["exchange_mic"] != "XNAS"
                    or selected[0]["security_form"] != "common_stock" or selected[0]["listing_status"] != "active"):
                raise ValueError("Archived Nasdaq evidence does not establish the exact active MSFT common-share listing.")
            parsed[kind] = (selected[0], bundle["provenance"])
        else:
            raw_reference = json.loads(content)
            references = [row for row in sec_reference_records(raw_reference) if row["ticker"] == "MSFT"]
            if (len(references) != 1 or references[0]["cik"] != CIK
                    or exchange_mic(references[0].get("exchange")) != "XNAS"):
                raise ValueError("Archived SEC evidence does not establish exact MSFT CIK and Nasdaq venue.")
            originals = ([dict(zip(raw_reference["fields"], values)) for values in raw_reference["data"]]
                         if isinstance(raw_reference.get("fields"), list) and isinstance(raw_reference.get("data"), list)
                         else [row for row in raw_reference.values() if isinstance(row, dict)])
            originals = [row for row in originals if row.get("ticker") == "MSFT"]
            if len(originals) != 1:
                raise ValueError("An exact original SEC reference row is required for archived provenance.")
            parsed[kind] = (references[0], metadata, originals[0])
    listing, meta = parsed["nasdaqlisted"]
    reference, sec, original_reference = parsed["company_tickers_exchange"]
    observed = instant(sec["retrieved_at"]).date().isoformat()
    linkage = sec_issuer_linkage(ticker="MSFT", venue="XNAS", cik=CIK, issuer_id=target["issuer_id"],
        observed_on=observed, registry_version=sec["sha256"], source="sec-edgar-reference", source_url=SEC_URL,
        record_hash=content_hash(reference), retrieved_at=sec["retrieved_at"])
    linkage.update(original_record=original_reference, original_record_hash=content_hash(original_reference))
    verification = {"status": "verified", "confidence": "source_backed", "source": meta["source"],
        "observed_on": meta["as_of"], "published_at": meta.get("published_at"), "source_timezone": meta.get("source_timezone"),
        "retrieved_at": meta["retrieved_at"], "record_hash": listing["source_record_hash"],
        "source_url": meta["source_url"], "parser_version": meta.get("version"), "conflicts": [],
        "warnings": listing.get("warnings", []), "latest_source_observation_count": 1, "issuer_linkage": linkage}
    verification["original_record"] = listing["original_record"]
    proofs = {"listing": _proof(meta["source"], meta["as_of"], meta["retrieved_at"], meta["source_url"]),
              "issuer_linkage": _proof(linkage["source"], observed, sec["retrieved_at"], SEC_URL)}
    proofs["listing"].update(published_at=meta.get("published_at"), source_timezone=meta.get("source_timezone"))
    package = {"version": VERSION, "identity": {"issuer_id": target["issuer_id"], "instrument_id": target["instrument_id"],
        "listing_id": target["listing_id"], "cik": CIK, "ticker": "MSFT", "exchange_mic": "XNAS",
        "security_form": "common_stock", "listing_status": "active"},
        "listing_verification": verification, "issuer_linkage": linkage, "proof_expiry": proofs,
        "source_inventory": sorted(inventory, key=lambda row: row["kind"]),
        "acquisition_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "spec_sha256": hashlib.sha256(spec_bytes).hexdigest(),
        "limitations": ["Archived source evidence is separate from the current installed registry and supports only an explicit dated scenario.",
                        "No current registry field, proof timestamp, share count, quote or financial input is refreshed."]}
    package["package_hash"] = content_hash(package)
    return {"spec_file": str(spec_file), "package": package}
