"""Dated public source excerpts and independently specified scope regressions."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.services.normalization import (
    complete_conventional_debt_provenance,
    extract_observations,
    normalize_company_facts,
)
from test_normalization import observation, payload


FIXTURE = Path(__file__).parent / "fixtures" / "valuation" / "phase6_provider_excerpts.json"


def retained(ticker):
    company = json.loads(FIXTURE.read_text(encoding="utf-8"))["companies"][ticker]
    return company, normalize_company_facts(company["companyfacts_excerpt"])["annual"][0]


@pytest.mark.parametrize("ticker,amount", [
    ("AAPL", 12_863_000_000), ("MSFT", 12_405_000_000),
    ("NVDA", 6_386_000_000), ("ORCL", 4_811_000_000),
])
def test_retained_stock_compensation_has_exact_native_annual_provenance(ticker, amount):
    company, annual = retained(ticker)
    assert annual["metrics"]["stock_based_compensation"] == amount
    assert annual["start_date"] == company["selected_period"]["start_date"]
    assert annual["end_date"] == company["selected_period"]["end_date"]
    records = annual["provenance"]["stock_based_compensation"]
    assert len(records) == 1
    assert records[0]["concept"] == "ShareBasedCompensation"
    assert records[0]["value"] == amount
    assert records[0]["start"] == annual["start_date"]
    assert records[0]["end"] == annual["end_date"]
    assert records[0]["filed"] <= company["retrieved_at"][:10]
    assert company["source_url"].startswith("https://data.sec.gov/api/xbrl/companyfacts/CIK")


@pytest.mark.parametrize("ticker,metric,amount", [
    ("AAPL", "noncurrent_marketable_securities", 77_723_000_000),
    ("MSFT", "long_term_investments", 36_348_000_000),
    ("MSFT", "long_term_debt_including_current", 40_294_000_000),
    ("MSFT", "gross_debt_instrument_carrying_amount", 46_136_000_000),
    ("MSFT", "finance_lease_liability", 66_594_000_000),
    ("MSFT", "operating_lease_liability", 21_925_000_000),
    ("ORCL", "finance_lease_liability", 7_701_000_000),
    ("ORCL", "operating_lease_liability", 30_190_000_000),
    ("NVDA", "total_debt_repayments", 0),
    ("AAPL", "long_term_debt_proceeds", 4_481_000_000),
    ("AAPL", "long_term_debt_repayments", 10_932_000_000),
    ("AAPL", "net_commercial_paper_borrowing", -2_032_000_000),
    ("MSFT", "debt_repayments_maturing_over_three_months", 3_000_000_000),
    ("MSFT", "change_in_accounts_receivable", 12_737_000_000),
    ("MSFT", "change_in_inventory", 461_000_000),
    ("MSFT", "change_in_accounts_payable", 5_268_000_000),
])
def test_retained_distinct_financial_scopes_are_not_aliased(ticker, metric, amount):
    _, annual = retained(ticker)
    assert annual["metrics"][metric] == amount
    assert {row["value"] for row in annual["provenance"][metric]} == {amount}
    assert all(not row.get("derivation") for row in annual["provenance"][metric])


def test_dated_investment_categories_remain_distinct():
    _, apple = retained("AAPL")
    _, microsoft = retained("MSFT")
    assert apple["metrics"]["long_term_investments"] is None
    assert microsoft["metrics"]["noncurrent_marketable_securities"] is None


@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "NVDA"])
def test_partial_or_lease_inclusive_cached_debt_cannot_complete_conventional_debt(ticker):
    _, annual = retained(ticker)
    assert annual["metrics"]["total_debt"] is None
    assert "total_debt" not in annual["provenance"]
    assert any(w["field"] == "total_debt" and w["code"] in {
        "unverified_debt_scope", "missing_debt_components",
    } for w in annual["warnings"])


def test_oracle_reported_debt_is_not_lease_or_gross_debt_substitution():
    _, annual = retained("ORCL")
    assert annual["metrics"]["total_debt"] == 129_541_000_000
    assert complete_conventional_debt_provenance(
        annual["provenance"]["total_debt"], end_date=annual["end_date"],
    )
    assert annual["metrics"]["gross_debt_instrument_carrying_amount"] == 130_105_000_000
    assert all(row["concept"] == "DebtLongtermAndShorttermCombinedAmount"
               for row in annual["provenance"]["total_debt"])


def test_reported_nvidia_da_proves_component_addition_is_not_a_general_identity():
    _, annual = retained("NVDA")
    values = annual["metrics"]
    assert values["depreciation_and_amortization"] == 2_843_000_000
    assert values["depreciation_expense"] + values["intangible_amortization_expense"] == 2_888_000_000
    for ticker in ("MSFT", "ORCL"):
        _, period = retained(ticker)
        assert period["metrics"]["depreciation_and_amortization"] is None


@pytest.mark.parametrize("prefix", ["Finance", "Operating"])
def test_lease_total_requires_both_compatible_components_and_retains_signed_sources(prefix):
    result = normalize_company_facts(payload({
        "Revenues": ("USD", [observation(100)]),
        prefix + "LeaseLiabilityCurrent": ("USD", [observation(10, None)]),
        prefix + "LeaseLiabilityNoncurrent": ("USD", [observation(40, None)]),
    }))
    annual = result["annual"][0]
    target = prefix.lower() + "_lease_liability"
    assert annual["metrics"][target] == 50
    records = annual["provenance"][target]
    assert {row["coefficient"] for row in records} == {1}
    assert sum(row["value"] * row["coefficient"] for row in records) == 50
    assert annual["metrics"]["total_debt"] is None


@pytest.mark.parametrize("case", ["missing_component", "different_period", "different_currency", "restatement_context"])
def test_partial_or_incompatible_lease_components_do_not_create_totals(case):
    facts = {
        "Revenues": ("USD", [observation(100)]),
        "FinanceLeaseLiabilityCurrent": ("USD", [observation(10, None)]),
        "FinanceLeaseLiabilityNoncurrent": ("USD", [observation(40, None)]),
    }
    if case == "missing_component":
        facts.pop("FinanceLeaseLiabilityNoncurrent")
    elif case == "different_period":
        facts["FinanceLeaseLiabilityNoncurrent"][1][0]["end"] = "2024-09-30"
    elif case == "different_currency":
        facts["FinanceLeaseLiabilityNoncurrent"] = ("EUR", facts["FinanceLeaseLiabilityNoncurrent"][1])
    else:
        facts["FinanceLeaseLiabilityNoncurrent"][1][0].update(
            accn="0000000001-25-000002", filed="2025-03-01", form="10-K/A",
        )
    assert normalize_company_facts(payload(facts))["annual"][0]["metrics"]["finance_lease_liability"] is None


def test_reported_lease_total_is_preserved_when_components_conflict():
    annual = normalize_company_facts(payload({
        "Revenues": ("USD", [observation(100)]),
        "FinanceLeaseLiability": ("USD", [observation(60, None)]),
        "FinanceLeaseLiabilityCurrent": ("USD", [observation(10, None)]),
        "FinanceLeaseLiabilityNoncurrent": ("USD", [observation(40, None)]),
    }))["annual"][0]
    assert annual["metrics"]["finance_lease_liability"] == 60
    assert annual["provenance"]["finance_lease_liability"][0]["concept"] == "FinanceLeaseLiability"
    assert any(w["code"] == "conflicting_aggregate_components" for w in annual["warnings"])


@pytest.mark.parametrize("aggregate", [True, False])
def test_complete_conventional_debt_uses_long_term_scope_once(aggregate):
    facts = {
        "Revenues": ("USD", [observation(100)]),
        "ShortTermBorrowings": ("USD", [observation(5, None)]),
        "LongTermDebtCurrent": ("USD", [observation(10, None)]),
        "LongTermDebtNoncurrent": ("USD", [observation(40, None)]),
        "FinanceLeaseLiability": ("USD", [observation(30, None)]),
    }
    if aggregate:
        facts["LongTermDebt"] = ("USD", [observation(50, None)])
    annual = normalize_company_facts(payload(facts))["annual"][0]
    assert annual["metrics"]["total_debt"] == 55
    assert complete_conventional_debt_provenance(annual["provenance"]["total_debt"], end_date=annual["end_date"])
    assert sum(row["value"] * row["coefficient"] for row in annual["provenance"]["total_debt"]) == 55


def test_conflicting_long_term_aggregate_blocks_derived_complete_debt():
    annual = normalize_company_facts(payload({
        "Revenues": ("USD", [observation(100)]),
        "ShortTermBorrowings": ("USD", [observation(5, None)]),
        "LongTermDebt": ("USD", [observation(60, None)]),
        "LongTermDebtCurrent": ("USD", [observation(10, None)]),
        "LongTermDebtNoncurrent": ("USD", [observation(40, None)]),
    }))["annual"][0]
    assert annual["metrics"]["long_term_debt_including_current"] == 60
    assert annual["metrics"]["total_debt"] is None


def test_reported_complete_debt_keeps_source_without_choosing_a_conflicting_candidate():
    annual = normalize_company_facts(payload({
        "Revenues": ("USD", [observation(100)]),
        "ShortTermBorrowings": ("USD", [observation(5, None)]),
        "LongTermDebt": ("USD", [observation(50, None)]),
        "DebtLongtermAndShorttermCombinedAmount": ("USD", [observation(60, None)]),
    }))["annual"][0]
    assert annual["metrics"]["total_debt"] is None
    assert annual["metrics"]["reported_total_debt"] == 60
    assert annual["metrics"]["short_term_debt"] == 5
    assert annual["metrics"]["long_term_debt_including_current"] == 50
    assert annual["provenance"]["reported_total_debt"][0]["concept"] == "DebtLongtermAndShorttermCombinedAmount"
    assert any(w["code"] == "conflicting_debt_components" for w in annual["warnings"])


@pytest.mark.parametrize("change", [
    {"concept": "DebtCurrent"}, {"concept": "CommercialPaper"}, {"concept": "DebtInstrumentCarryingAmount"},
    {"concept": "FinanceLeaseLiability"}, {"end": "2024-09-30"}, {"start": "2024-01-01"},
    {"unit": "EUR"}, {"value": None}, {"value": float("inf")}, {"value": True},
    {"value": -1}, {"coefficient": -1}, {"coefficient": True}, {"accn": None},
    {"filed": "2024-01-01"}, {"taxonomy": "issuer-custom"}, {"source": "unverified"},
])
def test_complete_debt_scope_validator_rejects_legacy_partial_and_malformed_records(change):
    records = extract_observations(payload({
        "DebtLongtermAndShorttermCombinedAmount": ("USD", [observation(55, None)]),
    }))
    assert complete_conventional_debt_provenance(records, end_date="2024-12-31")
    records[0].update(change)
    assert not complete_conventional_debt_provenance(records, end_date="2024-12-31")


def test_new_fields_preserve_instant_duration_and_negative_net_change_conventions():
    raw = payload({
        "Revenues": ("USD", [observation(100)]),
        "FinanceLeaseLiability": ("USD", [observation(10)]),
        "ShareBasedCompensation": ("USD", [observation(20, None)]),
        "ProceedsFromRepaymentsOfCommercialPaper": ("USD", [observation(-5)]),
        "IncreaseDecreaseInInventories": ("USD", [observation(-3)]),
    })
    original = deepcopy(raw)
    normalized = normalize_company_facts(raw)
    annual = normalized["annual"][0]
    assert raw == original
    assert annual["metrics"]["finance_lease_liability"] is None
    assert annual["metrics"]["stock_based_compensation"] is None
    assert annual["metrics"]["net_commercial_paper_borrowing"] == -5
    assert annual["metrics"]["change_in_inventory"] == -3
    assert any(w["code"] == "unexpected_reporting_period" for w in normalized["warnings"])


def test_new_cash_flow_durations_use_aligned_ytd_and_do_not_difference_instant_leases():
    facts = {}
    for concept, first, second in (
        ("ShareBasedCompensation", 30, 70),
        ("ProceedsFromRepaymentsOfCommercialPaper", -5, -1),
        ("IncreaseDecreaseInAccountsReceivable", 100, 50),
    ):
        facts[concept] = ("USD", [
            observation(first, end="2024-03-31", fp="Q1", form="10-Q", filed="2024-05-01", accn="0000000001-24-000001"),
            observation(second, end="2024-06-30", fp="Q2", form="10-Q", filed="2024-08-01", accn="0000000001-24-000002"),
        ])
    facts["FinanceLeaseLiability"] = ("USD", [
        observation(20, None, end="2024-03-31", fp="Q1", form="10-Q", filed="2024-05-01", accn="0000000001-24-000001"),
        observation(40, None, end="2024-06-30", fp="Q2", form="10-Q", filed="2024-08-01", accn="0000000001-24-000002"),
    ])
    normalized = normalize_company_facts(payload(facts))
    second = next(p for p in normalized["quarterly"] if p["fiscal_period"] == "Q2")
    assert second["start_date"] == "2024-04-01"
    for metric, expected in (("stock_based_compensation", 40), ("net_commercial_paper_borrowing", 4), ("change_in_accounts_receivable", -50)):
        assert second["metrics"][metric] == expected
        assert sum(row["coefficient"] * row["value"] for row in second["provenance"][metric]) == expected
    assert second["metrics"]["finance_lease_liability"] == 40
    assert not any(row.get("derivation") for row in second["provenance"]["finance_lease_liability"])
    assert normalized["annual"] == []  # Partial quarters never become an annual/TTM base.
    assert "ttm" not in normalized


def test_new_mapped_duration_preserves_original_and_latest_amended_vintages():
    raw = payload({"ShareBasedCompensation": ("USD", [
        observation(25),
        observation(27, form="10-K/A", filed="2025-04-01", accn="0000000001-25-000002"),
    ])})
    assert [row["value"] for row in extract_observations(raw)] == [25, 27]
    annual = normalize_company_facts(raw)["annual"][0]
    assert annual["metrics"]["stock_based_compensation"] == 27
    assert annual["provenance"]["stock_based_compensation"][0]["accn"] == "0000000001-25-000002"
    assert any(w["field"] == "stock_based_compensation" and w["code"] == "restated_fact" for w in annual["warnings"])
