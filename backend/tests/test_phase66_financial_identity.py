"""Deterministic synthetic ownership and capability tests; no market coverage claim."""
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, select, text

from app.core.exceptions import ApiError
from app.core.database import build_session_factory
from app.models import Company, FinancialFact, FinancialSnapshot, SecurityIssuer
from app.repositories.financial_repository import FinancialRepository
from app.services.coverage_service import PRIMARY_STAGES, identity_stages
from app.services.security_identity import applicability, cache_scope
from app.providers.sec_edgar import filing_regime
from app.services.normalization import normalize_company_facts
from app.valuation.inputs import build_valuation_inputs
from app.valuation.eligibility import eligibility
from test_phase65_analysis_identity import Registry, attach, synthetic_identity
from test_api import client


def issuer(factory, identifier, cik):
    with factory.begin() as session:
        session.add(SecurityIssuer(id=identifier, source_key="synthetic:" + identifier,
                                  cik=cik, name="Synthetic issuer", source_refs=[]))


def test_registered_symbol_reuse_preserves_each_company_and_original_history(session_factory):
    issuer(session_factory, "old-issuer", "0000000001")
    issuer(session_factory, "new-issuer", "0000000002")
    repo = FinancialRepository(session_factory)
    original = repo.save_company({"ticker": "REUSE", "name": "Old issuer", "cik": "1", "issuer_id": "old-issuer"})
    repo.save_financials(original, [{"concept": "Revenue", "unit": "USD", "value": 12, "accn": "synthetic-old"}], {"annual": []})
    replacement = repo.save_company({"ticker": "REUSE", "name": "New issuer", "cik": "2", "issuer_id": "new-issuer"})
    assert replacement != original
    with session_factory() as session:
        assert session.get(Company, original).issuer_id == "old-issuer"
        assert session.get(Company, replacement).issuer_id == "new-issuer"
        assert session.scalar(select(FinancialFact)).company_id == original
        assert session.scalar(select(FinancialSnapshot)).company_id == original
    with pytest.raises(ApiError, match="historical data"):
        repo.save_company({"ticker": "REUSE", "name": "Bare symbol", "cik": "2"})


@pytest.mark.parametrize("selected", ["unknown-issuer", "wrong-issuer"])
def test_unregistered_or_wrong_cik_issuer_cannot_own_financials(session_factory, selected):
    issuer(session_factory, "wrong-issuer", "0000000002")
    with pytest.raises(ApiError):
        FinancialRepository(session_factory).save_company({"ticker": "SYN", "name": "Synthetic", "cik": "1", "issuer_id": selected})
    with session_factory() as session:
        assert session.scalar(select(Company)) is None


def test_same_issuer_share_class_buckets_are_not_merged(session_factory):
    issuer(session_factory, "dual-class-issuer", "0000000001")
    repo = FinancialRepository(session_factory)
    first = repo.save_company({"ticker": "SYNA", "name": "Class A", "cik": "1", "issuer_id": "dual-class-issuer"})
    second = repo.save_company({"ticker": "SYNB", "name": "Class B", "cik": "1", "issuer_id": "dual-class-issuer"})
    assert first != second


def test_noncanonical_registry_cik_keeps_original_owner_and_company_bucket(session_factory):
    issuer(session_factory, "legacy-unpadded-issuer", "1")
    repo = FinancialRepository(session_factory)
    profile = {"ticker": "SYN", "name": "Synthetic legacy CIK", "cik": "0000000001"}
    first = repo.save_company(profile)
    assert repo.save_company(profile) == first
    assert repo.save_company({**profile, "issuer_id": "legacy-unpadded-issuer"}) == first
    with session_factory() as session:
        assert session.get(Company, first).issuer_id == "legacy-unpadded-issuer"
        assert len(session.scalars(select(SecurityIssuer)).all()) == 1
        assert len(session.scalars(select(Company)).all()) == 1


def test_semantically_duplicate_registry_ciks_cannot_choose_or_create_an_owner(session_factory):
    issuer(session_factory, "unpadded-issuer", "1")
    issuer(session_factory, "padded-issuer", "0000000001")
    repo = FinancialRepository(session_factory)
    for explicit in (None, "padded-issuer"):
        with pytest.raises(ApiError, match="Multiple registry issuers"):
            repo.save_company({"ticker": "SYN", "name": "Synthetic ambiguous CIK", "cik": "1", "issuer_id": explicit})
    with session_factory() as session:
        assert session.scalar(select(Company)) is None
        assert len(session.scalars(select(SecurityIssuer)).all()) == 2


