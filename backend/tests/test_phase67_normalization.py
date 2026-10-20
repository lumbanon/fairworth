"""Scope and period regressions; examples are explicitly synthetic unless dated.

No provider requests or inferred zero-valued financial inputs are used here.
"""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.services.normalization import (
    NORMALIZATION_VERSION,
    _compatible,
    extract_observations,
    normalize_company_facts,
)
from app.valuation.inputs import build_valuation_inputs, normalize_annual_period
from phase6_company_helpers import phase6_company_inputs, source_examples
from test_normalization import cash_flow_payload, observation, payload, period_by_fp


def sources(concept, records, unit="USD"):
    return extract_observations(payload({concept: (unit, records)}))


def test_diluted_common_numerator_is_not_differenced_across_dilution_periods():
    raw = cash_flow_payload()
    definition = deepcopy(raw["facts"]["us-gaap"]["NetCashProvidedByUsedInOperatingActivities"])
    raw["facts"]["us-gaap"]["NetIncomeLossAvailableToCommonStockholdersDiluted"] = definition
    result = normalize_company_facts(raw)
    assert result["annual"][0]["metrics"]["common_net_income_diluted"] == 550
    assert period_by_fp(result, "Q4")["metrics"]["common_net_income_diluted"] is None
    definition["units"]["USD"].append(observation(180, "2024-10-01", "2024-12-31"))
    reported = normalize_company_facts(raw)
    assert period_by_fp(reported, "Q4")["metrics"]["common_net_income_diluted"] == 180
    assert not any(source.get("derivation") for source in period_by_fp(reported, "Q4")["provenance"]["common_net_income_diluted"])


@pytest.mark.parametrize("incompatible", [
    observation(20, "2024-10-01"),
    observation(20, "2024-01-02"),
    observation(20, None),
    observation(20, "2023-01-01", "2023-12-31"),
])
def test_same_accession_cannot_override_exact_reporting_periods(incompatible):
    operating = sources("NetCashProvidedByUsedInOperatingActivities", [observation(100)])
    capex = sources("PaymentsToAcquirePropertyPlantAndEquipment", [incompatible])
    assert operating[0]["accn"] == capex[0]["accn"]
    assert not _compatible([operating, capex], fiscal_year=2024)


def test_equivalent_reported_and_ytd_derived_quarters_have_matching_period_support():
    derived = sources("NetCashProvidedByUsedInOperatingActivities", [
        observation(220, end="2024-06-30", fp="Q2", form="10-Q", filed="2024-08-01"),
        observation(100, end="2024-03-31", fp="Q2", form="10-Q", filed="2024-08-01"),
    ])
    derived[0]["coefficient"] = 1
    derived[1]["coefficient"] = -1
    direct = sources("PaymentsToAcquirePropertyPlantAndEquipment", [
        observation(25, "2024-04-01", "2024-06-30", fp="Q2", form="10-Q", filed="2024-08-01"),
    ])
    assert _compatible([derived, direct], fiscal_year=2024)
    direct[0]["start"] = "2024-04-02"
    assert not _compatible([derived, direct], fiscal_year=2024)


@pytest.mark.parametrize("coefficient", [None, True, float("inf"), {}, 2])
def test_invalid_signed_period_support_is_rejected(coefficient):
    left = sources("NetCashProvidedByUsedInOperatingActivities", [observation(100)])
    right = sources("PaymentsToAcquirePropertyPlantAndEquipment", [observation(20)])
    right[0]["coefficient"] = coefficient
    assert not _compatible([left, right], fiscal_year=2024)


def test_aligned_ytd_fcf_keeps_exact_signed_amounts_after_period_guard():
    second = period_by_fp(normalize_company_facts(cash_flow_payload()), "Q2")
    assert second["metrics"]["free_cash_flow"] == 95
    terms = {(row["concept"], row["start"], row["end"], row["coefficient"], row["value"])
             for row in second["provenance"]["free_cash_flow"]}
    assert sum(coefficient * value for _, _, _, coefficient, value in terms) == 95


