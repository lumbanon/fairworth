"""Independent hand calculations on explicitly synthetic financial examples.

Amounts below are absolute units and shares are actual counts. Expected results
use stated cash-flow tables or exact rational arithmetic, never the JS engine or
the Python model under test to generate an expected answer.
"""

import json
from fractions import Fraction
from math import sqrt

import pytest

from app.valuation.models import MODEL_FUNCTIONS, missing_inputs, required_inputs
from app.valuation.models import (ddm, ev_ebitda, ev_revenue, fcfe_dcf, fcff_dcf,
                                  forward_pe, graham, peg, price_to_book, reit_affo, residual_income)
from app.valuation.models.reverse_dcf import calculate as reverse_dcf, solve_bounded


BRIDGE = {"debt": 100, "cash": 20, "preferred_equity": 6,
          "minority_interest": 4, "other_nonoperating_assets": 3}
ZERO_BRIDGE = {key: 0 for key in BRIDGE}
DCF = {"fcff": 100, "fcfe": 100, "cash_flow_growth": 0,
       "wacc": 0.1, "cost_of_equity": 0.1, "terminal_growth": 0,
       "forecast_years": 2, "shares": 10, "currency": "USD", **BRIDGE}


def valid(result, expected):
    assert result["status"] == "valid", result
    assert result["fair_value"] == pytest.approx(float(expected), rel=1e-10, abs=1e-8)
    json.dumps(result, allow_nan=False)


def test_fcff_perpetuity_discounts_and_bridges_every_claim_exactly_once():
    result = fcff_dcf.calculate(DCF)
    # EV=100/10%=1000. Equity=1000-100+20-6-4+3=913.
    valid(result, 91.3)
    assert result["details"]["enterprise_value"] == pytest.approx(1000)
    assert result["details"]["equity_value"] == pytest.approx(913)
    assert result["details"]["projection"][0]["present_value"] == pytest.approx(Fraction(1000, 11))


def test_fcff_growing_projection_and_terminal_discounting():
    result = fcff_dcf.calculate({**DCF, "cash_flow_growth": 0.1})
    # CF110/121 each PV100; terminal PV1210/1.21=1000; EV1200.
    valid(result, 111.3)
    assert result["details"]["terminal_present_value"] == pytest.approx(1000)


def test_negative_forecast_growth_is_valid():
    # PV90/1.1 + PV81/1.21 + terminal810/1.21 = 9000/11.
    valid(fcff_dcf.calculate({**DCF, **ZERO_BRIDGE, "cash_flow_growth": -0.1}), Fraction(900, 11))


def test_negative_explicit_forecasts_can_recover_to_positive_terminal_cash_flow():
    result = fcff_dcf.calculate({**DCF, **ZERO_BRIDGE, "projected_fcff": [-20, 30]})
    # -20/1.1 + (30+300)/1.21 = 2800/11 EV.
    valid(result, Fraction(280, 11))
    assert any("negative" in warning for warning in result["warnings"])


def test_negative_terminal_cash_flows_and_negative_equity_are_preserved():
    result = fcff_dcf.calculate({**DCF, **ZERO_BRIDGE, "fcff": -100})
    valid(result, -100)
    assert any("nonpositive" in warning for warning in result["warnings"])
    valid(ev_revenue.calculate({"forecast_revenue": 10, "target_ev_revenue": 1,
                               "shares": 10, **ZERO_BRIDGE, "debt": 30}), -2)


def test_fcff_and_fcfe_require_distinct_complete_components():
    components = {"ebit": 200, "net_income": 150, "tax_rate": 0.25,
                  "depreciation_and_amortization": 20, "capex": 40,
                  "change_nwc": 30, "net_borrowing": 10}
    inputs = {**DCF, **ZERO_BRIDGE, **components, "fcff": None, "fcfe": None}
    # FCFF=150+20-40-30=100. FCFE=150+20-40-30+10=110.
    valid(fcff_dcf.calculate(inputs), 100)
    valid(fcfe_dcf.calculate({**inputs, "debt": 999999999}), 110)
    no_borrowing = fcfe_dcf.calculate({**inputs, "net_borrowing": None})
    assert no_borrowing["status"] == "unavailable"
    assert "net_borrowing" in no_borrowing["warnings"][0]


