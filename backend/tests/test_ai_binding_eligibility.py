"""Typed source capabilities keep quantities separate from citation-only evidence."""
from copy import deepcopy
from decimal import Decimal

import pytest

from app.ai.bindings import binding_catalog, binding_kinds, finite_number


def record(**changes):
    return {"id": "e_amount", "category": "reported_fact", "provider": "sec-edgar",
            "metric": "revenue", "value": 100, "unit": "USD", "period": None,
            "observation_date": None, "quality_warnings": [], **changes}


@pytest.mark.parametrize("value", [0, -1, 1, 0.0, -0.25, 1.25, 1e-200, 1e200])
def test_finite_numeric_sources_include_verified_zero_and_negative_values(value):
    assert finite_number(value) is True
    assert binding_kinds(record(value=value)) == ("value",)


@pytest.mark.parametrize("value", [None, True, False, "100", "NaN", [], {}, [100],
                                     float("nan"), float("inf"), -float("inf"), Decimal("100"), 10 ** 1000])
def test_non_scalar_boolean_nonfinite_and_implicit_numeric_conversions_are_excluded(value):
    assert finite_number(value) is False
    assert "value" not in binding_kinds(record(value=value))


@pytest.mark.parametrize("category", ["reported_fact", "historical_metric", "valuation_output",
                                       "policy_estimate", "user_assumption"])
def test_supported_numerical_evidence_categories_remain_eligible(category):
    assert binding_kinds(record(category=category)) == ("value",)


@pytest.mark.parametrize("category", ["unavailable", "filing_excerpt", "company_profile", "interpretation", "invented"])
def test_citation_categories_cannot_be_used_as_financial_quantities(category):
    assert "value" not in binding_kinds(record(category=category))


@pytest.mark.parametrize("unit", ["USD", "EUR", "USD/share", "USD/shares", "USD/year", "fraction",
                                   "percent", "multiple", "ratio", "number", "models", "count", "shares",
                                   "years", "fiscal years"])
def test_supported_numeric_units_have_value_capabilities(unit):
    assert "value" in binding_kinds(record(unit=unit))


@pytest.mark.parametrize("unit", [None, "", "text", "structured", "unknown", "unknown/share", "usd", "USD/unknown"])
def test_unknown_and_narrative_units_never_render_as_numeric_values(unit):
    assert "value" not in binding_kinds(record(unit=unit))


@pytest.mark.parametrize("warning", [
    "The market provider did not supply a usable current share count.",
    "Single-model estimate: there is no independent model confirmation.",
    "This historical estimate depends on explicitly disclosed forecasting or capital-value modeling policies.",
    "Dated filing-cover common shares are not a live current-day observation; future issuance, buybacks and splits may change the count.",
    "Using the cached Treasury observation dated 2026-10-13 because the current-day refresh is unavailable (provider_timeout); original source dates are retained.",
    "Provider beta estimation lookback and return frequency are not exposed; retrieval date is not a separately supplied calculation date.",
])
def test_known_msft_quality_warnings_do_not_discard_usable_dated_or_policy_values(warning):
    assert "value" in binding_kinds(record(quality_warnings=[warning]))


@pytest.mark.parametrize("observed", ["2026-07-29", "2024-02-29", "2026-10-15T20:00:01+00:00", "2026-10-15T20:00:01Z"])
def test_date_capabilities_require_real_calendar_dates_and_source_metadata(observed):
    assert "date" in binding_kinds(record(observation_date=observed))


@pytest.mark.parametrize("observed", [None, "", "not dated", "2026-02-29", "2026-13-01", "2026-10-15T25:00:00Z", 20260729, True])
def test_malformed_source_dates_have_no_date_capability(observed):
    assert "date" not in binding_kinds(record(observation_date=observed))


@pytest.mark.parametrize("period", ["FY2026", "FY2026 FY; 2025-07-01 to 2026-06-30",
                                     "FY 2022, 2023, 2024, 2025, 2026", "2021-06-30 to 2026-06-30", "2026-06-30", "10-K", "10-Q"])
def test_explicit_fiscal_periods_and_source_forms_have_period_capabilities(period):
    assert "period" in binding_kinds(record(period=period))


@pytest.mark.parametrize("period", [None, "", "FYunknown", "2026-02-30", "2026-07-01 to 2026-06-30",
                                     "FY2026 FY; 2025-07-01 to 2026-02-30", {"fiscal_year": 2026}, True])