@pytest.mark.parametrize("total,common,compatibility", [(50, 40, 50), (None, 40, 40), (0, 0, 0)])
def test_cash_dividend_scopes_remain_separate_without_changing_compatibility_amount(total, common, compatibility):
    facts = {"Revenues": ("USD", [observation(100)])}
    if total is not None:
        facts["PaymentsOfDividends"] = ("USD", [observation(total)])
    if common is not None:
        facts["PaymentsOfDividendsCommonStock"] = ("USD", [observation(common)])
    original = deepcopy(facts)
    annual = normalize_company_facts(payload(facts))["annual"][0]
    assert facts == original
    assert annual["metrics"]["dividends_paid"] == compatibility
    assert annual["metrics"]["total_dividends_paid"] == total
    assert annual["metrics"]["common_dividends_paid"] == common
    assert annual["provenance"]["common_dividends_paid"][0]["economic_scope"] == "common_only"
    assert all(row["economic_scope"] == ("common_only" if total is None else "total_cash_dividends")
               for row in annual["provenance"]["dividends_paid"])
    assert any(warning["code"] == "common_dividend_scope" for warning in annual["warnings"]) is (total is None)
    inputs = build_valuation_inputs({"ticker": "SYNTH", "has_multiple_share_classes": False}, {"annual": [annual], "currency": "USD"})
    assert inputs["values"]["dividend_per_share"] is None
    assert not inputs["basis"].get("stable_dividend_verified")


@pytest.mark.parametrize("concept,expected_scope", [
    ("PaymentsOfDividends", "total_cash_dividends"),
    ("PaymentsOfDividendsCommonStock", "common_only"),
])
def test_derived_quarter_dividends_preserve_original_economic_scope(concept, expected_scope):
    quarterly = normalize_company_facts(payload({concept: ("USD", [
        observation(10, end="2024-03-31", fp="Q1", form="10-Q", filed="2024-05-01", accn="0000000001-24-000001"),
        observation(25, end="2024-06-30", fp="Q2", form="10-Q", filed="2024-08-01", accn="0000000001-24-000002"),
    ])}))
    second = period_by_fp(quarterly, "Q2")
    assert second["metrics"]["dividends_paid"] == 15
    assert {row["economic_scope"] for row in second["provenance"]["dividends_paid"]} == {expected_scope}
    target = "common_dividends_paid" if expected_scope == "common_only" else "total_dividends_paid"
    assert second["metrics"][target] == 15


def test_ppe_only_depreciation_does_not_claim_company_wide_da_or_ebitda():
    raw = payload({
        "Revenues": ("USD", [observation(100)]),
        "OperatingIncomeLoss": ("USD", [observation(20)]),
        "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment": ("USD", [observation(5)]),
        "AmortizationOfIntangibleAssets": ("USD", [observation(2)]),
    })
    original = deepcopy(raw)
    normalized = normalize_company_facts(raw)
    annual = normalized["annual"][0]
    assert raw == original
    assert annual["metrics"]["depreciation_depletion_amortization_ppe"] == 5
    assert annual["metrics"]["intangible_amortization_expense"] == 2
    assert annual["metrics"]["depreciation_and_amortization"] is None
    assert any(warning["code"] == "ppe_depreciation_scope" for warning in annual["warnings"])
    inputs = build_valuation_inputs({"ticker": "SYNTH", "has_multiple_share_classes": False}, normalized)
    assert inputs["values"]["ebitda"] is None