def test_ordinary_free_cash_flow_is_not_unlevered_or_equity_cash_flow():
    for module in (fcff_dcf, fcfe_dcf):
        result = module.calculate({**DCF, "fcff": None, "fcfe": None, "free_cash_flow": 100})
        assert result["status"] == "unavailable"


def test_revenue_drivers_project_financial_statements_and_incremental_nwc():
    result = fcff_dcf.calculate({**DCF, **ZERO_BRIDGE, "fcff": None,
                                 "revenue": 1000, "revenue_growth": 0.1,
                                 "operating_margin": 0.2, "tax_rate": 0.25,
                                 "capex_ratio": 0.05, "da_ratio": 0.03, "nwc_ratio": 0.1})
    # Y1: NOPAT165 + DA33 - capex55 - ΔNWC10 =133.
    # Y2: NOPAT181.5 + DA36.3 - capex60.5 - ΔNWC11 =146.3.
    # Sustainable terminal revenue1210: ΔNWC0, so FCFF157.3, not146.3.
    expected_ev = Fraction(1330, 11) + Fraction(14630, 121) + Fraction(157300, 121)
    valid(result, expected_ev / 10)
    assert result["details"]["projection"][0]["cash_flow"] == pytest.approx(133)
    assert result["details"]["projection"][1]["change_nwc"] == pytest.approx(11)
    assert result["details"]["terminal_cash_flow"] == pytest.approx(157.3)
    assert result["details"]["terminal_projection"]["change_nwc"] == 0


def test_fcfe_drivers_require_borrowing_and_do_not_reapply_the_equity_bridge():
    inputs = {**DCF, "fcfe": None, "revenue": 1000, "revenue_growth": 0.1,
              "net_margin": 0.1, "capex_ratio": 0.05, "da_ratio": 0.03,
              "nwc_ratio": 0.1, "net_borrowing": 10}
    result = fcfe_dcf.calculate(inputs)
    # CF1=110+33-55-10+10=88; CF2=121+36.3-60.5-11+10=95.8.
    # Terminal income/DA/capex121/36.3/60.5, noΔNWC, borrowing10 =>106.8.
    valid(result, (Fraction(880, 11) + Fraction(9580, 121) + Fraction(106800, 121)) / 10)
    assert "enterprise_value" not in result["details"]
    assert fcfe_dcf.calculate({**inputs, "net_borrowing": None})["status"] == "unavailable"


def test_growth_fading_changes_forecast_assumptions_instead_of_scaling_valuation():
    result = fcff_dcf.calculate({**DCF, **ZERO_BRIDGE, "forecast_years": 3,
                                 "cash_flow_growth": 0.1, "growth_fade_to_terminal": True})
    # Explicit growth10%,5%,0% => CF110,115.5,115.5, followed by constant terminalCF.
    expected = Fraction(1100, 11) + Fraction(11550, 121) + Fraction(115500, 1331) + Fraction(1155000, 1331)
    valid(result, expected / 10)
    assert [row["forecast_growth"] for row in result["details"]["projection"]] == pytest.approx([0.1, 0.05, 0])


def test_explicit_starting_cash_flow_override_takes_precedence_over_driver_defaults():
    result = fcff_dcf.calculate({**DCF, **ZERO_BRIDGE, "revenue": 1000, "revenue_growth": 0.1,
                                 "operating_margin": 0.2, "tax_rate": 0.25,
                                 "capex_ratio": 0.05, "da_ratio": 0.03, "nwc_ratio": 0.1})
    valid(result, 100)
    assert "revenue" not in result["details"]["projection"][0]


@pytest.mark.parametrize("field", list(BRIDGE))
def test_enterprise_bridge_does_not_default_any_missing_component_to_zero(field):
    result = fcff_dcf.calculate({**DCF, field: None})
    assert result["status"] == "unavailable"
    assert field in result["details"]["missing_inputs"]


