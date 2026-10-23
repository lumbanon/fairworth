"""Exact-source preview and explicitly confirmed, transactional SEC import.

This service never downloads data. Preview is SELECT-only. Apply checks the
frozen database baseline and original acquired bytes again inside one write
transaction; existing financial observations are never updated or deleted.
"""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP, localcontext
import hashlib
import math
from pathlib import Path

from fastapi.encoders import jsonable_encoder
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.core.database import as_utc, utcnow
from app.models import CacheEntry, Company, FinancialFact, FinancialImportBatch, FinancialSnapshot
from app.repositories.financial_repository import content_hash, insert_ignore, parse_date
from app.services.financial_import_audit import (
    _observation_key, _target, audit_financial_import, instant, load_approved_sec_source,
    read_only_connection,
)
from app.services.normalization import NORMALIZATION_VERSION, extract_observations, normalize_company_facts
from app.services.archived_security_import import build_archived_security_package


VERSION = "sec-financial-import-1"
TABLES = (Company.__table__, FinancialFact.__table__, FinancialSnapshot.__table__, CacheEntry.__table__)
MAX_SOURCES = 9


def _digest_manifest(manifest):
    return content_hash({key: value for key, value in manifest.items() if key != "preview_digest"})


def _baseline(connection):
    """All existing application rows participate, including unrelated issuers."""
    result = {}
    for table in TABLES:
        digest, count = hashlib.sha256(), 0
        statement = select(table).order_by(*table.primary_key.columns)
        for row in connection.execute(statement.execution_options(stream_results=True)).mappings():
            digest.update(content_hash(dict(row)).encode("ascii"))
            count += 1
        result[table.name] = {"rows": count, "sha256": digest.hexdigest()}
    # An empty audit table has the same baseline before and after its explicitly
    # approved migration, so preview itself never requires an application write.
    digest, count = hashlib.sha256(), 0
    if inspect(connection).has_table(FinancialImportBatch.__tablename__):
        for row in connection.execute(select(FinancialImportBatch.__table__).order_by(FinancialImportBatch.id)).mappings():
            digest.update(content_hash(dict(row)).encode("ascii"))
            count += 1
    result[FinancialImportBatch.__tablename__] = {"rows": count, "sha256": digest.hexdigest()}
    return result


def _load(spec):
    raw, source = load_approved_sec_source(spec["source"], spec["manifest"])
    return raw, source


def _inventory(connection, specs, as_of, ttl):
    reports, seen = [], set()
    for spec in specs:
        raw, source = _load(spec)
        report = audit_financial_import(connection, raw, source, ticker=spec["ticker"], as_of=as_of,
            sec_cache_ttl_seconds=ttl, instrument_id=spec.get("instrument_id"), listing_id=spec.get("listing_id"),
            issuer_owned=True)
        issuer = report["identity"]["issuer_id"]
        if issuer in seen:
            raise ValueError("One source per issuer is required; multiple securities cannot duplicate consolidated statements.")
        seen.add(issuer)
        report["source_files"] = {"source": str(Path(spec["source"]).resolve()),
                                  "manifest": str(Path(spec["manifest"]).resolve())}
        report["write_plan"]["potential_company_metadata_updates"] = 0
        report["write_plan"]["company_update_basis"] = "Existing owner metadata and ticker remain unchanged."
        report["write_plan"]["apply_supported"] = True
        source_cache_key = f"sec:import:facts:{source['cik']}:{source['sha256']}"
        raw_cache = connection.execute(select(CacheEntry.payload, CacheEntry.retrieved_at, CacheEntry.expires_at)
                                      .where(CacheEntry.key == source_cache_key)).mappings().first()
        if raw_cache and content_hash(raw_cache["payload"]) != source["canonical_payload_sha256"]:
            raise ValueError("An immutable import source cache conflicts with the exact original bytes.")
        install = raw_cache is None
        report["cache_consequences"]["proposed_cache_writes"] = int(install)
        report["cache_consequences"]["target_key"] = source_cache_key
        report["cache_consequences"]["policy"] = (
            "Append one immutable source-SHA cache entry at original acquisition/expiry; preserve every existing raw and "
            "normalized cache row. Serve the audited imported snapshot separately unless a newer source exists.")
        report["ownership_policy"] = "One unambiguous stable issuer owner, shared by selected securities; never reassign existing history."
        reports.append(report)
    return reports