@pytest.mark.parametrize("derived", [False, True])
def test_legacy_ppe_only_da_keeps_original_evidence_without_enabling_ebitda(derived):
    raw = payload({
        "Revenues": ("USD", [observation(100)]),
        "OperatingIncomeLoss": ("USD", [observation(20)]),
        "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment": ("USD", [observation(5)]),
    })
    normalized = normalize_company_facts(raw)
    annual = normalized["annual"][0]
    original_records = deepcopy(annual["provenance"]["depreciation_depletion_amortization_ppe"])
    annual["metrics"]["depreciation_and_amortization"] = 5
    annual["provenance"]["depreciation_and_amortization"] = deepcopy(original_records)
    if derived:
        annual["provenance"]["depreciation_and_amortization"][0].update(
            derivation="legacy_da_proxy", coefficient=1,
        )
    normalized["normalization_version"] = 4
    original = deepcopy(normalized)
    inputs = build_valuation_inputs({"ticker": "SYNTH", "has_multiple_share_classes": False}, normalized)
    fact = inputs["facts"]["depreciation_and_amortization"]
    assert normalized == original
    assert fact["value"] is None and fact["reported_value"] == 5
    assert fact["provenance"] == original["annual"][0]["provenance"]["depreciation_and_amortization"]
    assert fact["provenance"][0]["accn"] == original_records[0]["accn"]
    assert any(warning["code"] == "incomplete_depreciation_amortization_scope" for warning in fact["warnings"])
    assert inputs["values"]["ebitda"] is None


def test_reported_diluted_common_income_is_distinct_from_parent_income_and_fcfe_basis():
    normalized = normalize_company_facts(payload({
        "NetIncomeLoss": ("USD", [observation(200)]),
        "NetIncomeLossAvailableToCommonStockholdersDiluted": ("USD", [observation(150)]),
        "EarningsPerShareDiluted": ("USD/shares", [observation(15)]),
        "WeightedAverageNumberOfDilutedSharesOutstanding": ("shares", [observation(10)]),
    }))
    period = normalized["annual"][0]
    assert period["metrics"]["net_income"] == 200
    assert period["metrics"]["common_net_income_diluted"] == 150
    common = period["provenance"]["common_net_income_diluted"][0]
    assert common["concept"] == "NetIncomeLossAvailableToCommonStockholdersDiluted"
    assert common["economic_scope"] == "common_diluted_eps_numerator"
    assert common["start"] == period["start_date"] and common["end"] == period["end_date"]
    inputs = build_valuation_inputs({"ticker": "SYNTH", "has_multiple_share_classes": False}, normalized)
    assert inputs["facts"]["common_net_income_diluted"]["value"] == 150
    assert inputs["facts"]["common_net_income_diluted"]["provenance"][0] == common
    assert inputs["values"]["net_income"] == 200
    # FCFE still consumes the parent-income value. A different common EPS
    # numerator cannot certify that value's common-equity earnings scope.
    assert not inputs["basis"]["income_earnings_basis_verified"]


@pytest.mark.parametrize("common_income", [0, -10, 150])
def test_common_income_never_fills_missing_parent_income(common_income):
    normalized = normalize_company_facts(payload({
        "Revenues": ("USD", [observation(100)]),
        "NetIncomeLossAvailableToCommonStockholdersDiluted": ("USD", [observation(common_income)]),
    }))
    period = normalized["annual"][0]
    assert period["metrics"]["common_net_income_diluted"] == common_income
    assert period["metrics"]["net_income"] is None
    assert "net_income" not in period["provenance"]


@pytest.mark.parametrize("unit,record", [
    ("EUR", observation(150)),
    ("USD", observation(150, None)),
    ("USD", observation(150, "2024-10-01")),
    ("USD", observation(150, accn=None)),
    ("USD", observation(None)),
    ("USD", observation(float("inf"))),
])
def test_diluted_common_income_requires_exact_annual_currency_period_and_source(unit, record):
    normalized = normalize_company_facts(payload({
        "NetIncomeLoss": ("USD", [observation(200)]),
        "NetIncomeLossAvailableToCommonStockholdersDiluted": (unit, [record]),
    }))
    period = normalized["annual"][0]
    assert period["metrics"]["net_income"] == 200
    assert period["metrics"]["common_net_income_diluted"] is None
    assert "common_net_income_diluted" not in period["provenance"]


