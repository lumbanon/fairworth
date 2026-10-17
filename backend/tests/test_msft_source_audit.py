"""Real retained source evidence for dated shares and incomplete MSFT debt."""
import json
from pathlib import Path

import pytest

from app.services.automatic_inputs_service import latest_sec_shares
from app.services.normalization import extract_observations, normalize_company_facts
from app.valuation.automatic import prepare_automatic_inputs
from app.valuation.engine import calculate_valuation


FIXTURES = Path(__file__).parent / "fixtures" / "valuation"


def excerpt():
    return json.loads((FIXTURES / "msft_shares_debt_excerpts.json").read_text())


def test_msft_cover_period_end_and_weighted_shares_remain_distinct():
    source = excerpt()
    raw = source["companyfacts_excerpt"]
    cover = latest_sec_shares(raw, {"cik": "0000789019", "has_multiple_share_classes": False}, source["retrieved_at"])
    annual = normalize_company_facts(raw)["annual"][-1]
    assert cover["value"] == 7_425_545_491
    assert cover["observation_date"] == "2026-07-23"
    assert cover["filed"] == "2026-07-29"
    assert cover["scope_verified"] is True
    assert cover["provenance"][0]["accn"] == source["primary_filing_accession"]
    assert annual["end_date"] == "2026-06-30"
    assert annual["metrics"]["shares_outstanding"] == 7_427_000_000
    assert annual["metrics"]["weighted_average_basic_shares"] == 7_429_000_000
    assert annual["metrics"]["weighted_average_diluted_shares"] == 7_453_000_000
    assert "not a live current-day observation" in " ".join(cover["warnings"])


def test_msft_old_zero_borrowings_do_not_complete_fy2026_debt():
    source = excerpt()
    annual = normalize_company_facts(source["companyfacts_excerpt"])["annual"][-1]
    metrics = annual["metrics"]
    assert metrics["current_long_term_debt"] == 9_227_000_000
    assert metrics["long_term_debt"] == 31_067_000_000
    assert metrics["short_term_debt"] is None
    assert metrics["reported_total_debt"] is None
    assert metrics["total_debt"] is None
    inventory = source["raw_concept_inventory"]
    assert inventory["us-gaap:ShortTermBorrowings"]["latest_observation_date"] == "2018-06-30"
    assert inventory["us-gaap:CommercialPaper"]["latest_observation_date"] == "2025-06-30"
    assert inventory["us-gaap:DebtLongtermAndShorttermCombinedAmount"]["latest_observation_date"] == "2015-03-31"
    assert inventory["us-gaap:DebtCurrent"]["present_in_raw_companyfacts"] is False
    assert any(warning["code"] == "missing_debt_components" for warning in annual["warnings"])


def test_msft_gross_debt_and_leases_are_preserved_without_scope_substitution():
    source = excerpt()
    raw = source["companyfacts_excerpt"]
    observations = {row["concept"]: row for row in extract_observations(raw)}
    assert observations["LongTermDebt"]["value"] == 40_294_000_000
    assert (observations["LongTermDebtCurrent"]["value"]
            + observations["LongTermDebtNoncurrent"]["value"]) == observations["LongTermDebt"]["value"]
    assert observations["DebtInstrumentCarryingAmount"]["value"] == 46_136_000_000
    assert observations["FinanceLeaseLiability"]["value"] == 66_594_000_000
    assert observations["OperatingLeaseLiability"]["value"] == 21_925_000_000
    assert normalize_company_facts(raw)["annual"][-1]["metrics"]["total_debt"] is None


def test_msft_permitted_share_float_does_not_replace_dated_sec_basis_or_unlock_models():
    from test_automatic_evidence_fixture import examples

    source = excerpt()
    inputs, evidence = examples()["MSFT"]
    prepared = prepare_automatic_inputs(inputs, evidence)
    share_float = source["fmp_share_float_excerpt"]
    assert share_float["status_code"] == 200
    assert share_float["date"] == "2026-10-13 21:32:45"
    assert share_float["outstandingShares"] == 7_425_550_000
    assert share_float["source"] == source["primary_filing_url"]
    assert prepared["values"]["shares"] == 7_425_545_491
    assert prepared["basis"]["valuation_share_observation_date"] == "2026-07-23"
    assert prepared["values"]["debt"] is None
    valuation = calculate_valuation(prepared)
    base = valuation["scenarios"]["base"]
    assert base["summary"]["fair_value"] == pytest.approx(619.5604742486083)
    assert base["summary"]["effective_weights"] == {"pe": 1}
    assert base["summary"]["count"] == 1
    assert base["summary"]["classification"] == "policy_based"
