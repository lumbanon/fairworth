"""Dated native EPS numerator proofs; no inferred class or split compatibility."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.services.automatic_inputs_service import _native_eps_reconciliation, original_annual_periods
from app.services.normalization import normalize_company_facts
from app.valuation.inputs import build_valuation_inputs
from app.valuation.historical_multiples import _adjusted_eps


@pytest.fixture
def excerpts():
    fixture = json.loads((Path(__file__).parent / "fixtures/valuation/phase67_sec_financial_excerpts_2026_10_20.json").read_text())
    assert fixture["data_mode"] == "newly_approved_live"
    return {row["symbol"]: row for row in fixture["issuers"]}


def native(row):
    # Company classification is an explicit blocked test boundary. The source
    # excerpt does not establish selected-class, listing or split compatibility.
    company = {"ticker": row["symbol"], "cik": row["cik"], "has_multiple_share_classes": True,
               "share_class_basis_verified": False}
    normalized = normalize_company_facts(row["raw"], cik=row["cik"])
    return original_annual_periods(row["raw"], normalized, company, row["source"]["retrieved_at"]), company, normalized


@pytest.mark.parametrize("symbol,year,total,common,shares,eps", [
    ("ORCL", 2026, 17_087_000_000, 16_984_000_000, 2_914_000_000, 5.83),
    ("JPM", 2025, 57_048_000_000, 55_681_000_000, 2_781_500_000, 20.02),
])
def test_original_common_income_proves_eps_numerator_without_changing_consolidated_income(excerpts, symbol, year, total, common, shares, eps):
    original = deepcopy(excerpts[symbol])
    rows, company, normalized = native(excerpts[symbol])
    selected = next(row for row in rows if row["fiscal_year"] == year)
    proof = selected["native_eps_reconciliation"]
    assert proof["verified"] is selected["reported_common_eps_basis_verified"] is True
    assert proof["numerator_metric"] == "common_net_income_diluted"
    assert proof["numerator_value"] == common
    assert proof["implied_diluted_eps"] == pytest.approx(common / shares)
    assert proof["reported_diluted_eps"] == eps
    assert abs(total / shares - eps) > .02
    assert selected["metrics"]["net_income"] == total
    assert proof["source_identifiers"] == [selected["source_accession"]]
    assert all(record["accn"] == selected["source_accession"] and record["filed"] == selected["publication_date"]
               for record in proof["provenance"])
    inputs = build_valuation_inputs({"company": company}, normalized, excerpts[symbol]["source"]["retrieved_at"])
    assert inputs["values"]["net_income"] == total
    assert inputs["basis"]["income_earnings_basis_verified"] is False
    assert inputs["basis"]["share_basis_verified"] is False
    assert selected["eps_split_basis_verified"] is False
    assert selected["facts"]["diluted_eps"]["split_basis_verified"] is False
    assert excerpts[symbol] == original


def test_jpm_native_common_income_has_four_separate_source_proofs(excerpts):
    rows, _, _ = native(excerpts["JPM"])
    selected = [row for row in rows if row["fiscal_year"] in {2022, 2023, 2024, 2025}]
    assert len(selected) == 4
    assert all(row["reported_common_eps_basis_verified"] is True for row in selected)
    assert len({row["source_accession"] for row in selected}) == 4
    assert all(row["eps_split_basis_verified"] is False for row in selected)


@pytest.mark.parametrize("field,change", [
    ("common_net_income_diluted", {"unit": "EUR"}),
    ("common_net_income_diluted", {"start": "2026-03-01"}),
    ("common_net_income_diluted", {"end": "2026-04-30"}),
    ("common_net_income_diluted", {"accn": "0001193125-26-277522"}),
    ("common_net_income_diluted", {"filed": "2026-06-19"}),
    ("common_net_income_diluted", {"form": "10-K/A"}),
    ("common_net_income_diluted", {"fy": 2025}),
    ("common_net_income_diluted", {"fp": "Q4"}),
    ("common_net_income_diluted", {"metric": "net_income"}),
    ("common_net_income_diluted", {"concept": "NetIncomeLoss"}),
    ("common_net_income_diluted", {"taxonomy": "unreviewed-taxonomy"}),
    ("common_net_income_diluted", {"value": 17_087_000_000}),
    ("common_net_income_diluted", {"derivation": "net_income_less_unverified_preferred"}),
    ("weighted_average_diluted_shares", {"unit": "USD"}),
    ("diluted_eps", {"accn": "0001193125-26-277522"}),
])
def test_cross_period_filing_unit_or_metric_sources_do_not_verify_native_common_eps(excerpts, field, change):
    rows, _, _ = native(excerpts["ORCL"])
    selected = deepcopy(next(row for row in rows if row["fiscal_year"] == 2026))
    selected["facts"][field]["provenance"][0].update(change)
    assert _native_eps_reconciliation(selected)["verified"] is False


def test_an_explicit_unusable_common_numerator_cannot_fall_back_to_other_income(excerpts):
    rows, _, _ = native(excerpts["ORCL"])
    selected = deepcopy(next(row for row in rows if row["fiscal_year"] == 2026))
    selected["facts"]["common_net_income_diluted"]["provenance"][0]["unit"] = "EUR"
    # Even a coincidentally matching consolidated numerator does not repair the
    # explicit common-income source's incompatible unit.
    matching = selected["metrics"]["diluted_eps"] * selected["metrics"]["weighted_average_diluted_shares"]
    selected["facts"]["net_income"]["value"] = matching
    selected["facts"]["net_income"]["provenance"][0]["value"] = matching
    proof = _native_eps_reconciliation(selected)
    assert proof["numerator_metric"] == "common_net_income_diluted"
    assert proof["verified"] is False


@pytest.mark.parametrize("symbol", ["ORCL", "JPM"])
def test_reported_numerator_proof_does_not_supply_missing_class_or_split_evidence(excerpts, symbol):
    rows, _, _ = native(excerpts[symbol])
    selected = rows[-1]
    result, reason = _adjusted_eps(selected, {"date": "2026-10-20", "close": 1, "adjustment_basis": "unadjusted"},
                                   {"complete": False, "splits": []})
    assert result is None
    assert reason == "unverified_earnings_split_basis"


def test_original_consolidated_numerator_route_is_retained_when_no_common_fact_exists(excerpts):
    row = excerpts["MSFT"]
    normalized = normalize_company_facts(row["raw"], cik=row["cik"])
    # This uses Microsoft's separately retained single-class declaration; it is
    # a test condition, not a new assertion from the companyfacts excerpt.
    rows = original_annual_periods(row["raw"], normalized, {"cik": row["cik"], "has_multiple_share_classes": False}, row["source"]["retrieved_at"])
    selected = rows[-1]
    assert selected["native_eps_reconciliation"]["verified"] is True
    assert selected["native_eps_reconciliation"]["numerator_metric"] == "net_income"
    assert selected["reported_common_eps_basis_verified"] is False
    assert selected["eps_split_basis_verified"] is True