@pytest.mark.parametrize("updates", [
    {"shares": None}, {"wacc": None}, {"terminal_growth": None},
])
def test_missing_critical_inputs_are_unavailable(updates):
    assert fcff_dcf.calculate({**DCF, **updates})["status"] == "unavailable"


@pytest.mark.parametrize("updates", [
    {"shares": 0}, {"shares": -1}, {"shares": float("nan")}, {"shares": float("inf")},
    {"shares": "10"}, {"shares": True}, {"wacc": 0}, {"wacc": -0.1},
    {"wacc": 0.02, "terminal_growth": 0.03}, {"terminal_growth": 0.1},
    {"cash_flow_growth": -1}, {"forecast_years": 0}, {"forecast_years": 31},
    {"forecast_years": 1.5}, {"projected_fcff": [100]}, {"projected_fcff": [100, float("nan")]},
    {"shares_unit": "millions"}, {"amount_scale": "millions"},
    {"forecast_currency": "EUR"}, {"debt": -1},
])
def test_dcf_invalid_numeric_and_unit_inputs_never_leak_nonfinite_json(updates):
    result = fcff_dcf.calculate({**DCF, **updates})
    assert result["status"] == "invalid_input", result
    assert result["fair_value"] is None
    json.dumps(result, allow_nan=False)


def test_forward_pe_uses_explicit_forward_eps_or_transparently_forecasts_reported_eps():
    valid(forward_pe.calculate({"forward_eps": 5.5, "target_pe": 15}), 82.5)
    result = forward_pe.calculate({"trailing_eps": 5, "earnings_growth": 0.1, "target_pe": 15})
    valid(result, 82.5)
    assert "reported trailing" in result["details"]["earnings_basis"]
    assert forward_pe.calculate({"net_income": 100, "shares": 20, "target_pe": 15})["status"] == "unavailable"


def test_ev_ebitda_forecast_multiple_and_enterprise_bridge():
    inputs = {"revenue": 1000, "revenue_growth": 0.1, "ebitda_margin": 0.2,
              "target_ev_ebitda": 10, "shares": 20, **BRIDGE,
              "debt": 200, "cash": 50, "other_nonoperating_assets": 0}
    valid(ev_ebitda.calculate(inputs), 102)
    valid(ev_ebitda.calculate({**inputs, "forecast_ebitda": 220}), 102)


def test_ev_revenue_forecast_multiple_and_enterprise_bridge():
    valid(ev_revenue.calculate({"revenue": 1000, "revenue_growth": 0.1,
                               "target_ev_revenue": 2.5, "shares": 20, **BRIDGE,
                               "debt": 200, "cash": 50, "other_nonoperating_assets": 0}), 129.5)


def test_peg_uses_percentage_points_and_forward_earnings():
    result = peg.calculate({"trailing_eps": 5, "earnings_growth": 0.12, "target_peg": 2})
    valid(result, 134.4)
    assert result["details"]["justified_pe"] == pytest.approx(24)
    assert result["details"]["growth_percent"] == pytest.approx(12)


def test_graham_conventional_formula_uses_reported_eps_and_book_per_share():
    valid(graham.calculate({"trailing_eps": 4, "book_equity": 180, "shares": 20}), sqrt(810))


def test_stable_ddm_and_zero_and_negative_growth():
    valid(ddm.calculate({"dividend_per_share": 2, "dividend_growth": 0.04, "cost_of_equity": 0.08}), 52)
    valid(ddm.calculate({"dividend_per_share": 2, "dividend_growth": 0, "cost_of_equity": 0.1}), 20)
    valid(ddm.calculate({"dividend_per_share": 2, "dividend_growth": -0.02, "cost_of_equity": 0.08}), 19.6)


def test_multistage_ddm_discounts_dividends_and_terminal_value_per_share():
    valid(ddm.calculate({"projected_dividends": [2, 2.2], "forecast_years": 2,
                         "terminal_growth": 0, "cost_of_equity": 0.1}), Fraction(240, 11))


def test_residual_income_constant_book_uses_an_equity_capital_charge():
    inputs = {"book_equity": 1000, "shares": 10, "return_on_equity": 0.12,
              "payout_ratio": 1, "cost_of_equity": 0.1, "terminal_growth": 0, "forecast_years": 2}
    valid(residual_income.calculate(inputs), 120)
    valid(residual_income.calculate({**inputs, "return_on_equity": 0.08}), 80)
    valid(residual_income.calculate({**inputs, "return_on_equity": 0.1}), 100)