@pytest.mark.parametrize("business,model,reason", [("bank", "fcff", "financial_institution_enterprise_framework"),
    ("insurance", "evEbitda", "financial_institution_enterprise_framework"),
    ("reit", "pe", "reit_gaap_earnings_not_cash_earnings")])
def test_security_form_does_not_erase_business_applicability(business, model, reason):
    company = synthetic_identity(security_form="common_stock", issuer_business_category=business)
    result = eligibility(model, {"company": company, "currency": "USD", "basis": {}},
                         {"is_bank": False, "is_reit": False, "share_basis_confirmed": True, "forward_eps": 10, "target_pe": 20})
    assert result["status"] == "ineligible"
    assert reason in result["reason_codes"]


def test_explicit_unknown_security_form_is_not_replaced_by_legacy_type():
    assert applicability(synthetic_identity(security_form="unknown", instrument_type="common_stock"))[0] == "instrument_classification_unverified"


@pytest.mark.parametrize("change", [{"security_form": "preferred"}, {"issuer_business_category": "bank"},
    {"listing_verification": {"status": "verified", "record_hash": "different-source"}}])
def test_scoped_caches_include_verification_form_and_business(change):
    base = synthetic_identity()
    assert cache_scope(base) != cache_scope({**base, **change})


def test_ten_capabilities_do_not_equate_listing_with_statement_or_share_coverage():
    company = synthetic_identity(security_form="common_stock", issuer_business_category="bank",
        listing_verification={"status": "verified", "observed_on": "2026-10-18", "retrieved_at": "2026-10-19T00:00:00Z"})
    result = identity_stages(company)
    assert len(PRIMARY_STAGES) == 10
    assert result["security_identity"]["status"] == result["active_listing"]["status"] == "available"
    assert result["classification"]["security_form"] == "common_stock"
    assert result["classification"]["issuer_business_category"] == "bank"
    assert result["share_basis"]["status"] == "missing_evidence"
    assert result["active_listing"]["source_observed_on"] == "2026-10-18"
    assert result["active_listing"]["source_retrieved_at"] == "2026-10-19T00:00:00Z"


@pytest.mark.parametrize("changes", [{"identity_status": "reference_only"}, {"security_form": "unknown"},
    {"cik": None}, {"issuer_id": None}, {"has_multiple_share_classes": True, "share_class_basis_verified": False}])
def test_legacy_share_flag_cannot_promote_unverified_selected_security(changes):
    company = synthetic_identity(**changes)
    result = identity_stages(company, {"basis": {"share_basis_verified": True}})
    assert result["share_basis"]["status"] == "missing_evidence"


def test_inactive_verified_security_can_retain_compatible_historical_share_basis():
    company = synthetic_identity(listing_status="inactive", has_multiple_share_classes=False)
    result = identity_stages(company, {"basis": {"share_basis_verified": True}})
    assert result["share_basis"]["status"] == "available"
    assert result["active_listing"]["status"] == "financially_inapplicable"


@pytest.mark.parametrize("status", ["reference_only", "conflicting"])
def test_flat_active_flag_cannot_override_listing_proof(status):
    company = synthetic_identity(listing_verification={"status": status})
    assert identity_stages(company)["active_listing"]["status"] != "available"
    assert applicability(company) is not None


def test_verified_listing_and_classification_do_not_require_financial_issuer_mapping():
    company = synthetic_identity(cik=None, issuer_id=None, identity_status="reference_only", security_form="etf",
                                 listing_verification={"status": "verified"})
    result = identity_stages(company)
    assert result["active_listing"]["status"] == result["classification"]["status"] == "available"
    assert result["classification"]["supported_operating_company_valuation"] is False
    assert result["security_identity"]["status"] == "missing_evidence"


def test_stale_listing_projection_blocks_current_valuation_but_preserves_dated_proof():
    company = synthetic_identity(registry_status="stale", listing_verification={"status": "verified", "observed_on": "2020-01-01"})
    assert applicability(company)[0] == "stale_listing_verification"
    assert identity_stages(company)["active_listing"]["reason_codes"] == ["stale_listing_verification"]
    assert applicability(synthetic_identity(registry_status="stale")) is None  # Historical injected legacy contract.


