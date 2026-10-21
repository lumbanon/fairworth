"""Debt/cash scope reconciliation, with real retained and synthetic controls."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.schemas.common import FinancialPeriod
from app.services.normalization import NORMALIZATION_VERSION, normalize_company_facts, reconcile_debt_evidence
from app.valuation.completeness import build_data_completeness
from app.valuation.automatic import prepare_automatic_inputs
from app.valuation.inputs import build_valuation_inputs, normalize_annual_period
from test_normalization import observation, payload


FIXTURE = Path(__file__).parent / "fixtures/valuation/phase671_financial_scope_excerpts_2026_10_20.json"


def debt_payload(*, total=55, long=50):
    return payload({"Revenues": ("USD", [observation(100)]),
        "ShortTermBorrowings": ("USD", [observation(5, None)]),
        "LongTermDebt": ("USD", [observation(long, None)]),
        "LongTermDebtCurrent": ("USD", [observation(10, None)]),
        "LongTermDebtNoncurrent": ("USD", [observation(40, None)]),
        "DebtLongtermAndShorttermCombinedAmount": ("USD", [observation(total, None)])})


def candidate_map(annual):
    return {row["id"]: row for row in annual["financial_reconciliations"]["debt"]["candidates"]}


@pytest.mark.parametrize("reported", [True, False])
def test_compatible_complete_debt_paths_keep_values_and_auditable_same_scope_candidates(reported):
    raw = debt_payload()
    if not reported:
        raw["facts"]["us-gaap"].pop("DebtLongtermAndShorttermCombinedAmount")
    original = deepcopy(raw)
    annual = normalize_company_facts(raw)["annual"][0]
    assert raw == original
    assert annual["metrics"]["total_debt"] == 55
    result = annual["financial_reconciliations"]["debt"]
    assert result["status"] == "available" and result["effective_total_debt"] == 55
    candidates = candidate_map(annual)
    for key in ("short_term_plus_long_term", "short_term_plus_current_noncurrent"):
        assert candidates[key]["value"] == 55 and candidates[key]["scope_complete"]
        assert {row["accn"] for row in candidates[key]["provenance"]} == {"0000000001-25-000001"}
    assert not candidates["reported_long_term"]["scope_complete"]
    assert candidates["reported_long_term"]["value"] == 50


def test_reported_and_derived_conflict_preserves_both_and_quarantines_only_effective_debt():
    annual = normalize_company_facts(debt_payload(total=60))["annual"][0]
    values = annual["metrics"]
    assert values["total_debt"] is None and "total_debt" not in annual["provenance"]
    assert values["reported_total_debt"] == 60 and values["long_term_debt_including_current"] == 50
    candidates = candidate_map(annual)
    assert candidates["reported_total_debt"]["value"] == 60
    assert candidates["short_term_plus_long_term"]["value"] == 55
    comparisons = annual["financial_reconciliations"]["debt"]["comparisons"]
    assert {row["difference"] for row in comparisons if row["status"] == "conflict"} == {5}
    assert any(row["code"] == "unresolved_debt_reconciliation" for row in annual["warnings"])


@pytest.mark.parametrize("currency_scope", ["period", "dataset", "api_round_trip"])
def test_legacy_reported_debt_cannot_erase_conflict_with_forged_reconciliation_metadata(currency_scope):
    annual = normalize_company_facts(debt_payload(total=60))["annual"][0]
    annual["metrics"]["total_debt"] = 60
    annual["provenance"]["total_debt"] = deepcopy(annual["provenance"]["reported_total_debt"])
    annual["financial_reconciliations"] = {"debt": {"status": "available", "effective_total_debt": 60}}
    if currency_scope == "dataset":
        annual.pop("currency")
    elif currency_scope == "api_round_trip":
        annual = FinancialPeriod.model_validate(annual).model_dump(mode="json")
        assert "currency" not in annual
    original = deepcopy(annual)
    canonical = normalize_annual_period(annual, "USD", "2025-03-01T00:00:00Z")
    assert annual == original
    assert canonical["facts"]["total_debt"]["value"] is None
    assert canonical["facts"]["total_debt"]["reported_value"] == 60
    assert canonical["facts"]["reported_total_debt"]["value"] == 60
    assert canonical["financial_reconciliations"]["debt"]["status"] == "conflict"
    assert canonical["financial_reconciliations"]["debt"]["effective_total_debt"] is None


@pytest.mark.parametrize("reported,expected", [(60, None), (55, 55)])
def test_dataset_currency_scope_survives_legacy_baseline_and_automatic_observation(reported, expected):
    normalized = normalize_company_facts(debt_payload(total=reported))
    annual = normalized["annual"][0]
    annual.pop("currency")
    annual["metrics"]["total_debt"] = reported
    annual["provenance"]["total_debt"] = deepcopy(annual["provenance"]["reported_total_debt"])
    annual["financial_reconciliations"] = {"debt": {"status": "available", "effective_total_debt": reported}}
    inputs = build_valuation_inputs({"ticker": "SYNTH"}, normalized, "2025-03-01T00:00:00Z")
    assert inputs["values"]["debt"] == expected
    assert inputs["currency"] == "USD"
    record = {"value": reported, "unit": "USD", "state": "verified_value", "source_type": "reported",
        "provider": "sec-edgar", "observation_date": "2024-12-31", "period": deepcopy(inputs["reporting_period"]),
        "provenance": deepcopy(inputs["facts"]["reported_total_debt"]["provenance"])}
    # A stale diagnostic cannot override the independently validated baseline.
    inputs["financial_reconciliations"] = {"debt": {"status": "available", "effective_total_debt": reported}}
    prepared = prepare_automatic_inputs(inputs, {"as_of_date": "2025-03-01", "observations": {"debt": record}})
    assert prepared["values"]["debt"] == expected
    if expected is None:
        assert prepared["automatic_assumptions"]["debt"]["value"] is None
        assert prepared["automatic_assumptions"]["debt"]["reported_value"] == reported


@pytest.mark.parametrize("reported,expected", [(60, None), (55, 55)])
def test_additional_sec_observation_cannot_restore_one_conflicting_debt_candidate(reported, expected):
    normalized = normalize_company_facts(debt_payload(total=reported))
    inputs = build_valuation_inputs({"ticker": "SYNTH"}, normalized, "2025-03-01T00:00:00Z")
    record = {"value": reported, "unit": "USD", "state": "verified_value", "source_type": "reported",
        "provider": "sec-edgar", "observation_date": "2024-12-31", "period": deepcopy(inputs["reporting_period"]),
        "provenance": deepcopy(inputs["facts"]["reported_total_debt"]["provenance"])}
    evidence = {"as_of_date": "2025-03-01", "observations": {"debt": record}}
    original = deepcopy(inputs)
    prepared = prepare_automatic_inputs(inputs, evidence)
    assert inputs == original
    assert prepared["values"]["debt"] == expected
    if expected is None:
        assert prepared["automatic_assumptions"]["debt"]["value"] is None
        assert prepared["automatic_assumptions"]["debt"]["reported_value"] == reported
        assert prepared["financial_reconciliations"]["debt"]["status"] == "conflict"


@pytest.mark.parametrize("change", [
    {"unit": "EUR"}, {"end": "2024-09-30"}, {"start": "2024-01-01"},
    {"source": "unverified"}, {"taxonomy": "custom"}, {"value": 999},
    {"coefficient": -1}, {"accn": None}, {"value": True},
])
def test_unverified_component_cannot_create_a_conflict_or_claim_complete_debt(change):
    annual = normalize_company_facts(debt_payload(total=60))["annual"][0]
    annual["provenance"]["short_term_debt"][0].update(change)
    result = reconcile_debt_evidence(annual)
    # The long-term subtotal still reconciles; an invalid short borrowing fact
    # is not evidence of a competing complete debt amount.
    assert result["status"] != "conflict"
    assert not any(row["scope_complete"] for row in result["candidates"] if row["id"].startswith("short_term_"))
    assert all(row["status"] == "not_comparable" for row in result["comparisons"]
               if row["left_candidate"] == "reported_total_debt")


def test_different_filing_contexts_preserve_candidates_without_comparing_unlike_vintages():
    raw = debt_payload(total=60)
    for concept in ("ShortTermBorrowings", "LongTermDebt", "LongTermDebtCurrent", "LongTermDebtNoncurrent"):
        raw["facts"]["us-gaap"][concept]["units"]["USD"][0].update(
            accn="0000000001-25-000002", filed="2025-04-01", form="10-K/A")
    annual = normalize_company_facts(raw)["annual"][0]
    assert annual["metrics"]["total_debt"] == 60
    comparisons = annual["financial_reconciliations"]["debt"]["comparisons"]
    assert all(row["status"] == "not_comparable" for row in comparisons
               if row["left_candidate"] == "reported_total_debt")


def test_nonfinite_candidate_sum_and_currency_mismatch_cannot_create_comparable_debt():
    annual = normalize_company_facts(debt_payload())["annual"][0]
    for field in ("short_term_debt", "long_term_debt_including_current"):
        annual["metrics"][field] = 1e308
        annual["provenance"][field][0].update(value=1e308, val=1e308)
    result = reconcile_debt_evidence(annual)
    candidate = next(row for row in result["candidates"] if row["id"] == "short_term_plus_long_term")
    assert candidate["value"] is None and not candidate["compatible_source_context"]
    assert all(row["status"] == "not_comparable" for row in result["comparisons"]
               if row["right_candidate"] == "short_term_plus_long_term")
    annual["currency"] = "EUR"
    assert not any(row["compatible_source_context"] for row in reconcile_debt_evidence(annual)["candidates"])


def test_invalid_legacy_source_numbers_stay_unavailable_and_json_serializable():
    annual = normalize_company_facts(debt_payload())["annual"][0]
    annual["provenance"]["short_term_debt"][0].update(value=float("inf"), val=float("inf"))
    annual["metrics"]["gross_debt_instrument_carrying_amount"] = float("nan")
    result = reconcile_debt_evidence(annual)
    json.dumps(result, allow_nan=False)
    candidate = next(row for row in result["candidates"] if row["id"] == "short_term_plus_long_term")
    assert not candidate["compatible_source_context"]
    assert next(row for row in candidate["provenance"] if row["concept"] == "ShortTermBorrowings")["value"] is None


@pytest.mark.parametrize("missing", ["ShortTermBorrowings", "LongTermDebtNoncurrent"])
def test_missing_components_are_never_verified_zero(missing):
    raw = debt_payload()
    raw["facts"]["us-gaap"].pop(missing)
    raw["facts"]["us-gaap"].pop("DebtLongtermAndShorttermCombinedAmount")
    if missing == "LongTermDebtNoncurrent":
        raw["facts"]["us-gaap"].pop("LongTermDebt")
    annual = normalize_company_facts(raw)["annual"][0]
    assert annual["metrics"]["total_debt"] is None
    assert any(row["missing_inputs"] for row in candidate_map(annual).values())


def test_reported_zero_borrowing_retains_its_proof_and_is_not_a_missing_value():
    raw = debt_payload(total=50)
    raw["facts"]["us-gaap"]["ShortTermBorrowings"]["units"]["USD"][0]["val"] = 0
    annual = normalize_company_facts(raw)["annual"][0]
    assert annual["metrics"]["total_debt"] == 50
    candidate = candidate_map(annual)["short_term_plus_current_noncurrent"]
    assert candidate["scope_complete"] and not candidate["missing_inputs"]
    assert next(row for row in candidate["provenance"] if row["concept"] == "ShortTermBorrowings")["value"] == 0


@pytest.mark.parametrize("symbol,difference", [("AMZN", 440_000_000), ("GOOGL", 542_000_000)])
def test_real_prior_authorized_debt_conflicts_are_exact_and_do_not_unlock_models(symbol, difference):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    entry = next(row for row in fixture["issuers"] if row["symbol"] == symbol)
    original = deepcopy(entry)
    normalized = normalize_company_facts(entry["raw"], cik=entry["cik"])
    assert entry == original and normalized["normalization_version"] == NORMALIZATION_VERSION == 6
    annual = max(normalized["annual"], key=lambda row: row["end_date"])
    assert annual["metrics"]["total_debt"] is None
    result = annual["financial_reconciliations"]["debt"]
    comparison = next(row for row in result["comparisons"] if row["left_candidate"] == "reported_long_term")
    assert comparison["status"] == "conflict" and comparison["difference"] == difference
    assert result["effective_total_debt"] is None
    assert all(row["end"] == "2025-12-31" and row["unit"] == "USD" and row["accn"]
               for candidate in result["candidates"] for row in candidate["provenance"])
    if symbol == "GOOGL":
        # The matching magnitude is disclosed separately, never used to infer
        # an undocumented sign convention or choose a complete debt candidate.
        assert annual["metrics"]["debt_discount_premium_and_issuance_costs_net"] == -difference
        assert any(row["field"] == "debt_discount_premium_and_issuance_costs_net"
                   for row in result["separate_scopes"])


def test_retained_restricted_cash_is_a_distinct_scope_not_an_unrestricted_cash_fallback():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    entry = next(row for row in fixture["issuers"] if row["symbol"] == "AMZN")
    normalized = normalize_company_facts(entry["raw"], cik=entry["cik"])
    annual = normalized["annual"][0]
    values = annual["metrics"]
    assert values["cash_and_cash_equivalents"] == 86_810_000_000
    assert values["cash_including_restricted_cash"] == 90_106_000_000
    assert values["restricted_cash_current"] == 300_000_000
    assert values["restricted_cash_noncurrent"] == 2_996_000_000
    assert values["restricted_cash_and_investments"] == 3_296_000_000
    assert annual["provenance"]["restricted_cash_current"][0]["concept"] == "RestrictedCashCurrent"
    inputs = build_valuation_inputs({"ticker": "AMZN"}, normalized, entry["source"]["retrieved_at"])
    assert inputs["values"]["cash"] == 86_810_000_000
    assert inputs["values"]["change_nwc"] is None and inputs["values"]["net_borrowing"] is None
    raw = deepcopy(entry["raw"])
    raw["facts"]["us-gaap"].pop("CashAndCashEquivalentsAtCarryingValue")
    no_unrestricted = build_valuation_inputs({"ticker": "AMZN"}, normalize_company_facts(raw))
    assert no_unrestricted["values"]["cash"] is None


@pytest.mark.parametrize("unit,record", [
    ("EUR", observation(10, None)), ("USD", observation(10)),
    ("USD", observation(-1, None)), ("USD", observation(10, None, accn=None)),
])
def test_restricted_cash_requires_reported_instant_scope_units_and_source(unit, record):
    annual = normalize_company_facts(payload({"Revenues": ("USD", [observation(100)]),
        "RestrictedCashCurrent": (unit, [record])}))["annual"][0]
    assert annual["metrics"]["restricted_cash_current"] is None
    assert annual["metrics"]["cash_and_cash_equivalents"] is None
    assert "restricted_cash_current" not in annual["provenance"]


def test_restricted_cash_verified_zero_stays_separate_without_verifying_unrestricted_zero():
    annual = normalize_company_facts(payload({"Revenues": ("USD", [observation(100)]),
        "RestrictedCashCurrent": ("USD", [observation(0, None)])}))["annual"][0]
    assert annual["metrics"]["restricted_cash_current"] == 0
    assert annual["provenance"]["restricted_cash_current"][0]["value"] == 0
    assert annual["metrics"]["cash_and_cash_equivalents"] is None


@pytest.mark.parametrize("symbol,amount", [("ORCL", 129_541_000_000), ("PGR", 6_897_000_000)])
def test_independently_reported_conventional_debt_remains_unchanged(symbol, amount):
    fixture = json.loads((FIXTURE.parent / "phase67_sec_financial_excerpts_2026_10_20.json").read_text(encoding="utf-8"))
    entry = next(row for row in fixture["issuers"] if row["symbol"] == symbol)
    annual = max(normalize_company_facts(entry["raw"], cik=entry["cik"])["annual"], key=lambda row: row["end_date"])
    assert annual["metrics"]["total_debt"] == amount
    assert annual["financial_reconciliations"]["debt"]["status"] == "available"


def test_reconciliation_survives_statement_api_canonical_inputs_and_completeness():
    normalized = normalize_company_facts(debt_payload(total=60))
    annual = normalized["annual"][0]
    statement = FinancialPeriod.model_validate(annual).model_dump(mode="json")
    assert statement["financial_reconciliations"] == annual["financial_reconciliations"]
    inputs = build_valuation_inputs({"ticker": "SYNTH"}, normalized, "2025-03-01T00:00:00Z")
    inventory = build_data_completeness(inputs, {}, [], {})
    assert inventory["financial_reconciliations"] == inputs["financial_reconciliations"]
    assert inventory["financial_reconciliations"]["debt"]["status"] == "conflict"
    assert inventory["fields"]["reported_total_debt"]["value"] == 60
    assert inventory["fields"]["total_debt"]["value"] is None