def test_residual_income_terminal_capital_charge_uses_ending_book_not_last_year_book():
    result = residual_income.calculate({"book_equity": 1000, "shares": 10, "return_on_equity": 0.12,
                                       "payout_ratio": 0.5, "cost_of_equity": 0.1,
                                       "terminal_growth": 0, "forecast_years": 2})
    # Books1000→1060→1123.6. RI20,21.2; next RI22.472 on1123.6.
    # V=1000+20/1.1+21.2/1.21+(22.472/.1)/1.21.
    valid(result, Fraction(147792, 1210))
    assert result["details"]["terminal_residual_income"] == pytest.approx(22.472)
    assert result["details"]["projection"][1]["ending_book_equity"] == pytest.approx(1123.6)


def test_residual_income_can_model_temporary_losses_with_explicit_terminal_recovery():
    result = residual_income.calculate({"book_equity": 1000, "shares": 10, "return_on_equity": -0.2,
                                       "terminal_roe": 0.1, "payout_ratio": 1,
                                       "cost_of_equity": 0.1, "terminal_growth": 0, "forecast_years": 1})
    # One loss200 plus100 equity charge =>RI-300; terminalRI0 atKe.
    valid(result, Fraction(800, 11))
    assert result["details"]["projection"][0]["dividends"] == 0


def test_pb_and_verified_affo_multiples():
    valid(price_to_book.calculate({"book_equity": 180, "shares": 20, "target_pb": 1.5}), 13.5)
    valid(reit_affo.calculate({"forecast_affo": 90, "shares": 20, "target_p_affo": 16}), 72)
    assert reit_affo.calculate({"net_income": 90, "free_cash_flow": 90,
                                "shares": 20, "target_p_affo": 16})["status"] == "unavailable"


@pytest.mark.parametrize("module,inputs", [
    (forward_pe, {"forward_eps": 0, "target_pe": 15}),
    (forward_pe, {"forward_eps": -5, "target_pe": 15}),
    (forward_pe, {"forward_eps": 5, "target_pe": 1001}),
    (peg, {"forward_eps": 5, "earnings_growth": 0, "target_peg": 2}),
    (peg, {"forward_eps": 5, "earnings_growth": -0.1, "target_peg": 2}),
    (graham, {"trailing_eps": 5, "book_equity": -10, "shares": 10}),
    (price_to_book, {"book_equity": 0, "shares": 10, "target_pb": 1}),
    (ddm, {"dividend_per_share": 2, "dividend_growth": 0.1, "cost_of_equity": 0.1}),
    (ev_ebitda, {"forecast_ebitda": -10, "target_ev_ebitda": 10, "shares": 10, **ZERO_BRIDGE}),
    (ev_revenue, {"forecast_revenue": 0, "target_ev_revenue": 3, "shares": 10, **ZERO_BRIDGE}),
    (residual_income, {"book_equity": -100, "shares": 10, "return_on_equity": 0.1,
                       "payout_ratio": 0.5, "cost_of_equity": 0.1, "terminal_growth": 0, "forecast_years": 2}),
    (reit_affo, {"forecast_affo": -10, "shares": 10, "target_p_affo": 10}),
])
def test_invalid_earnings_equity_discount_and_multiple_inputs(module, inputs):
    result = module.calculate(inputs)
    assert result["status"] == "invalid_input", result
    json.dumps(result, allow_nan=False)


def test_missing_input_alternatives_do_not_require_irrelevant_input_paths():
    assert missing_inputs("pe", {"forward_eps": 5, "target_pe": 15}) == []
    assert missing_inputs("fcff", {**DCF, "fcff": None, "projected_fcff": [-20, 30]}) == []
    assert "net_borrowing" in missing_inputs("fcfe", {**DCF, "fcfe": None, "net_income": 150,
                                                       "depreciation_and_amortization": 20, "capex": 40, "change_nwc": 30})
    assert len(MODEL_FUNCTIONS) == 11
    assert all(required_inputs(model_id) for model_id in MODEL_FUNCTIONS)