@pytest.mark.parametrize("changes", [{"registry_status": "partial"}, {"registry_status": "fresh", "listing_verification": {"status": "verified", "stale": True}}])
def test_missing_or_future_listing_clock_cannot_establish_current_valuation(changes):
    company = synthetic_identity(listing_verification={"status": "verified"}, **{key: value for key, value in changes.items() if key != "listing_verification"})
    company.update(changes)
    assert applicability(company)[0] == "stale_listing_verification"
    assert identity_stages(company)["active_listing"]["status"] == "missing_evidence"


@pytest.mark.parametrize("form", ["20-F", "40-F"])
def test_foreign_annual_forms_cannot_inherit_domestic_share_basis(raw_facts, form):
    for concept in raw_facts["facts"]["us-gaap"].values():
        for records in concept["units"].values():
            for record in records:
                record["form"] = form
    normalized = normalize_company_facts(raw_facts, cik="0000000001")
    result = build_valuation_inputs({"company": synthetic_identity(security_form="common_stock", has_multiple_share_classes=False)}, normalized)
    assert result["company"]["filing_regime"] == "foreign_private_issuer"
    assert result["basis"]["share_basis_verified"] is False
    assert result["values"]["shares"] is result["values"]["trailing_eps"] is None
    assert applicability(result["company"])[0] == "foreign_share_basis_unverified"


def test_unknown_business_category_does_not_treat_a_potential_reit_as_ordinary_pe():
    company = synthetic_identity(security_form="common_stock", issuer_business_category="unknown")
    result = eligibility("pe", {"company": company, "currency": "USD"},
                         {"forward_eps": 10, "target_pe": 20, "is_reit": False, "share_basis_confirmed": True})
    assert "business_classification_unavailable" in result["reason_codes"]
    assert result["status"] == "unavailable"


def test_filing_regime_uses_latest_annual_form_without_inventing_framework_or_currency():
    data = {"filings": {"recent": {"form": ["20-F", "10-K", "8-K"], "filingDate": ["2025-03-01", "2026-03-01", "2026-04-01"]}}}
    assert filing_regime(data) == "us_domestic_reporter"
    assert filing_regime({"filings": {"recent": {"form": ["6-K"], "filingDate": ["2026-03-01"]}}}) is None


def test_actual_api_serialization_preserves_public_listing_presentation(client):
    identity = attach(client, display_symbol="SYN.A", security_description="Synthetic common stock, Class A",
                      source_security_identifier="synthetic-directory:SYN.A", security_form="common_stock")
    class SearchRegistry(Registry):
        async def search(self, _query, _limit, _offset):
            return {"results": [identity], "status": "partial", "warnings": []}
    client.app.state.company_service.registry = SearchRegistry(identity)
    company = client.get("/api/stocks/SYN").json()["company"]
    search = client.get("/api/stocks/search?q=SYN").json()["results"][0]
    coverage = client.get("/api/stocks/SYN/coverage").json()["identity"]
    for field in ("display_symbol", "security_description", "source_security_identifier"):
        assert company[field] == search[field] == coverage[field] == identity[field]


def migration_config(connection):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def legacy_company(connection, cik="0000000001"):
    connection.execute(text("INSERT INTO companies(id,ticker,name,cik,updated_at) VALUES(51,'SYN','Synthetic legacy',:cik,'2026-10-18')"), {"cik": cik})
    connection.exec_driver_sql("INSERT INTO financial_snapshots(id,company_id,content_hash,snapshot_at,periods,normalized_data,warnings,source_references) VALUES(31,51,'synthetic-hash','2026-10-18','{}','{\"unchanged\":true}','[]','[]')")