def build_preview(engine, source_specs, *, as_of, sec_cache_ttl_seconds, archived_security_package=None):
    if not 1 <= len(source_specs) <= MAX_SOURCES:
        raise ValueError("A bounded preview requires one to nine issuer sources.")
    clock = instant(as_of)
    with read_only_connection(engine) as connection:
        # A consistent snapshot is necessary when facts and baseline are read
        # in multiple SELECTs. PostgreSQL's default READ COMMITTED is insufficient.
        if connection.dialect.name == "postgresql":
            connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        reports = _inventory(connection, source_specs, clock, sec_cache_ttl_seconds)
        archived = (build_archived_security_package(connection, archived_security_package, as_of=clock)
                    if archived_security_package else None)
        if archived and archived["package"]["identity"]["issuer_id"] not in {row["identity"]["issuer_id"] for row in reports}:
            raise ValueError("Archived selected-security evidence must belong to an issuer included in this exact financial import.")
        baseline = _baseline(connection)
        has_audit_table = inspect(connection).has_table(FinancialImportBatch.__tablename__)
    totals = {key: sum(row["facts"][key] for row in reports) for key in (
        "source_observations", "incoming_unique", "already_persisted", "new_observations",
        "same_filing_conflicts", "incoming_conflicting_contexts", "restatement_review_candidates")}
    totals.update(company_inserts=sum(row["write_plan"]["potential_company_inserts"] for row in reports),
                  snapshot_inserts=sum(row["write_plan"]["potential_snapshot_inserts"] for row in reports),
                  cache_writes=sum(row["cache_consequences"]["proposed_cache_writes"] for row in reports),
                  company_updates=0, fact_updates=0, fact_deletes=0, executed_writes=0)
    blocked = bool(totals["same_filing_conflicts"] or totals["incoming_conflicting_contexts"])
    preview = {"version": VERSION, "mode": "read_only_preview", "as_of": clock.isoformat(),
        "normalization_version": NORMALIZATION_VERSION, "sec_cache_ttl_seconds": sec_cache_ttl_seconds,
        "database_baseline": baseline, "sources": reports, "totals": totals,
        "archived_security": archived,
        "apply_blocked": blocked, "migration_required": not has_audit_table,
        "required_schema_revision": "0005_financial_import_batches",
        "policy": {"confirmation": "APPLY <preview_digest>", "transaction": "atomic; rollback every write on any mismatch",
            "restatements": "Append original filing observations; retain existing normalization precedence and conflict quarantine.",
            "caches": "Append immutable issuer/source-SHA entries at original retrieval/expiry. Preserve every existing cache row and interpretation version.",
            "approval": "Preview creation and acquisition receipts do not authorize application writes."}}
    preview["preview_digest"] = _digest_manifest(preview)
    return preview


def _fact_rows(raw, company_id, source):
    rows = {}
    for observation in extract_observations(raw):
        value = observation.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            continue
        key = _observation_key(observation)
        rows[key] = {"company_id": company_id, "observation_key": key,
            "concept": observation.get("concept", "unknown"), "normalized_metric": observation.get("metric"),
            "reported_value": value, "unit": observation.get("unit", "unknown"),
            "fiscal_year": observation.get("fy"), "fiscal_period": observation.get("fp"),
            "period_start": parse_date(observation.get("start")), "period_end": parse_date(observation.get("end")),
            "filing_date": parse_date(observation.get("filed")), "accession_number": observation.get("accn"),
            "form_type": observation.get("form"), "original_source": jsonable_encoder(observation),
            "retrieved_at": instant(source["retrieved_at"])}
    return list(rows.values())


def _count(session, model):
    from sqlalchemy import func
    return session.scalar(select(func.count()).select_from(model))


