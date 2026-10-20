"""Approved, dated public excerpts; routine tests never repeat acquisition."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import re

import pytest

from app.services.normalization import normalize_company_facts
from scripts.replay_financial_model_coverage import replay_approved_excerpts

PATH = Path(__file__).parent / "fixtures/valuation/phase67_sec_financial_excerpts_2026_10_20.json"


@pytest.fixture(scope="module")
def excerpts():
    return json.loads(PATH.read_text(encoding="utf-8"))


def test_approved_excerpt_limits_and_independent_source_clocks(excerpts):
    assert excerpts["data_mode"] == "newly_approved_live"
    assert len(excerpts["issuers"]) == 8
    assert len({row["cik"] for row in excerpts["issuers"]}) == 8
    limits = excerpts["acquisition"]
    assert limits["maximum_requests"] == 8 and limits["automatic_retries"] == limits["redirects"] == 0
    assert limits["received_bytes"] == 36_961_056
    assert sum(row["source"]["bytes"] for row in excerpts["issuers"]) == limits["received_bytes"]
    assert all(row["source"]["bytes"] <= 12_000_000 for row in excerpts["issuers"])
    assert PATH.stat().st_size < 500_000
    for row in excerpts["issuers"]:
        assert row["source"]["url"] == f"https://data.sec.gov/api/xbrl/companyfacts/CIK{row['cik']}.json"
        assert re.fullmatch(r"[0-9a-f]{64}", row["source"]["sha256"])
        assert str(row["raw"]["cik"]).zfill(10) == row["cik"]
        assert datetime.fromisoformat(row["source"]["retrieved_at"]) <= datetime.fromisoformat(excerpts["as_of"])
        assert row["selection"]["complete_provider_document"] is False


@pytest.mark.parametrize("symbol", ["MSFT", "NVDA", "ORCL", "JPM", "AMZN", "GOOGL", "O", "PGR"])
def test_each_approved_issuer_retains_annual_source_observations(excerpts, symbol):
    entry = next(row for row in excerpts["issuers"] if row["symbol"] == symbol)
    before = deepcopy(entry)
    normalized = normalize_company_facts(entry["raw"], cik=entry["cik"])
    assert entry == before
    assert len(normalized["annual"]) == 4
    latest = max(normalized["annual"], key=lambda row: row["end_date"])
    assert latest["fiscal_period"] == "FY"
    assert latest["metrics"]["net_income"] is not None
    assert latest["metrics"]["weighted_average_diluted_shares"] > 0
    for field in ("net_income", "diluted_eps", "weighted_average_diluted_shares"):
        assert latest["provenance"][field]
        assert all(source["accn"] and source["filed"] and source["concept"] and source["unit"]
                   and source["start"] == latest["start_date"] and source["end"] == latest["end_date"]
                   for source in latest["provenance"][field])


def test_new_financial_retrieval_never_refreshes_listing_class_quote_or_eligibility():
    report = replay_approved_excerpts()
    assert report["data_mode"] == "newly_approved_live"
    assert report["source_issuer_denominator"] == 8 and report["sample_denominator"] == 9
    assert {row["symbol"] for row in report["samples"]} == {"MSFT", "NVDA", "ORCL", "JPM", "AMZN", "GOOG", "GOOGL", "O", "PGR"}
    assert report["stages"]["financial_statements"] == {"numerator": 9, "denominator": 9}
    assert report["stages"]["verified_active_listing"]["numerator"] == 0
    assert report["stages"]["at_least_one_eligible_model"]["numerator"] == 0
    assert report["stages"]["published_fair_value"]["numerator"] == 0
    for row in report["samples"]:
        assert row["identity"]["identity_status"] == "reference_only"
        assert row["identity"]["listing_verification"]["observed_on"] == "2026-10-19"
        assert row["identity"]["listing_verification"]["freshness"] == "stale"
        assert row["fair_value"] is None
        assert len(row["models"]) == 11
        assert all(any(part["code"] == "security_identity_unverified" for part in model["blockers"]) for model in row["models"])
    alphabet = [row for row in report["samples"] if row["symbol"] in {"GOOG", "GOOGL"}]
    assert len({row["identity"]["listing_id"] for row in alphabet}) == 2
    assert len({row["identity"]["instrument_id"] for row in alphabet}) == 2
    assert len({row["identity"]["cik"] for row in alphabet}) == 1
