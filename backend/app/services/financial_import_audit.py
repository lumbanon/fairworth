"""Read-only plans for retained SEC evidence. There is deliberately no apply path.

Raw observation identities match the existing repository; different filings are
preserved as history, while conflicting values in an identical filing context
need review. A plan never refreshes source clocks or grants model eligibility.
"""
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path

from sqlalchemy import or_, select, text

from app.models import CacheEntry, Company, FinancialFact, FinancialSnapshot
from app.models.security_registry import SecurityInstrument, SecurityIssuer, SecurityListing
from app.providers.base import normalize_cik, validate_ticker
from app.repositories.financial_repository import content_hash
from app.services.normalization import NORMALIZATION_VERSION, extract_observations, normalize_company_facts


VERSION = "financial-import-dry-run-1"
MAX_SOURCE_BYTES = 12_000_000
MAX_OBSERVATIONS = 200_000
EXAMPLE_LIMIT = 20


def instant(value):
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Source and audit clocks require explicit timezones.")
    return result.astimezone(UTC)


@contextmanager
def read_only_connection(engine):
    """Enforce read-only access in PostgreSQL and disposable SQLite test DBs."""
    with engine.connect() as connection:
        dialect = connection.dialect.name
        if dialect == "postgresql":
            connection.execute(text("SET TRANSACTION READ ONLY"))
        elif dialect == "sqlite":
            previous_query_only = connection.exec_driver_sql("PRAGMA query_only").scalar()
            connection.exec_driver_sql("PRAGMA query_only = ON")
        else:
            raise ValueError("Dry runs require PostgreSQL or SQLite tests.")
        try:
            yield connection
        finally:
            connection.rollback()
            if dialect == "sqlite":
                connection.exec_driver_sql("PRAGMA query_only = ON" if previous_query_only else "PRAGMA query_only = OFF")
                connection.rollback()