def test_common_income_restatements_do_not_rewrite_parent_income():
    raw = payload({
        "NetIncomeLoss": ("USD", [observation(200)]),
        "NetIncomeLossAvailableToCommonStockholdersDiluted": ("USD", [
            observation(150),
            observation(160, form="10-K/A", filed="2025-03-01", accn="0000000001-25-000002"),
        ]),
    })
    period = normalize_company_facts(raw)["annual"][0]
    assert period["metrics"]["net_income"] == 200
    assert period["metrics"]["common_net_income_diluted"] == 160
    assert period["provenance"]["common_net_income_diluted"][0]["accn"] == "0000000001-25-000002"
    assert any(warning["field"] == "common_net_income_diluted" and warning["code"] == "restated_fact"
               for warning in period["warnings"])


@pytest.mark.parametrize("ticker,parent_income,common_income,expected_end,accession,filed", [
    ("ORCL", 17_087_000_000, 16_984_000_000, "2026-05-31", "0001193125-26-277521", "2026-06-22"),
    ("JPM", 57_048_000_000, 55_681_000_000, "2025-12-31", "0001628280-26-008131", "2026-02-13"),
])
def test_approved_dated_common_income_retains_exact_separate_scope_and_original_source(
        ticker, parent_income, common_income, expected_end, accession, filed):
    fixture = json.loads((Path(__file__).parent / "fixtures" / "valuation" /
                          "phase67_sec_financial_excerpts_2026_10_20.json").read_text(encoding="utf-8"))
    assert fixture["data_mode"] == "newly_approved_live"
    source = next(row for row in fixture["issuers"] if row["symbol"] == ticker)
    normalized = normalize_company_facts(source["raw"], cik=source["cik"])
    period = max(normalized["annual"], key=lambda row: row["end_date"])
    assert period["end_date"] == expected_end
    assert period["metrics"]["net_income"] == parent_income
    assert period["metrics"]["common_net_income_diluted"] == common_income
    records = period["provenance"]["common_net_income_diluted"]
    native = [record for record in records if record["accn"] == accession]
    assert native and all(record["filed"] == filed for record in native)
    assert all(record["source"] == "sec" and record["taxonomy"] == "us-gaap"
               and record["concept"] == "NetIncomeLossAvailableToCommonStockholdersDiluted"
               and record["unit"] == "USD" and record["value"] == common_income
               and record["start"] == period["start_date"] and record["end"] == expected_end
               and record["economic_scope"] == "common_diluted_eps_numerator" for record in records)
    canonical = normalize_annual_period(period, "USD", source["source"]["retrieved_at"])
    assert canonical["facts"]["net_income"]["value"] == parent_income
    common_fact = canonical["facts"]["common_net_income_diluted"]
    assert common_fact["value"] == common_fact["reported_value"] == common_income
    assert common_fact["provenance"] == records
    assert not common_fact["warnings"]
    shares, eps = (period["metrics"][key] for key in ("weighted_average_diluted_shares", "diluted_eps"))
    assert abs(common_income / shares - eps) <= .02
    assert abs(parent_income / shares - eps) > .02


@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "NVDA", "ORCL"])
def test_retained_financial_periods_and_all_existing_nonnull_values_are_preserved(ticker):
    statements, _, _ = source_examples()
    original = max(statements[ticker]["normalized"]["annual"], key=lambda row: row["end_date"])
    prepared, _, audit = phase6_company_inputs(ticker)
    assert prepared["normalization_version"] == NORMALIZATION_VERSION == 5
    assert all(prepared["reporting_period"][key] == original[key]
               for key in ("fiscal_year", "fiscal_period", "start_date", "end_date"))
    for field, value in original["metrics"].items():
        if value is not None and field not in audit["quarantined_legacy_fields"]:
            assert prepared["facts"][field]["value"] == value
    assert not any(row["concept"] == "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment"
                   for annual in statements[ticker]["normalized"]["annual"]
                   for row in annual["provenance"].get("depreciation_and_amortization", []))
