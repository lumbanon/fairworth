"""Orchestration regressions with synthetic examples and exact provider excerpts."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.core.exceptions import ApiError
from app.valuation.engine import calculate_valuation, calculation_values
from app.valuation.inputs import build_valuation_inputs
from app.valuation.scenarios import scenario_defaults
from app.valuation.schemas import DiscountRateInputs, ManualPrice, SensitivityRequest, ValuationRequest
from app.valuation.weighting import GROUP_BUDGETS, combine_valuations, suggest_weights


@pytest.fixture
def synthetic_inputs():
    """Clearly synthetic canonical data; these are not SEC/FMP company facts."""
    return {"company": {"ticker": "SYN", "name": "Synthetic model example", "is_bank": False, "is_reit": False},
            "currency": "USD", "reporting_period": {"fiscal_year": 2025, "fiscal_period": "FY",
                                                        "start_date": "2025-01-01", "end_date": "2025-12-31"},
            "values": {"revenue": 1000, "ebit": 200, "net_income": 50, "trailing_eps": 5,
                       "shares": 10, "debt": 100, "cash": 20, "book_equity": 1000,
                       "preferred_equity": 0, "minority_interest": 0, "other_nonoperating_assets": 0,
                       "depreciation_and_amortization": 20, "capex": 40},
            "market": None, "facts": {}, "annual_periods": [], "source_references": [], "warnings": [],
            "basis": {"share_basis_verified": True, "income_earnings_basis_verified": True,
                      "current_shares_available": False}}


@pytest.fixture
def verified_inputs():
    path = Path(__file__).parent / "fixtures" / "valuation" / "verified_provider_excerpts.json"
    examples = json.loads(path.read_text(encoding="utf-8"))["companies"]
    return {ticker: build_valuation_inputs(value["profile"], value["normalized"], value["retrieved_at"])
            for ticker, value in examples.items()}


def find_model(result, model_id, scenario="base"):
    return next(model for model in result["scenarios"][scenario]["models"] if model["id"] == model_id)


def pe_request(**kwargs):
    return ValuationRequest(assumptions={"forward_eps": 5.5, "target_pe": 15}, enabled_models=["pe"], **kwargs)


def fcff_request(**kwargs):
    return ValuationRequest(assumptions={"fcff": 100, "cash_flow_growth": 0, "wacc": 0.1,
                                         "terminal_growth": 0, "forecast_years": 2}, enabled_models=["fcff"], **kwargs)


def test_observed_financial_facts_survive_unavailable_assumption_defaults(synthetic_inputs):
    result = calculate_valuation(synthetic_inputs, fcff_request())
    model = find_model(result, "fcff")
    assert model["status"] == "valid", model
    assert model["fair_value"] == pytest.approx(92)  # EV1000 minusnetdebt80 on10shares.
    assert model["details"]["debt"] == 100
    assert model["details"]["cash"] == 20
    assert model["details"]["shares"] == 10


def test_explicit_user_clear_removes_a_model_input_instead_of_reusing_a_fact(synthetic_inputs):
    request = fcff_request()
    request.assumptions["debt"] = None
    result = calculate_valuation(synthetic_inputs, request)
    assert find_model(result, "fcff")["status"] == "unavailable"
    assert result["scenarios"]["base"]["summary"]["fair_value"] is None


def test_intrinsic_value_is_independent_of_market_price_availability(synthetic_inputs):
    result = calculate_valuation(synthetic_inputs, pe_request())
    summary = result["scenarios"]["base"]["summary"]
    assert summary["fair_value"] == pytest.approx(82.5)
    assert summary["upside"] is summary["margin_of_safety"] is None
    assert result["market"]["price"] is None
    assert result["reverse_dcf"]["status"] == "unavailable"
    assert summary["count"] == 1
    assert any("single-model" in warning for warning in summary["warnings"])
    json.dumps(result, allow_nan=False)


def test_manual_price_is_labeled_removable_and_does_not_mutate_provider_inputs(synthetic_inputs):
    before = deepcopy(synthetic_inputs)
    manual = calculate_valuation(synthetic_inputs, pe_request(manual_market_price=ManualPrice(value=100, currency="USD")))
    reset = calculate_valuation(synthetic_inputs, pe_request())
    assert synthetic_inputs == before
    assert manual["market"]["source_type"] == "user"
    assert manual["market"]["label"] == "User-provided market price"
    assert manual["market"]["price_timestamp"] is None
    assert manual["market"]["provider_price"] is None
    summary = manual["scenarios"]["base"]["summary"]
    assert summary["upside"] == pytest.approx(-17.5)
    assert summary["margin_of_safety"] == pytest.approx(-17.5 / 82.5 * 100)
    assert reset["market"]["price"] is None
    assert reset["scenarios"]["base"]["summary"]["fair_value"] == summary["fair_value"]


def test_manual_price_preserves_original_provider_observation(synthetic_inputs):
    synthetic_inputs["market"] = {"price": 90, "currency": "USD", "provider": "synthetic-market",
                                    "price_timestamp": "2025-12-31T21:00:00Z", "status": "stale"}
    before = deepcopy(synthetic_inputs)
    result = calculate_valuation(synthetic_inputs, pe_request(manual_market_price=ManualPrice(value=100, currency="USD")))
    assert result["market"]["price"] == 100
    assert result["market"]["provider_price"] == 90
    assert synthetic_inputs == before
    reset = calculate_valuation(synthetic_inputs, pe_request())
    assert reset["market"]["source_type"] == "provider"
    assert reset["market"]["status"] == "stale"
    assert reset["market"]["price_timestamp"] == "2025-12-31T21:00:00Z"


def test_manual_price_rejects_currency_mismatch(synthetic_inputs):
    with pytest.raises(ApiError):
        calculate_valuation(synthetic_inputs, pe_request(manual_market_price=ManualPrice(value=100, currency="EUR")))


def test_base_and_scenario_specific_edits_recalculate_independently(synthetic_inputs):
    request = pe_request(scenario_overrides={"bear": {"forward_eps": 4, "target_pe": 12},
                                            "base": {"forward_eps": 6},
                                            "bull": {"forward_eps": 7, "target_pe": 18}})
    result = calculate_valuation(synthetic_inputs, request)
    assert result["scenarios"]["bear"]["summary"]["fair_value"] == pytest.approx(48)
    assert result["scenarios"]["base"]["summary"]["fair_value"] == pytest.approx(90)
    assert result["scenarios"]["bull"]["summary"]["fair_value"] == pytest.approx(126)
    assert result["scenarios"]["base"]["assumptions"]["metadata"]["forward_eps"]["overridden"]
    # Editing base again must leave independent bear/bull inputs unchanged.
    request.scenario_overrides["base"]["forward_eps"] = 8
    edited = calculate_valuation(synthetic_inputs, request)
    assert edited["scenarios"]["base"]["summary"]["fair_value"] == pytest.approx(120)
    assert edited["scenarios"]["bear"]["summary"] == result["scenarios"]["bear"]["summary"]
    assert edited["scenarios"]["bull"]["summary"] == result["scenarios"]["bull"]["summary"]


def test_primary_user_inputs_generate_distinct_operating_scenario_defaults(synthetic_inputs):
    result = calculate_valuation(synthetic_inputs, pe_request())
    # Scenarios alterEPS andP/E separately, then the ordinaryP/E model reruns.
    assert result["scenarios"]["bear"]["summary"]["fair_value"] == pytest.approx(4.95 * 13.5)
    assert result["scenarios"]["base"]["summary"]["fair_value"] == pytest.approx(5.5 * 15)
    assert result["scenarios"]["bull"]["summary"]["fair_value"] == pytest.approx(6.05 * 16.5)


def test_invalid_scenario_is_excluded_without_corrupting_other_scenarios(synthetic_inputs):
    result = calculate_valuation(synthetic_inputs, fcff_request(scenario_overrides={"bear": {"wacc": 0.02, "terminal_growth": 0.03}}))
    assert find_model(result, "fcff", "bear")["status"] == "invalid_input"
    assert result["scenarios"]["bear"]["summary"]["fair_value"] is None
    assert result["scenarios"]["base"]["summary"]["fair_value"] == pytest.approx(92)


def test_unusual_scenario_ordering_is_reported_not_silently_sorted(synthetic_inputs):
    result = calculate_valuation(synthetic_inputs, pe_request(scenario_overrides={"bear": {"forward_eps": 10}}))
    assert result["scenarios"]["bear"]["summary"]["fair_value"] > result["scenarios"]["base"]["summary"]["fair_value"]
    assert any(warning["code"] == "scenario_ordering" for warning in result["warnings"])


def test_pe_sensitivity_center_matches_base_and_each_grid_point_uses_actual_formula(synthetic_inputs):
    spec = SensitivityRequest(model_id="pe", x_parameter="forward_eps", y_parameter="target_pe",
                              x_values=[4, 5.5, 7], y_values=[10, 15, 20])
    result = calculate_valuation(synthetic_inputs, pe_request(sensitivity=spec))
    grid = result["sensitivity"]
    assert grid["unit"] == "USD/share"
    assert grid["rows"][1]["cells"][1]["fair_value"] == result["scenarios"]["base"]["summary"]["fair_value"]
    for row in grid["rows"]:
        for cell in row["cells"]:
            assert cell["fair_value"] == pytest.approx(cell["x_value"] * row["y_value"])


def test_dcf_sensitivity_center_recalculates_discount_and_invalid_terminal_spread(synthetic_inputs):
    spec = SensitivityRequest(model_id="fcff", x_parameter="wacc", y_parameter="terminal_growth",
                              x_values=[0.08, 0.1, 0.12], y_values=[-0.01, 0, 0.1])
    result = calculate_valuation(synthetic_inputs, fcff_request(sensitivity=spec))
    grid = result["sensitivity"]
    assert grid["rows"][1]["cells"][1]["fair_value"] == pytest.approx(92)
    assert grid["rows"][2]["cells"][0]["status"] == "invalid_input"
    assert grid["rows"][2]["cells"][1]["fair_value"] is None
    # Constant100 FCFF withg0 givesEV100/WACC at every valid discount point.
    assert grid["rows"][1]["cells"][0]["fair_value"] == pytest.approx((1250 - 80) / 10)


def test_dcf_operating_sensitivity_requires_a_revenue_driven_forecast(synthetic_inputs):
    request = ValuationRequest(assumptions={"revenue_growth": 0.1, "operating_margin": 0.2,
                                           "tax_rate": 0.25, "da_ratio": 0.03,
                                           "capex_ratio": 0.05, "nwc_ratio": 0.1,
                                           "forecast_years": 2, "terminal_growth": 0, "wacc": 0.1,
                                           "growth_fade_to_terminal": False}, enabled_models=["fcff"],
                               sensitivity=SensitivityRequest(model_id="fcff", x_parameter="revenue_growth",
                                                              y_parameter="operating_margin", x_values=[0.05, 0.1, 0.15],
                                                              y_values=[0.15, 0.2, 0.25]))
    result = calculate_valuation(synthetic_inputs, request)
    grid = result["sensitivity"]
    assert grid["rows"][1]["cells"][1]["fair_value"] == pytest.approx(find_model(result, "fcff")["fair_value"])
    assert grid["rows"][2]["cells"][1]["fair_value"] > grid["rows"][0]["cells"][1]["fair_value"]


def test_reverse_dcf_requires_price_and_is_never_in_weighted_models(synthetic_inputs):
    result = calculate_valuation(synthetic_inputs, fcff_request(manual_market_price=ManualPrice(value=112, currency="USD")))
    # At10%growth, EV1200 minusnetdebt80 =>112/share.
    assert result["reverse_dcf"]["status"] == "valid", result["reverse_dcf"]
    # Policyfade is enabled bydefault; explicitly disable to isolateconstant-growth diagnostic.
    request = fcff_request(manual_market_price=ManualPrice(value=112, currency="USD"))
    request.assumptions["growth_fade_to_terminal"] = False
    exact = calculate_valuation(synthetic_inputs, request)
    assert exact["reverse_dcf"]["implied_growth"] == pytest.approx(0.1, abs=1e-8)
    assert set(exact["scenarios"]["base"]["summary"]["effective_weights"]) == {"fcff"}
    assert "reverse" not in exact["suggested_weights"]


def test_sourced_capm_and_wacc_reach_the_engine_without_fabricated_market_inputs(synthetic_inputs):
    source = {"source": "Explicitly synthetic observed-rate example", "observation_date": "2025-12-31"}
    sourced = DiscountRateInputs(risk_free_rate={**source, "value": 0.04},
                                 beta={**source, "value": 1.2, "method": "Synthetic regression example"},
                                 equity_risk_premium={**source, "value": 0.05},
                                 cost_of_debt={**source, "value": 0.05, "method": "Synthetic quoted yield example"},
                                 equity_market_value={**source, "value": 800, "currency": "USD"},
                                 debt_market_value={**source, "value": 200, "currency": "USD"}, tax_rate=0.25)
    request = fcff_request()
    del request.assumptions["wacc"]
    request.discount_rates = sourced
    result = calculate_valuation(synthetic_inputs, request)
    base = result["scenarios"]["base"]
    assert base["assumptions"]["values"]["cost_of_equity"] == pytest.approx(0.1)
    assert base["assumptions"]["values"]["wacc"] == pytest.approx(0.0875)
    assert base["assumptions"]["metadata"]["wacc"]["source_type"] == "market_derived_estimate"
    # EV=100/.0875, no terminalgrowth; equitysubtract80 on10shares.
    assert base["summary"]["fair_value"] == pytest.approx((100 / 0.0875 - 80) / 10)


def test_partial_sourced_discount_inputs_do_not_disable_independent_earnings_model(synthetic_inputs):
    request = pe_request()
    request.discount_rates = DiscountRateInputs(risk_free_rate={"value": 0.04,
                                                                "source": "Synthetic sourced observation",
                                                                "observation_date": "2025-12-31"})
    result = calculate_valuation(synthetic_inputs, request)
    assert result["scenarios"]["base"]["summary"]["fair_value"] == pytest.approx(82.5)
    assert result["scenarios"]["base"]["assumptions"]["values"]["wacc"] is None
    assert result["scenarios"]["base"]["assumptions"]["metadata"]["wacc"]["warnings"]


def test_signed_aggregation_retains_negative_equity_and_omits_margin_of_safety(synthetic_inputs):
    request = ValuationRequest(assumptions={"fcff": -100, "cash_flow_growth": 0,
                                           "wacc": 0.1, "terminal_growth": 0, "forecast_years": 2,
                                           "forward_eps": 5, "target_pe": 10}, enabled_models=["fcff", "pe"],
                               weights={"fcff": 3, "pe": 1}, manual_market_price=ManualPrice(value=100, currency="USD"))
    result = calculate_valuation(synthetic_inputs, request)
    summary = result["scenarios"]["base"]["summary"]
    assert find_model(result, "fcff")["fair_value"] == pytest.approx(-108)
    assert summary["fair_value"] == pytest.approx(-68.5)
    assert summary["effective_weights"] == {"fcff": 0.75, "pe": 0.25}
    assert summary["margin_of_safety"] is None
    assert summary["upside"] == pytest.approx(-168.5)


def test_unavailable_models_keep_user_weights_and_remaining_weights_renormalize(synthetic_inputs):
    request = pe_request(weights={"pe": 2, "fcff": 8})
    request.enabled_models = ["pe", "fcff"]
    result = calculate_valuation(synthetic_inputs, request)
    summary = result["scenarios"]["base"]["summary"]
    assert summary["fair_value"] == pytest.approx(82.5)
    assert summary["effective_weights"] == {"pe": 1}
    assert result["configured_weights"]["fcff"] == 8
    assert any("configured weight is retained" in warning for warning in summary["warnings"])


def test_no_enabled_models_returns_unavailable_instead_of_zero(synthetic_inputs):
    result = calculate_valuation(synthetic_inputs, ValuationRequest(enabled_models=[]))
    assert result["scenarios"]["base"]["summary"]["fair_value"] is None
    assert result["confidence"]["level"] == "unavailable"


def test_related_earnings_models_share_one_recommendation_budget():
    def model(model_id):
        return {"id": model_id, "status": "valid", "eligibility": {"status": "eligible"}}
    one, _ = suggest_weights([model("pe")])
    both, reasons = suggest_weights([model("pe"), model("peg")])
    assert one["pe"] == GROUP_BUDGETS["earnings"]
    assert both["pe"] + both["peg"] == one["pe"]
    assert both["pe"] > both["peg"]
    assert "family budget" in reasons["peg"]


def test_aggregation_ignores_nonfinite_invalid_and_diagnostic_outputs():
    models = [{"id": "pe", "name": "P/E", "status": "valid", "fair_value": 100},
              {"id": "peg", "name": "PEG", "status": "valid", "fair_value": float("nan")},
              {"id": "fcff", "name": "DCF", "status": "invalid_input", "fair_value": 999}]
    result = combine_valuations(models, ["pe", "peg", "fcff"], {"pe": 1, "peg": 1, "fcff": 1})
    assert result["fair_value"] == 100
    assert result["count"] == 1
    json.dumps(result, allow_nan=False)


def test_reverse_dcf_diagnostics_cannot_enter_weighted_intrinsic_value():
    models = [{"id": "pe", "name": "P/E", "status": "valid", "fair_value": 100},
              {"id": "reverse_dcf", "name": "Reverse DCF", "status": "valid", "fair_value": 500}]
    result = combine_valuations(models, ["pe", "reverse_dcf"], {"pe": 1, "reverse_dcf": 9})
    assert result["fair_value"] == 100
    assert result["effective_weights"] == {"pe": 1}


def test_scenario_defaults_preserve_supported_negative_and_extreme_ratio_economics():
    values = {"return_on_equity": -0.2, "operating_margin": -0.2, "capex_ratio": 1.5, "nwc_ratio": -0.1}
    defaults = scenario_defaults({"values": values, "metadata": {}})
    assert defaults["bear"]["values"]["return_on_equity"] < values["return_on_equity"]
    assert defaults["bull"]["values"]["return_on_equity"] > values["return_on_equity"]
    assert defaults["bear"]["values"]["capex_ratio"] > values["capex_ratio"]
    assert defaults["bull"]["values"]["capex_ratio"] < values["capex_ratio"]
    assert defaults["bear"]["values"]["nwc_ratio"] > values["nwc_ratio"]
    assert defaults["bull"]["values"]["nwc_ratio"] < values["nwc_ratio"]


def test_msft_missing_debt_is_not_zero_and_other_financial_facts_are_preserved(verified_inputs):
    inputs = verified_inputs["MSFT"]
    before = deepcopy(inputs)
    result = calculate_valuation(inputs, ValuationRequest(assumptions={"forecast_ebitda": 100000000000,
                                                                      "target_ev_ebitda": 10,
                                                                      "preferred_equity": 0,
                                                                      "minority_interest": 0,
                                                                      "other_nonoperating_assets": 0},
                                                          enabled_models=["evEbitda"]))
    assert inputs["values"]["debt"] is None
    model = find_model(result, "evEbitda")
    assert model["status"] == "unavailable"
    assert "debt" in model["eligibility"]["missing_inputs"]
    assert inputs == before


def test_orcl_explicit_forward_eps_is_an_assumption_without_quote_or_income_rescaling(verified_inputs):
    inputs = verified_inputs["ORCL"]
    before = deepcopy(inputs)
    assert inputs["market"] is None or inputs["market"].get("price") is None
    result = calculate_valuation(inputs, pe_request())
    assert result["scenarios"]["base"]["summary"]["fair_value"] == pytest.approx(82.5)
    assert result["market"]["price"] is None
    assert result["reverse_dcf"]["status"] == "unavailable"
    assert result["scenarios"]["base"]["summary"]["upside"] is None
    assert inputs["values"]["net_income"] == 17087000000
    assert inputs["values"]["free_cash_flow"] == -23686000000
    assert result["financials"]["facts"]["net_income"]["reported_value"] == 17087000000
    assert inputs == before


@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "NVDA", "ORCL"])
def test_exact_provider_excerpts_do_not_manufacture_forward_multiples_or_current_shares(verified_inputs, ticker):
    inputs = verified_inputs[ticker]
    result = calculate_valuation(inputs)
    assert result["defaults"]["base"]["values"]["target_pe"] is None
    assert not inputs["basis"]["current_shares_available"]
    assert find_model(result, "pe")["status"] == "unavailable"
    assert find_model(result, "fcfe")["status"] == "unavailable"
    assert result["scenarios"]["base"]["summary"]["fair_value"] is None
    json.dumps(result, allow_nan=False)


def test_scope_confirmation_unlocks_reported_eps_with_historical_source_metadata(verified_inputs):
    result = calculate_valuation(verified_inputs["ORCL"], ValuationRequest(assumptions={"share_basis_confirmed": True, "target_pe": 20}))
    base = result["scenarios"]["base"]
    assert base["assumptions"]["metadata"]["earnings_growth"]["source_type"] == "historical_estimate"
    assert base["assumptions"]["metadata"]["forward_eps"]["source_type"] == "derived_estimate"
    assert find_model(result, "pe")["status"] == "valid"
    assert result["financials"]["basis"]["income_earnings_basis_verified"] is False


def test_book_methods_require_common_equity_scope_even_for_banks(synthetic_inputs):
    synthetic_inputs["company"]["is_bank"] = True
    request = ValuationRequest(assumptions={"target_pb": 2}, enabled_models=["pb"])
    result = calculate_valuation(synthetic_inputs, request)
    assert find_model(result, "pb")["status"] == "unavailable"
    assert "common_equity_basis_confirmed" in find_model(result, "pb")["eligibility"]["missing_inputs"]
    request.assumptions["common_equity_basis_confirmed"] = True
    assert find_model(calculate_valuation(synthetic_inputs, request), "pb")["fair_value"] == 200


def test_reverse_dcf_can_solve_growth_when_no_forward_growth_is_supplied(synthetic_inputs):
    request = fcff_request(manual_market_price={"value": 92, "currency": "USD"})
    del request.assumptions["cash_flow_growth"]
    synthetic_inputs["values"]["free_cash_flow"] = None
    result = calculate_valuation(synthetic_inputs, request)
    assert result["reverse_dcf"]["status"] == "valid"
    assert result["reverse_dcf"]["implied_growth"] == pytest.approx(0, abs=1e-8)


def test_overflowing_market_comparisons_are_unavailable_finite_json(synthetic_inputs):
    request = pe_request(manual_market_price={"value": 5e-324, "currency": "USD"})
    result = calculate_valuation(synthetic_inputs, request)
    assert result["scenarios"]["base"]["summary"]["upside"] is None
    assert result["scenarios"]["base"]["summary"]["fair_value"] == pytest.approx(82.5)
    json.dumps(result, allow_nan=False)


def test_dated_reported_model_baselines_have_explicit_default_sources(verified_inputs):
    result = calculate_valuation(verified_inputs["AAPL"])
    defaults = result["defaults"]["base"]
    for key in ("shares", "debt", "cash", "book_equity"):
        assert defaults["values"][key] == verified_inputs["AAPL"]["values"][key]
        assert defaults["metadata"][key]["source_type"] == "reported_input"
        assert defaults["metadata"][key]["observation_period"]["fiscal_year"] == 2025
    missing = calculate_valuation(verified_inputs["MSFT"])["defaults"]["base"]
    assert missing["values"]["debt"] is None
    assert missing["metadata"]["debt"]["source_type"] == "unavailable"