def test_malformed_or_reversed_periods_have_no_period_capability(period):
    assert "period" not in binding_kinds(record(period=period))


def test_binding_capability_order_and_missing_value_do_not_create_zero():
    item = record(observation_date="2026-07-29", period="FY2026")
    assert binding_kinds(item) == ("value", "date", "period")
    missing = record(category="unavailable", value=None, observation_date="2026-07-29", period="FY2026")
    assert binding_kinds(missing) == ()


@pytest.mark.parametrize("gate", [{"compatible": False}, {"scope_verified": False}, {"status": "incompatible"},
                                    {"input_status": "unknown"}, {"source_type": "unavailable"}, {"evidence_type": "unavailable"}])
def test_explicit_source_incompatibility_cannot_be_repaired_by_referencing_it(gate):
    assert binding_kinds(record(observation_date="2026-07-29", period="FY2026", **gate)) == ()


@pytest.mark.parametrize("source", [
    {"category": "company_profile", "metric": "company_profile", "value": {"cik": "0000789019"}, "unit": "text"},
    {"category": "company_profile", "metric": "business_description", "value": "Office 365 provider narrative", "unit": "text"},
    {"category": "historical_metric", "metric": "valuation_methodology", "value": "FCFF discounts cash flows at WACC.", "unit": "text"},
    {"category": "valuation_output", "metric": "base_model_results", "value": {"count": 1}, "unit": "structured"},
    {"category": "reported_fact", "value": True},
    {"category": "reported_fact", "value": float("nan")},
    {"category": "reported_fact", "value": None},
])
def test_inherited_financial_metadata_does_not_make_arbitrary_or_unusable_sources_bindable(source):
    item = record(observation_date="2026-07-29", period="FY2026", **source)
    assert binding_kinds(item) == ()


def test_filing_metadata_is_bindable_without_turning_its_text_into_a_financial_quantity():
    item = record(category="filing_excerpt", provider="sec-edgar", metric="filing_passage",
                  value="Risk factors", unit="text", period="10-K", observation_date="2026-07-29")
    assert binding_kinds(item) == ("date", "period")
    assert "value" not in binding_kinds(item)


def test_model_name_binding_is_separate_from_values_and_arbitrary_text():
    item = record(category="valuation_output", provider="Fairworth Python valuation engine",
                  metric="base_model_name", value="Forward P/E", unit="text")
    assert binding_kinds(item) == ("model",)
    assert binding_kinds({**item, "metric": "business_description"}) == ()
    assert binding_kinds({**item, "metric": "valuation_methodology"}) == ()
    assert binding_kinds({**item, "category": "unavailable"}) == ()
    assert binding_kinds({**item, "provider": "permitted company profile provider"}) == ()


@pytest.mark.parametrize("name", [None, True, 100, {}, [], "", "{{value:e_amount}}", "Forward P/E\nnew claim", "<script>", "x" * 101])
def test_invalid_model_metadata_cannot_create_model_or_numeric_bindings(name):
    item = record(category="valuation_output", provider="Fairworth Python valuation engine",
                  metric="base_model_name", value=name, unit="text")
    assert "model" not in binding_kinds(item)
    assert "value" not in binding_kinds(item)


def test_catalog_keeps_unavailable_structures_and_narrative_sources_citable_without_quantity_bindings():
    records = [
        record(id="e_fair", category="policy_estimate", metric="base_fair_value", value=619.5604742486083, unit="USD/share"),
        record(id="e_price", metric="market_price", value=539.44, unit="USD/share", observation_date="2026-10-15T20:00:01+00:00"),
        record(id="e_method", category="historical_metric", metric="valuation_methodology", value="FCFF discounts unlevered cash flows at WACC.", unit="text"),
        record(id="e_models", category="valuation_output", metric="base_model_results", value={"models": [{"id": "fcff", "fair_value": None}]}, unit="structured"),
        record(id="e_debt", category="unavailable", metric="total_debt", value=None),
        record(id="e_name", category="valuation_output", provider="Fairworth Python valuation engine",
               metric="base_model_name", value="Forward P/E", unit="text"),
    ]
    registry = {item["id"]: item for item in records}
    before = deepcopy(registry)
    catalog = binding_catalog(registry)
    assert catalog == {"value": ["e_fair", "e_price"], "date": ["e_price"], "period": [],
                       "model": ["e_name"], "citation_only": ["e_method", "e_models", "e_debt"]}
    assert registry == before
