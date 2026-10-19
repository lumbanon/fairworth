"""Coverage-denominator tests with explicitly synthetic records."""
from copy import deepcopy
from datetime import date, datetime, UTC

import pytest

from app.models.security_registry import (SecurityInstrument, SecurityIssuer, SecurityListing,
                                          SecurityRegistryRefresh)
from app.registry.coverage_audit import financial_matrix, markdown_matrix, registry_counts
from app.schemas.coverage import CoverageStages


def bundle():
    parts = {name: {"status": "missing_evidence", "reason": "Not available in the synthetic sample.",
                    "reason_codes": ["missing_sample_evidence"]} for name in CoverageStages.model_fields}
    return {"data_mode": "synthetic", "as_of": "2026-10-19T00:00:00Z", "samples": [
        {"requested_symbol": "SYN", "data_mode": "synthetic", "coverage": {
            "identity": {"issuer_id": "issuer-syn", "instrument_id": "instrument-syn", "listing_id": "listing-syn",
                "cik": "0000000001", "security_form": "common_stock", "listing_status": "unknown"},
            "as_of": "2026-10-18T00:00:00Z", "methodology_version": "synthetic-test", "stages": parts}}]}


def test_matrix_preserves_not_assessed_counts_and_independent_denominators():
    report = financial_matrix(bundle())
    assert report["data_mode"] == "synthetic"
    assert report["sample_denominator"] == report["issuer_denominator"] == 1
    assert report["securities_with_statements"] == report["securities_with_contributing_models"] == 0
    assert report["samples"][0]["contributing_model_count"] is None
    rendered = markdown_matrix(report)
    assert "| Contributing model count |" in rendered
    assert "Not assessed" in rendered
    assert "synthetic" in rendered


def test_matrix_rejects_cross_mode_duplicate_and_unknown_identity_denominators():
    for mutation in ("mode", "duplicate", "missing_identity", "naive_date", "future_date"):
        data = bundle()
        if mutation == "mode":
            data["samples"][0]["data_mode"] = "retained_public"
        elif mutation == "duplicate":
            data["samples"].append(deepcopy(data["samples"][0]))
        elif mutation == "missing_identity":
            data["samples"][0]["coverage"]["identity"] = None
        elif mutation == "naive_date":
            data["as_of"] = "2026-10-19T00:00:00"
        else:
            data["samples"][0]["coverage"]["as_of"] = "2026-10-20T00:00:00Z"
        with pytest.raises(ValueError):
            financial_matrix(data)


def test_reference_only_sample_cannot_be_labeled_real_verified():
    data = bundle()
    data["data_mode"] = data["samples"][0]["data_mode"] = "real_verified"
    with pytest.raises(ValueError, match="source-backed"):
        financial_matrix(data)


def test_unresolved_registry_issuer_ids_do_not_inflate_verified_entity_count():
    data = bundle()
    data["samples"][0]["coverage"]["identity"]["cik"] = None
    report = financial_matrix(data)
    assert report["issuer_denominator"] == 0
    assert report["unresolved_issuer_listing_count"] == 1
    assert "Unresolved" in markdown_matrix(report)


@pytest.mark.parametrize("number", [True, -1, 12, 1.5])
def test_model_count_must_be_exact_engine_count(number):
    data = bundle()
    data["samples"][0]["coverage"]["stages"]["valuation"]["contributing_model_count"] = number
    with pytest.raises(ValueError, match="engine count"):
        financial_matrix(data)


def test_sql_registry_counts_do_not_promote_reference_stale_conflicting_or_future_rows(session_factory):
    with session_factory.begin() as session:
        issuer = SecurityIssuer(id="issuer-syn", source_key="synthetic:issuer", name="Synthetic issuer", business_category="reit")
        refresh = SecurityRegistryRefresh(id="refresh-syn", content_hash="a" * 64, source="synthetic",
            as_of=date(2026, 10, 18), retrieved_at=datetime(2026, 10, 19, tzinfo=UTC),
            complete_scope=False, provenance={}, records=[])
        instrument = SecurityInstrument(id="instrument-syn", source_key="synthetic:instrument", issuer=issuer,
            security_form="common_stock", instrument_type="common_stock")
        session.add_all([issuer, refresh, instrument])
        session.flush()
        for index, (status, observed, confidence, state) in enumerate([
            ("verified", "2026-10-18", "source_backed", "active"),
            ("reference_only", "2026-10-18", "unverified", "unknown"),
            ("conflicting", "2026-10-18", "source_backed", "unknown"),
            ("verified", "2026-10-01", "source_backed", "active"),
            ("verified", "2026-10-20", "source_backed", "active"),
            ("verified", "2026-10-18", "unverified", "active"),
        ]):
            session.add(SecurityListing(id=f"listing-{index}", source_key=f"synthetic:{index}", instrument=instrument,
                ticker=f"SYN{index}", name="Synthetic", normalized_name="SYNTHETIC", listing_status=state,
                identity_status="reference_only", as_of=date(2026, 10, 18), refresh_id=refresh.id,
                verification={"status": status, "observed_on": observed, "confidence": confidence}))
    report = registry_counts(session_factory, as_of=date(2026, 10, 19), data_mode="synthetic")
    assert report["listing_denominator"] == 6
    assert report["verified_active_observations"] == 2
    assert report["current_verified_active_observations"] == 1
    assert report["verified_identity_count"] == 0
    assert report["conflicting_listing_count"] == 1
    assert report["verified_active_security_form_counts"] == {"common_stock": 2}
    assert report["future_source_observation_count"] == 1
    assert "Not inferred" in report["financial_coverage"]