def verify_applied_preview(engine, preview, *, confirmation):
    """Verify an existing exact import receipt without invoking its write path.

    This is a read-only replay, not another import attempt. PostgreSQL enforces
    READ ONLY and a consistent snapshot; no explicit LOCK, insert or sequence
    operations are requested. Missing or changed persisted evidence fails closed.
    All original financial facts must retain their complete reviewed baseline,
    including historical labels. Whole-database preservation remains a separate
    audit: the preview describes the database *before* the import.
    """
    digest = preview.get("preview_digest")
    if (preview.get("version") != VERSION or not digest or digest != _digest_manifest(preview)
            or confirmation != f"VERIFY {digest}"):
        raise ValueError("Verification requires the exact intact preview and explicit VERIFY confirmation.")
    if preview.get("normalization_version") != NORMALIZATION_VERSION or preview.get("apply_blocked"):
        raise ValueError("Conflicting source facts or changed normalization require a new reviewed preview.")
    if not 1 <= len(preview.get("sources", [])) <= MAX_SOURCES:
        raise ValueError("A bounded verification requires one to nine issuer sources.")
    with read_only_connection(engine) as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        if not inspect(connection).has_table(FinancialImportBatch.__tablename__):
            raise ValueError("The reviewed import-batch migration is not installed.")
        with Session(bind=connection, autoflush=False) as session:
            prior = session.scalar(select(FinancialImportBatch).where(FinancialImportBatch.preview_digest == digest))
            if prior is None or prior.id != "sec-" + digest[:48]:
                raise ValueError("No exact committed import batch exists for this reviewed preview.")
            reports = preview["sources"]
            if prior.source_inventory != [row["source"] for row in reports]:
                raise ValueError("Committed source inventory differs from the exact reviewed preview.")
            # Apply's append-only invariant fingerprints every original fact,
            # including its historical normalization labels and retrieval clock.
            # Verify that same complete baseline before interpreting old labels:
            # they must not be relabeled by today's normalization policy.
            original_facts = preview["database_baseline"]["financial_facts"]
            preserved_fact_ids, original_digest = set(), hashlib.sha256()
            statement = (select(FinancialFact.__table__).order_by(FinancialFact.id)
                         .limit(original_facts["rows"]).execution_options(stream_results=True))
            for row in connection.execute(statement).mappings():
                preserved_fact_ids.add(row["id"])
                original_digest.update(content_hash(dict(row)).encode("ascii"))
            if (len(preserved_fact_ids) != original_facts["rows"]
                    or original_digest.hexdigest() != original_facts["sha256"]):
                raise ValueError("The complete original financial-fact baseline changed after the reviewed import.")
            archived = preview.get("archived_security")
            if archived and build_archived_security_package(connection, archived["spec_file"], as_of=preview["as_of"]) != archived:
                raise ValueError("Archived security source or stable identity changed since preview.")
            expected_imported, verified_facts, preserved_labels = [], 0, 0
            for report in reports:
                raw, source = _load(report["source_files"])
                if source != report["source"]:
                    raise ValueError("Original acquired source differs from the exact reviewed preview.")
                identity, _owners, company_id = _target(connection, report["identity"]["ticker"], source["cik"],
                    report["identity"]["instrument_id"], report["identity"]["listing_id"], issuer_owned=True)
                if identity != report["identity"] or company_id is None:
                    raise ValueError("Committed financial owner differs from the reviewed stable issuer identity.")
                if report["selected_company_id"] is not None and company_id != report["selected_company_id"]:
                    raise ValueError("The original reviewed financial owner was reassigned.")
                normalized = normalize_company_facts(raw, cik=source["cik"])
                snapshot_hash = content_hash(normalized)
                if snapshot_hash != report["normalization"]["proposed_snapshot_hash"]:
                    raise ValueError("Normalized interpretation differs from the reviewed immutable snapshot.")
                snapshot = session.scalar(select(FinancialSnapshot).where(FinancialSnapshot.company_id == company_id,
                    FinancialSnapshot.content_hash == snapshot_hash))
                if (snapshot is None or content_hash(snapshot.normalized_data) != snapshot_hash
                        or snapshot.warnings != normalized.get("warnings", [])
                        or snapshot.source_references != normalized.get("source_references", [])
                        or snapshot.periods != {kind: [period["end_date"] for period in normalized.get(kind, [])]
                                               for kind in ("annual", "quarterly")}):
                    raise ValueError("The committed normalized snapshot failed its exact immutable binding.")
                source_cache_key = report["cache_consequences"]["target_key"]
                cached = session.get(CacheEntry, source_cache_key)
                retrieved = instant(source["retrieved_at"])
                expiry = retrieved + timedelta(seconds=preview["sec_cache_ttl_seconds"])
                if (cached is None or cached.provider != "sec-edgar"
                        or content_hash(cached.payload) != source["canonical_payload_sha256"]
                        or as_utc(cached.retrieved_at) != retrieved or as_utc(cached.expires_at) != expiry
                        or content_hash(normalize_company_facts(cached.payload, cik=source["cik"])) != snapshot_hash):
                    raise ValueError("The committed original source failed its immutable hash or acquisition-clock binding.")
                incoming = {row["observation_key"]: row for row in _fact_rows(raw, company_id, source)}
                fields = ("concept", "unit", "fiscal_year", "fiscal_period", "period_start",
                          "period_end", "filing_date", "accession_number", "form_type")
                for fact in session.scalars(select(FinancialFact).where(FinancialFact.company_id == company_id)
                                            .execution_options(yield_per=500)):
                    expected = incoming.pop(fact.observation_key, None)
                    if expected is None:
                        continue
                    # Numeric(30, 10) is the existing database storage contract;
                    # the complete original JSON value remains exact and hashed.
                    with localcontext() as context:
                        context.prec = 40
                        stored_value = Decimal(str(expected["reported_value"])).quantize(Decimal("0.0000000001"),
                                                                                       rounding=ROUND_HALF_UP)
                    preserved = fact.id in preserved_fact_ids
                    if (_observation_key(fact.original_source) != fact.observation_key
                            or (not preserved and content_hash(fact.original_source) != content_hash(expected["original_source"]))
                            or fact.reported_value != stored_value
                            or any(getattr(fact, key) != expected[key] for key in fields)
                            or (not preserved and fact.normalized_metric != expected["normalized_metric"])):
                        raise ValueError("A committed financial observation differs from the exact original evidence.")
                    if preserved and (fact.normalized_metric != expected["normalized_metric"]
                            or fact.original_source.get("metric") != expected["original_source"].get("metric")):
                        preserved_labels += 1
                    verified_facts += 1
                if incoming:
                    raise ValueError("Committed financial observations are missing from the reviewed source.")
                expected_imported.append({"issuer_id": identity["issuer_id"], "company_id": company_id,
                    "snapshot_id": snapshot.id, "cik": source["cik"], "source_sha256": source["sha256"],
                    "source_cache_key": source_cache_key, "source_payload_hash": source["canonical_payload_sha256"],
                    "source_url": source["source_url"], "retrieved_at": source["retrieved_at"],
                    "expires_at": expiry.isoformat(), "normalization_version": NORMALIZATION_VERSION,
                    "snapshot_hash": snapshot_hash, "new_observations": report["facts"]["new_observations"],
                    "restatement_review_candidates": report["facts"]["restatement_review_candidates"]})
            expected_summary = {"version": VERSION, "imported": expected_imported,
                "row_changes": {"companies": preview["totals"]["company_inserts"],
                                "financial_facts": preview["totals"]["new_observations"],
                                "financial_snapshots": preview["totals"]["snapshot_inserts"]},
                "cache_writes": preview["totals"]["cache_writes"], "original_rows_preserved": True,
                "fact_updates": 0, "fact_deletes": 0, "model_eligibility_granted": False,
                "archived_security_proofs": ({archived["package"]["identity"]["listing_id"]: archived["package"]}
                                             if archived else {}),
                "normalization_version": NORMALIZATION_VERSION}
            if prior.summary != expected_summary:
                raise ValueError("Committed import receipt differs from the exact reviewed source and write plan.")
            return {"verification": {"mode": "read_only_applied_preview_verification", "executed_writes": 0,
                                     "verified_sources": len(reports), "verified_observations": verified_facts,
                                     "preserved_original_facts": len(preserved_fact_ids),
                                     "preserved_label_count": preserved_labels},
                    "receipt": {"batch_id": prior.id, "already_applied": True, **prior.summary}}