def test_reverse_dcf_recovers_hand_calculated_growth_and_signed_bracket_endpoints():
    # At10% growth EV1200; equity(1200-500)=700; price70 on10 shares.
    result = reverse_dcf({**DCF, **ZERO_BRIDGE, "debt": 500}, 70)
    assert result["status"] == "valid", result
    assert result["implied_growth"] == pytest.approx(0.1, abs=1e-8)
    assert result["solver"]["converged"]
    assert result["solved_variable"] == "cash_flow_growth"
    assert "cash_flow_growth" not in result["held_constants"]


def test_reverse_dcf_handles_negative_starting_cash_flow_and_missing_comparison_price():
    # Negative100 constant CF EV-1000 plus nonoperating asset2000 =>equity1000.
    result = reverse_dcf({**DCF, **ZERO_BRIDGE, "fcff": -100, "other_nonoperating_assets": 2000}, 100)
    assert result["status"] == "valid", result
    assert result["implied_growth"] == pytest.approx(0, abs=1e-8)
    assert reverse_dcf(DCF)["status"] == "unavailable"
    assert reverse_dcf(DCF, -1)["status"] == "invalid_input"


def test_reverse_solver_detects_missing_brackets_multiple_roots_and_flat_degeneracy():
    assert reverse_dcf(DCF, 1e9)["status"] == "unavailable"
    assert solve_bounded(lambda x: (x - 0.1) * (x - 0.3), (-0.5, 1))["status"] == "ambiguous"
    flat = solve_bounded(lambda x: 0, (-0.5, 1))
    assert flat["status"] == "ambiguous"
    assert "flat" in flat["reason"]
    assert solve_bounded(lambda x: -x + 0.1234)["roots"][0] == pytest.approx(0.1234, abs=1e-8)
    assert reverse_dcf({**DCF, "projected_fcff": [100, 100]}, 91.3)["status"] == "invalid_input"


def test_reverse_growth_solver_uses_actual_forecast_path_and_validates_currency():
    inputs = {**DCF, **ZERO_BRIDGE, "revenue": 1000, "revenue_growth": 0.1,
              "operating_margin": 0.2, "tax_rate": 0.25,
              "capex_ratio": 0.05, "da_ratio": 0.03, "nwc_ratio": 0.1}
    # Explicit startingFCFF takes precedence, so solve cashflowgrowth despite drivers.
    assert reverse_dcf(inputs, 120)["implied_growth"] == pytest.approx(0.1, abs=1e-8)
    driver = reverse_dcf({**inputs, "fcff": None}, float(Fraction(18656, 121)))
    assert driver["solved_variable"] == "revenue_growth"
    assert driver["implied_growth"] == pytest.approx(0.1, abs=1e-8)
    assert reverse_dcf({**DCF, "market_currency": "EUR"}, 91.3)["status"] == "invalid_input"


@pytest.mark.parametrize("options", [{"grid_points": 10000}, {"grid_points": 20.5},
                                      {"max_iterations": 10000}, {"max_iterations": True},
                                      {"value_tolerance": float("nan")}, {"variable_tolerance": 0}])
def test_reverse_solver_rejects_unbounded_work_or_invalid_convergence_settings(options):
    from app.valuation.validation import ValuationInputError
    with pytest.raises(ValuationInputError):
        solve_bounded(lambda x: x, **options)


def test_residual_income_declining_terminal_book_discloses_return_of_capital():
    result = residual_income.calculate({"book_equity": 1000, "shares": 10, "return_on_equity": 0.12,
                                       "payout_ratio": 1, "cost_of_equity": 0.1,
                                       "terminal_growth": -0.02, "forecast_years": 1,
                                       "terminal_roe": None})
    # RI1=20, continuingRI20 / (.1-(-.02)) =>166.6667 at year1.
    valid(result, (Fraction(1000) + Fraction(200, 11) + Fraction(5000, 33)) / 10)
    assert result["details"]["terminal_payout_ratio"] > 1
    assert any("return of capital" in warning for warning in result["warnings"])