def load_approved_sec_source(source_path, manifest_path):
    """Verify original acquired bytes against their retained acquisition record."""
    path, manifest_path = Path(source_path).resolve(), Path(manifest_path).resolve()
    if path.parent != manifest_path.parent or not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Source must be a bounded local file beside its acquisition manifest.")
    if manifest_path.stat().st_size > 1_000_000:
        raise ValueError("Acquisition manifest is unexpectedly large.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = manifest.get("attempts", manifest.get("requests", []))
    rows = [row for row in rows if isinstance(row, dict) and row.get("file") == path.name]
    if len(rows) != 1:
        raise ValueError("Exactly one original acquisition entry must identify this source.")
    row, data = rows[0], path.read_bytes()
    if (row.get("status") != "received" or row.get("http_status") != 200
            or row.get("sha256") != hashlib.sha256(data).hexdigest() or row.get("bytes") != len(data)):
        raise ValueError("Source bytes do not match a successful original acquisition.")
    raw = json.loads(data)
    cik = normalize_cik(raw.get("cik"))
    if normalize_cik(row.get("cik")) != cik or row.get("url") != f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json":
        raise ValueError("Source issuer or exact SEC endpoint does not match the acquisition.")
    retrieved = instant(row.get("retrieved_at"))
    return raw, {"mode": "previously_approved_local", "cik": cik, "source_url": row["url"],
                 "sha256": row["sha256"], "bytes": len(data), "retrieved_at": retrieved.isoformat(),
                 "canonical_payload_sha256": content_hash(raw), "manifest_file": manifest_path.name}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _value(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _observation_key(observation):
    # Keep the repository's immutable fingerprint: values and filing versions
    # participate, whereas normalized metric labels and retrieval do not.
    return content_hash({key: value for key, value in observation.items() if key not in {"metric", "retrieved_at"}})


def _context(observation, *, filing=True):
    fields = ("taxonomy", "concept", "unit", "start", "end")
    if filing:
        # Filing-context labels are not separate economic observations. Keep
        # fy/fp/frame in the immutable key, but never let a metadata relabeling
        # hide a changed amount in the exact same filing and financial period.
        fields += ("accn", "filed", "form")
    return tuple(str(observation.get(field) or "") for field in fields)


def _example(observation):
    return {key: observation.get(key) for key in ("taxonomy", "concept", "unit", "start", "end", "accn", "filed", "form", "value")}


def _target(connection, ticker, cik, instrument_id, listing_id):
    query = (select(SecurityListing.id.label("listing_id"), SecurityListing.ticker,
                    SecurityListing.instrument_id, SecurityInstrument.issuer_id, SecurityIssuer.cik,
                    SecurityListing.exchange_mic, SecurityListing.identity_status, SecurityListing.listing_status)
             .join(SecurityInstrument, SecurityListing.instrument_id == SecurityInstrument.id)
             .join(SecurityIssuer, SecurityInstrument.issuer_id == SecurityIssuer.id)
             .where(SecurityListing.ticker == ticker))
    if instrument_id:
        query = query.where(SecurityListing.instrument_id == instrument_id)
    if listing_id:
        query = query.where(SecurityListing.id == listing_id)
    rows = [dict(row) for row in connection.execute(query.limit(101)).mappings()]
    if len(rows) != 1:
        raise ValueError("An exact unique registered listing is required; select stable instrument/listing IDs when ambiguous.")
    target = rows[0]
    if normalize_cik(target["cik"]) != cik:
        raise ValueError("Original SEC evidence does not belong to the selected registered issuer.")
    owners = [dict(row) for row in connection.execute(select(Company.id, Company.ticker, Company.issuer_id, Company.cik)
              .where(or_(Company.ticker == ticker, Company.issuer_id == target["issuer_id"])).limit(1001)).mappings()]
    if len(owners) > 1000:
        raise ValueError("Ownership inventory exceeded its bounded scope.")
    selected = [row for row in owners if row["ticker"] == ticker and row["issuer_id"] == target["issuer_id"]]
    if len(selected) > 1 or any(normalize_cik(row["cik"]) != cik for row in selected):
        raise ValueError("Existing financial ownership conflicts with the exact registered issuer.")
    return target, owners, selected[0]["id"] if selected else None


def audit_financial_import(connection, raw, source, *, ticker, as_of, sec_cache_ttl_seconds,
                           instrument_id=None, listing_id=None):
    """Inventory exact potential writes using SELECT only; never call ingestion."""
    ticker, cik, clock = validate_ticker(ticker), normalize_cik(raw.get("cik")), instant(as_of)
    retrieved = instant(source.get("retrieved_at"))
    if source.get("cik") != cik or source.get("canonical_payload_sha256") != content_hash(raw) or retrieved > clock:
        raise ValueError("Audited original source identity, content and acquisition clock are required.")
    if not isinstance(sec_cache_ttl_seconds, int) or isinstance(sec_cache_ttl_seconds, bool) or sec_cache_ttl_seconds <= 0:
        raise ValueError("The existing configured SEC cache TTL must be explicit.")
    target, owners, company_id = _target(connection, ticker, cik, instrument_id, listing_id)
    observations = extract_observations(raw)
    if len(observations) > MAX_OBSERVATIONS:
        raise ValueError("Source observation budget exceeded.")
    valid = [row for row in observations if _finite(row.get("value"))]
    incoming = {_observation_key(row): row for row in valid}
    persisted = (list(connection.execute(select(FinancialFact.observation_key, FinancialFact.original_source,
                    FinancialFact.reported_value).where(FinancialFact.company_id == company_id)).mappings())
                 if company_id is not None else [])
    known = {row["observation_key"] for row in persisted}
    by_context, by_period = defaultdict(list), defaultdict(list)
    for row in persisted:
        record = row["original_source"]
        value = _value(record.get("value", record.get("val", row["reported_value"])))
        by_context[_context(record)].append(value)
        by_period[_context(record, filing=False)].append((value, str(record.get("filed") or "")))
    exact_duplicates = set(incoming) & known
    new = {key: row for key, row in incoming.items() if key not in known}
    conflicts, restatements = [], []
    incoming_context = defaultdict(set)
    for key, row in incoming.items():
        value, context = _value(row["value"]), _context(row)
        incoming_context[context].add(value)
        if any(other != value for other in by_context[context]):
            conflicts.append({"observation_key": key, **_example(row), "issue": "same_filing_context_different_value"})
        elif key in new and any(other != value for other, _filed in by_period[_context(row, filing=False)]):
            restatements.append({"observation_key": key, **_example(row),
                                 "issue": "different_filing_value_requires_normalization_precedence_review"})
    internal_conflicts = sum(len(values) > 1 for values in incoming_context.values())
    normalized = normalize_company_facts(raw, cik=cik)
    normalized_hash = content_hash(normalized)
    snapshots = (list(connection.execute(select(FinancialSnapshot.id, FinancialSnapshot.content_hash,
                    FinancialSnapshot.normalized_data).where(FinancialSnapshot.company_id == company_id)).mappings())
                 if company_id is not None else [])
    cache_rows = list(connection.execute(select(CacheEntry.key, CacheEntry.payload, CacheEntry.retrieved_at, CacheEntry.expires_at)
        .where(or_(CacheEntry.key == f"sec:facts:{cik}", CacheEntry.key.startswith(f"sec:financials:{cik}:")))).mappings())
    caches = []
    for row in cache_rows:
        caches.append({"key": row["key"], "canonical_payload_sha256": content_hash(row["payload"]),
                       "retrieved_at": str(row["retrieved_at"]), "expires_at": str(row["expires_at"]),
                       "same_raw_payload": row["key"] == f"sec:facts:{cik}" and content_hash(row["payload"]) == source["canonical_payload_sha256"]})
    scoped_conflicts = sum(period.get("financial_reconciliations", {}).get("debt", {}).get("status") == "conflict"
                           for kind in ("annual", "quarterly") for period in normalized.get(kind, []))
    dividends = [row for row in incoming.values() if row.get("taxonomy") == "us-gaap"
                 and row.get("concept") == "CommonStockDividendsPerShareDeclared" and row.get("unit") == "USD/shares"]
    dividends.sort(key=lambda row: (str(row.get("end") or ""), str(row.get("filed") or "")), reverse=True)
    snapshot_exists = any(row["content_hash"] == normalized_hash for row in snapshots)
    return {"audit_version": VERSION, "as_of": clock.isoformat(), "mode": "read_only_dry_run", "source": source,
        "identity": target, "existing_financial_owners": owners, "selected_company_id": company_id,
        "ownership_policy": "Exact issuer/instrument/listing scope; no CIK-only share-class copy or historical owner reassignment.",
        "facts": {"source_observations": len(observations), "finite_observations": len(valid),
                  "incoming_unique": len(incoming), "incoming_duplicate_observations": len(valid) - len(incoming),
                  "already_persisted": len(exact_duplicates), "existing_target_facts": len(persisted),
                  "new_observations": len(new), "same_filing_conflicts": len(conflicts),
                  "incoming_conflicting_contexts": internal_conflicts, "restatement_review_candidates": len(restatements),
                  "conflict_examples": conflicts[:EXAMPLE_LIMIT], "restatement_examples": restatements[:EXAMPLE_LIMIT]},
        "normalization": {"current_version": NORMALIZATION_VERSION, "proposed_snapshot_hash": normalized_hash,
                          "existing_snapshot_count": len(snapshots), "exact_snapshot_exists": snapshot_exists,
                          "existing_versions": dict(Counter(str(row["normalized_data"].get("normalization_version", "not_recorded")) for row in snapshots)),
                          "annual_periods": len(normalized.get("annual", [])), "quarterly_periods": len(normalized.get("quarterly", [])),
                          "debt_conflicted_periods": scoped_conflicts,
                          "restatement_policy": "Preserve immutable source versions; existing compatible filing-date precedence and conflict quarantine remain authoritative."},
        "cache_consequences": {"existing": caches, "configured_sec_ttl_seconds": sec_cache_ttl_seconds,
                               "source_maximum_cache_expiry": (retrieved + timedelta(seconds=sec_cache_ttl_seconds)).isoformat(),
                               "cache_expiry_basis": "Original acquisition plus the currently configured SEC cache maximum; this is not an asserted provider expiry or a newly written cache entry.",
                               "source_within_configured_cache_policy": clock < retrieved + timedelta(seconds=sec_cache_ttl_seconds),
                               "proposed_cache_writes": 0,
                               "policy": "No cache refresh or replacement is authorized; any later ingestion must preserve original acquisition/expiry and must not displace newer source evidence."},
        "display_only_candidates": {"declared_common_dividends_per_share": [_example(row) for row in dividends[:EXAMPLE_LIMIT]],
                                    "limitation": "Declared dividends are not paid dividends, sustainable forecasts, selected-class verification or an eligible DDM input."},
        "write_plan": {"executed_writes": 0, "apply_supported": False, "explicit_approval_required": True,
                       "potential_company_inserts": int(company_id is None), "potential_fact_inserts": len(new),
                       "potential_company_metadata_updates": int(company_id is not None),
                       "company_update_basis": "The standard ingestion path updates existing target company metadata and updated_at; exact non-null profile changes require review before any approved import.",
                       "potential_snapshot_inserts": int(not snapshot_exists), "fact_updates": 0, "fact_deletes": 0,
                       "scope_conflicts_require_review": bool(conflicts or internal_conflicts or scoped_conflicts),
                       "transaction_policy": "A separately authorized importer must revalidate ownership and hashes, commit atomically or roll back completely; this command cannot apply a plan."},
        "limitations": ["Dry-run financial availability does not establish currentness, share basis, listing/issuer freshness, quote compatibility or model eligibility.",
                        "Changed values across different filing contexts are review candidates, not an assertion of confirmed restatement.",
                        "Source hashes and provenance remain separate from normalized interpretation; no underlying financial records or caches are modified."]}