def apply_preview(engine, preview, *, confirmation, fault_hook=None):
    """Apply only a concrete reviewed preview; caller must obtain user consent.

    ``fault_hook`` is dependency injection for rollback/invariant tests; the CLI
    never accepts or enables it. No partial batch commits are possible.
    """
    digest = preview.get("preview_digest")
    if (preview.get("version") != VERSION or not digest or digest != _digest_manifest(preview)
            or confirmation != f"APPLY {digest}"):
        raise ValueError("Apply requires the exact intact preview and explicit operator confirmation.")
    if preview.get("normalization_version") != NORMALIZATION_VERSION or preview.get("apply_blocked"):
        raise ValueError("Conflicting source facts or changed normalization require a new reviewed preview.")
    if not inspect(engine).has_table(FinancialImportBatch.__tablename__):
        raise ValueError("The reviewed import-batch migration must be applied separately before import.")
    # Reopen every source before transaction and inside it. No cached manifest
    # can stand in for the original acquired source bytes.
    specs = [{**row["source_files"], "ticker": row["identity"]["ticker"],
              "instrument_id": row["identity"]["instrument_id"], "listing_id": row["identity"]["listing_id"]}
             for row in preview["sources"]]
    for spec, expected_source in zip(specs, preview["sources"], strict=True):
        _raw, verified_source = _load(spec)
        if verified_source != expected_source["source"]:
            raise ValueError("Original acquired source differs from the exact reviewed preview.")
    with engine.connect() as connection:
        if connection.dialect.name == "postgresql":
            connection = connection.execution_options(isolation_level="SERIALIZABLE")
        elif connection.dialect.name != "sqlite":
            raise ValueError("Imports support PostgreSQL and disposable SQLite tests only.")
        with connection.begin():
            if connection.dialect.name == "postgresql":
                # Bound lock waits and protect registry ownership plus all
                # baseline/write tables against concurrent silent reassignment.
                connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                connection.execute(text("LOCK TABLE security_issuers, security_instruments, security_listings IN SHARE MODE"))
                connection.execute(text("LOCK TABLE companies, financial_facts, financial_snapshots, cache_entries, financial_import_batches IN SHARE ROW EXCLUSIVE MODE"))
            session = Session(bind=connection, expire_on_commit=False)
            try:
                archived = preview.get("archived_security")
                if archived and build_archived_security_package(connection, archived["spec_file"], as_of=preview["as_of"]) != archived:
                    raise ValueError("Archived security source or stable identity changed since preview.")
                prior = session.scalar(select(FinancialImportBatch).where(FinancialImportBatch.preview_digest == digest))
                if prior:
                    return {"batch_id": prior.id, "already_applied": True, **prior.summary}
                if _baseline(connection) != preview["database_baseline"]:
                    raise ValueError("Database changed since preview; create and review a fresh preview.")
                reports = _inventory(connection, specs, preview["as_of"], preview["sec_cache_ttl_seconds"])
                if reports != preview["sources"]:
                    raise ValueError("Source, ownership, or interpretation changed since preview.")
                if archived and build_archived_security_package(connection, archived["spec_file"], as_of=preview["as_of"]) != archived:
                    raise ValueError("Archived security source or stable identity changed since preview.")
                before = {model.__tablename__: _count(session, model) for model in (Company, FinancialFact, FinancialSnapshot)}
                changed_cache_keys = {row["cache_consequences"]["target_key"] for row in reports
                                      if row["cache_consequences"]["proposed_cache_writes"]}
                old_caches = {row.key: content_hash({column.name: getattr(row, column.name)
                    for column in CacheEntry.__table__.columns}) for row in session.scalars(select(CacheEntry))
                    if row.key not in changed_cache_keys}
                imported, cache_writes = [], 0
                for spec, report in zip(specs, reports, strict=True):
                    raw, source = _load(spec)
                    if source != report["source"]:
                        raise ValueError("Original acquired source changed during apply; transaction rolled back.")
                    company_id = report["selected_company_id"]
                    if company_id is None:
                        company = Company(ticker=report["identity"]["ticker"], issuer_id=report["identity"]["issuer_id"],
                            cik=source["cik"], name=str(raw.get("entityName") or report["identity"]["ticker"])[:300],
                            exchange=report["identity"].get("exchange_mic"), updated_at=instant(source["retrieved_at"]))
                        session.add(company)
                        session.flush()
                        company_id = company.id
                    rows = _fact_rows(raw, company_id, source)
                    for offset in range(0, len(rows), 500):
                        insert_ignore(session, FinancialFact, rows[offset:offset + 500], ["company_id", "observation_key"])
                    normalized = normalize_company_facts(raw, cik=source["cik"])
                    snapshot_hash = content_hash(normalized)
                    if snapshot_hash != report["normalization"]["proposed_snapshot_hash"]:
                        raise ValueError("Normalized interpretation differs from the reviewed snapshot; transaction rolled back.")
                    insert_ignore(session, FinancialSnapshot, [{"company_id": company_id, "content_hash": snapshot_hash,
                        "snapshot_at": instant(source["retrieved_at"]),
                        "periods": {kind: [period["end_date"] for period in normalized.get(kind, [])] for kind in ("annual", "quarterly")},
                        "normalized_data": jsonable_encoder(normalized), "warnings": normalized.get("warnings", []),
                        "source_references": normalized.get("source_references", [])}], ["company_id", "content_hash"])
                    snapshot = session.scalar(select(FinancialSnapshot).where(FinancialSnapshot.company_id == company_id,
                        FinancialSnapshot.content_hash == snapshot_hash))
                    retrieved = instant(source["retrieved_at"])
                    expiry = retrieved + timedelta(seconds=preview["sec_cache_ttl_seconds"])
                    source_cache_key = report["cache_consequences"]["target_key"]
                    cached = session.get(CacheEntry, source_cache_key)
                    if cached is None:
                        session.add(CacheEntry(key=source_cache_key, payload=raw, retrieved_at=retrieved,
                            expires_at=expiry, provider="sec-edgar"))
                        cache_writes += 1
                    imported.append({"issuer_id": report["identity"]["issuer_id"], "company_id": company_id,
                        "snapshot_id": snapshot.id, "cik": source["cik"], "source_sha256": source["sha256"],
                        "source_cache_key": source_cache_key,
                        "source_payload_hash": source["canonical_payload_sha256"],
                        "source_url": source["source_url"], "retrieved_at": source["retrieved_at"],
                        "expires_at": expiry.isoformat(), "normalization_version": NORMALIZATION_VERSION,
                        "snapshot_hash": snapshot_hash, "new_observations": report["facts"]["new_observations"],
                        "restatement_review_candidates": report["facts"]["restatement_review_candidates"]})
                    if fault_hook:
                        fault_hook(session, report)
                session.flush()
                actual = {model.__tablename__: _count(session, model) - before[model.__tablename__]
                          for model in (Company, FinancialFact, FinancialSnapshot)}
                expected = {"companies": preview["totals"]["company_inserts"],
                            "financial_facts": preview["totals"]["new_observations"],
                            "financial_snapshots": preview["totals"]["snapshot_inserts"]}
                if actual != expected:
                    raise ValueError("Actual row changes differ from the reviewed preview; transaction rolled back.")
                current_caches = {row.key: content_hash({column.name: getattr(row, column.name)
                    for column in CacheEntry.__table__.columns}) for row in session.scalars(select(CacheEntry))
                    if row.key not in changed_cache_keys}
                if current_caches != old_caches or cache_writes != preview["totals"]["cache_writes"]:
                    raise ValueError("Unrelated cache data changed or planned cache counts differ; transaction rolled back.")
                for table in TABLES[:3]:
                    old_ids = select(table).order_by(*table.primary_key.columns)
                    # Existing rows must match the complete original baseline;
                    # newly inserted IDs are removed from this comparison.
                    original_count = preview["database_baseline"][table.name]["rows"]
                    digest_old = hashlib.sha256()
                    for row in connection.execute(old_ids.limit(original_count)).mappings():
                        digest_old.update(content_hash(dict(row)).encode("ascii"))
                    if digest_old.hexdigest() != preview["database_baseline"][table.name]["sha256"]:
                        raise ValueError("Existing financial rows changed; transaction rolled back.")
                batch_id = "sec-" + digest[:48]
                if archived and build_archived_security_package(connection, archived["spec_file"], as_of=preview["as_of"]) != archived:
                    raise ValueError("Archived security source changed during apply; transaction rolled back.")
                summary = {"version": VERSION, "imported": imported, "row_changes": actual,
                    "cache_writes": cache_writes, "original_rows_preserved": True,
                    "fact_updates": 0, "fact_deletes": 0, "model_eligibility_granted": False,
                    "archived_security_proofs": ({archived["package"]["identity"]["listing_id"]: archived["package"]}
                                                 if archived else {}),
                    "normalization_version": NORMALIZATION_VERSION}
                session.add(FinancialImportBatch(id=batch_id, preview_digest=digest,
                    source_inventory=[row["source"] for row in reports], summary=summary, applied_at=utcnow()))
                session.flush()
                return {"batch_id": batch_id, "already_applied": False, **summary}
            finally:
                session.close()
