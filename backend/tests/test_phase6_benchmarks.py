"""Independent Decimal financial benchmarks; all inputs are explicitly synthetic.

Expected cash-flow tables and bridges below are computed without calling any
valuation helper. They are not asserted to be issuer forecasts or market facts.
"""
from decimal import Decimal, localcontext

import pytest

from app.valuation.models import fcfe_dcf, fcff_dcf


def D(value):
    return Decimal(str(value))


def test_faded_fcff_independent_decimal_table_and_complete_equity_bridge():
    values = {"fcff": 375_000_000, "cash_flow_growth": 0.12, "growth_fade_to_terminal": True,
              "wacc": 0.095, "terminal_growth": 0.025, "forecast_years": 5, "shares": 80_000_000,
              "debt": 250_000_000, "cash": 80_000_000, "preferred_equity": 12_000_000,
              "minority_interest": 8_000_000, "other_nonoperating_assets": 15_000_000}
    with localcontext() as context:
        context.prec = 45
        flow, present, rows = D(375_000_000), D(0), []
        for year in range(1, 6):
            rate = D("0.12") + (D("0.025") - D("0.12")) * D(year - 1) / D(4)
            flow *= 1 + rate
            present += flow / D("1.095") ** year
            rows.append(flow)
        terminal = flow * D("1.025") / D("0.07") / D("1.095") ** 5
        enterprise = present + terminal
        equity = enterprise - D(250_000_000) + D(80_000_000) - D(12_000_000) - D(8_000_000) + D(15_000_000)
        expected = equity / D(80_000_000)
    actual = fcff_dcf.calculate(values)
    assert actual["status"] == "valid"
    assert actual["fair_value"] == pytest.approx(float(expected), rel=1e-12)
    assert [row["cash_flow"] for row in actual["details"]["projection"]] == pytest.approx([float(row) for row in rows])
    assert actual["details"]["enterprise_value"] == pytest.approx(float(enterprise))
    assert actual["details"]["equity_value"] == pytest.approx(float(equity))


def test_explicit_fcfe_losses_recovery_and_terminal_have_no_second_debt_bridge():
    values = {"projected_fcfe": [-25, 50, 90, 140], "terminal_fcfe": 160,
              "cost_of_equity": 0.105, "terminal_growth": 0.025,
              "forecast_years": 4, "shares": 12,
              "debt": 9_999_999, "cash": 7_777_777, "preferred_equity": 2_222_222}
    with localcontext() as context:
        context.prec = 45
        discounted = sum(D(flow) / D("1.105") ** year for year, flow in enumerate([-25, 50, 90, 140], 1))
        expected = (discounted + D(160) / D("0.08") / D("1.105") ** 4) / D(12)
    actual = fcfe_dcf.calculate(values)
    assert actual["status"] == "valid"
    assert actual["fair_value"] == pytest.approx(float(expected), rel=1e-12)
    assert "enterprise_value" not in actual["details"]
    assert any("negative" in warning for warning in actual["warnings"])


@pytest.mark.parametrize("nwc_ratio", [-0.07, 0, 0.12])
def test_explicit_revenue_dcf_terminal_reinvestment_decimal_benchmark(nwc_ratio):
    values = {"revenue": 900, "projected_revenue": [1000, 1100, 1170, 1220],
              "operating_margin": 0.18, "tax_rate": 0.25, "da_ratio": 0.035,
              "capex_ratio": 0.06, "nwc_ratio": nwc_ratio,
              "wacc": 0.09, "terminal_growth": 0.02, "forecast_years": 4,
              "shares": 15, "debt": 120, "cash": 35, "preferred_equity": 4,
              "minority_interest": 3, "other_nonoperating_assets": 8}
    with localcontext() as context:
        context.prec = 45
        previous, present = D(900), D(0)
        rows = []
        for year, amount in enumerate([1000, 1100, 1170, 1220], 1):
            revenue = D(amount)
            change = (revenue - previous) * D(nwc_ratio)
            flow = revenue * D("0.18") * D("0.75") + revenue * D("0.035") - revenue * D("0.06") - change
            present += flow / D("1.09") ** year
            rows.append((flow, change))
            previous = revenue
        terminal_revenue = D(1220) * D("1.02")
        terminal_flow = terminal_revenue * (D("0.18") * D("0.75") + D("0.035") - D("0.06")) - (terminal_revenue - D(1220)) * D(nwc_ratio)
        ev = present + terminal_flow / D("0.07") / D("1.09") ** 4
        expected = (ev - D(120) + D(35) - D(4) - D(3) + D(8)) / D(15)
    actual = fcff_dcf.calculate(values)
    assert actual["status"] == "valid"
    assert actual["fair_value"] == pytest.approx(float(expected), rel=1e-12)
    assert actual["details"]["terminal_cash_flow"] == pytest.approx(float(terminal_flow))
    for row, (cash_flow, change) in zip(actual["details"]["projection"], rows):
        assert row["cash_flow"] == pytest.approx(float(cash_flow))
        assert row["change_nwc"] == pytest.approx(float(change))