def test_ownership_upgrade_and_rollback_preserve_legacy_ids_and_snapshots(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ownership.sqlite'}")
    with engine.begin() as connection:
        config = migration_config(connection)
        command.upgrade(config, "0003_listing_observations")
        legacy_company(connection)
        before = connection.execute(text("SELECT * FROM financial_snapshots")).all()
        command.upgrade(config, "head")
        owner = connection.execute(text("SELECT id,issuer_id FROM companies")).one()
        assert owner.id == 51 and owner.issuer_id
        assert connection.execute(text("SELECT * FROM financial_snapshots")).all() == before
        assert connection.execute(text("SELECT cik FROM security_issuers WHERE id=:id"), {"id": owner.issuer_id}).scalar_one() == "0000000001"
        command.check(config)
        command.downgrade(config, "0003_listing_observations")
        assert connection.execute(text("SELECT * FROM financial_snapshots")).all() == before
        assert connection.execute(text("SELECT id FROM companies")).scalar_one() == 51
    engine.dispose()


def test_migrated_unpadded_registry_owner_survives_later_legacy_profile_write(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'unpadded-owner.sqlite'}")
    with engine.begin() as connection:
        config = migration_config(connection)
        command.upgrade(config, "0003_listing_observations")
        legacy_company(connection)
        connection.execute(text("INSERT INTO security_issuers(id,source_key,cik,name,source_refs,business_category,classification_evidence,updated_at) VALUES('existing-unpadded','synthetic:unpadded','1','Synthetic existing','[]','unknown','{}','2026-10-18')"))
        command.upgrade(config, "head")
        before = connection.execute(text("SELECT * FROM financial_snapshots")).all()
    repo = FinancialRepository(build_session_factory(engine))
    assert repo.save_company({"ticker": "SYN", "name": "Synthetic legacy", "cik": "0000000001"}) == 51
    with engine.connect() as connection:
        assert connection.execute(text("SELECT issuer_id FROM companies WHERE id=51")).scalar_one() == "existing-unpadded"
        assert connection.execute(text("SELECT count(*) FROM companies")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM security_issuers")).scalar_one() == 1
        assert connection.execute(text("SELECT * FROM financial_snapshots")).all() == before
    engine.dispose()


@pytest.mark.parametrize("failure", ["invalid_cik", "ambiguous_cik"])
def test_ownership_mapping_failure_aborts_before_schema_or_history_changes(tmp_path, failure):
    engine = create_engine(f"sqlite:///{tmp_path / (failure + '.sqlite')}")
    with engine.begin() as connection:
        config = migration_config(connection)
        command.upgrade(config, "0003_listing_observations")
        legacy_company(connection, cik="invalid" if failure == "invalid_cik" else "0000000001")
        if failure == "ambiguous_cik":
            for index, cik in enumerate(("1", "0000000001")):
                connection.execute(text("INSERT INTO security_issuers(id,source_key,cik,name,source_refs,business_category,classification_evidence,updated_at) VALUES(:id,:key,:cik,'Synthetic','[]','unknown','{}','2026-10-18')"), {"id": "issuer-" + str(index), "key": "synthetic:" + str(index), "cik": cik})
        with pytest.raises(RuntimeError, match="migration aborted"):
            command.upgrade(config, "head")
        assert "issuer_id" not in {row["name"] for row in inspect(connection).get_columns("companies")}
        assert connection.execute(text("SELECT company_id FROM financial_snapshots")).scalar_one() == 51
    engine.dispose()


def test_ownership_downgrade_refuses_to_merge_reused_tickers(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'downgrade.sqlite'}")
    with engine.begin() as connection:
        config = migration_config(connection)
        command.upgrade(config, "0003_listing_observations")
        legacy_company(connection)
        command.upgrade(config, "head")
        connection.execute(text("INSERT INTO security_issuers(id,source_key,cik,name,source_refs,business_category,classification_evidence,updated_at) VALUES('second-issuer','synthetic:second','0000000002','Synthetic second','[]','unknown','{}','2026-10-18')"))
        connection.execute(text("INSERT INTO companies(id,ticker,name,cik,issuer_id,updated_at) VALUES(52,'SYN','Synthetic second','0000000002','second-issuer','2026-10-18')"))
        with pytest.raises(RuntimeError, match="reused tickers"):
            command.downgrade(config, "0003_listing_observations")
        assert connection.execute(text("SELECT count(*) FROM companies")).scalar_one() == 2
        assert "issuer_id" in {row["name"] for row in inspect(connection).get_columns("companies")}
        assert connection.execute(text("SELECT company_id FROM financial_snapshots")).scalar_one() == 51
    engine.dispose()


def test_populated_sqlite_foreign_key_cascade_cannot_erase_history_during_upgrade(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'foreign-keys.sqlite'}")
    with engine.connect() as connection:
        config = migration_config(connection)
        command.upgrade(config, "0003_listing_observations")
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        legacy_company(connection)
        connection.commit()
        with pytest.raises(RuntimeError, match="populated SQLite"):
            command.upgrade(config, "head")
        assert connection.execute(text("SELECT company_id FROM financial_snapshots")).scalar_one() == 51
        assert "issuer_id" not in {row["name"] for row in inspect(connection).get_columns("companies")}
        connection.rollback()
    engine.dispose()
