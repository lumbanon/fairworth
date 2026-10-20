"""Synthetic, offline accounting examples with independently stated expectations."""

import copy
import json
from pathlib import Path

import pytest

from app.services.metrics import calculate_metrics
from app.services.normalization import extract_observations, normalize_company_facts


def observation(value, start="2024-01-01", end="2024-12-31", *, fy=2024, fp="FY", form="10-K", filed="2025-02-15", accn="0000000001-25-000001", frame=None):
    result = {"val": value, "end": end, "fy": fy, "fp": fp, "form": form, "filed": filed, "accn": accn}
    if start is not None:
        result["start"] = start
    if frame is not None:
        result["frame"] = frame
    return result


def payload(concepts):
    return {"cik": 1, "entityName": "Synthetic fixture", "facts": {"us-gaap": {
        concept: {"units": {unit: records}}
        for concept, (unit, records) in concepts.items()
    }}}


def cash_flow_payload():
    periods = [
        ("2024-03-31", "Q1", "10-Q", "2024-05-01", "0000000001-24-000001", 100, 20),
        ("2024-06-30", "Q2", "10-Q", "2024-08-01", "0000000001-24-000002", 220, 45),
        ("2024-09-30", "Q3", "10-Q", "2024-11-01", "0000000001-24-000003", 370, 80),
        ("2024-12-31", "FY", "10-K", "2025-02-15", "0000000001-25-000001", 550, 120),
    ]
    facts = {}
    for concept, index in (("NetCashProvidedByUsedInOperatingActivities", 5), ("PaymentsToAcquirePropertyPlantAndEquipment", 6)):
        facts[concept] = ("USD", [
            observation(row[index], end=row[0], fp=row[1], form=row[2], filed=row[3], accn=row[4])
            for row in periods
        ])
    return payload(facts)


def period_by_fp(result, fp):
    return next(period for period in result["quarterly"] if period["fiscal_period"] == fp)


def test_absolute_units_and_comparative_fiscal_years():
    raw = json.loads((Path(__file__).parent / "fixtures" / "companyfacts_minimal.json").read_text())
    result = normalize_company_facts(raw)
    current, previous = result["annual"]
    assert current["fiscal_year"] == 2025
    assert current["start_date"] == "2024-07-01"
    assert current["metrics"]["revenue"] == 1_200_000_000
    assert current["metrics"]["diluted_eps"] == 2.5
    assert current["metrics"]["weighted_average_diluted_shares"] == 50_000_000
    assert previous["fiscal_year"] == 2024  # Comparative fy=2025 is not its fiscal year.
    assert previous["metrics"]["revenue"] == 1_100_000_000
    assert previous["provenance"]["revenue"][0]["accn"] == "0000000001-25-000001"
    assert any(warning["code"] == "restated_fact" for warning in result["warnings"])
    assert result["source_references"][0]["url"].startswith("https://www.sec.gov/Archives/edgar/data/1/")


def test_negative_earnings_and_cash_flow_are_legitimate():
    raw = payload({
        "Revenues": ("USD", [observation(200)]),
        "NetIncomeLoss": ("USD", [observation(-20)]),
        "NetCashProvidedByUsedInOperatingActivities": ("USD", [observation(-10)]),
        "PaymentsToAcquirePropertyPlantAndEquipment": ("USD", [observation(30)]),
    })
    result = normalize_company_facts(raw)
    values = result["annual"][0]["metrics"]
    assert values["net_income"] == -20
    assert values["operating_cash_flow"] == -10
    assert values["free_cash_flow"] == -40


def test_preserves_all_raw_observations_and_unknown_concepts():
    raw = payload({"Revenues": ("EUR", [observation(100)]), "UnmappedReportedMetric": ("pure", [observation(3)])})
    raw["facts"]["issuer-custom"] = {"CustomMetric": {"units": {"USD": [observation(20)]}}}
    observations = extract_observations(raw)
    assert len(observations) == 3
    assert observations[0]["metric"] == "revenue"
    assert observations[1]["metric"] is None
    assert observations[2]["taxonomy"] == "issuer-custom"
    assert all("accn" in item and "frame" in item for item in observations)
    normalized = normalize_company_facts(raw)
    assert normalized["annual"] == []
    assert any(item["code"] == "incompatible_currency" for item in normalized["warnings"])


def test_selects_annual_and_standalone_quarter_separately():
    raw = payload({"Revenues": ("USD", [
        observation(1000),
        observation(300, "2024-04-01", "2024-06-30", fp="Q2", form="10-Q", filed="2024-08-01", accn="0000000001-24-000002"),
    ])})
    result = normalize_company_facts(raw)
    assert result["annual"][0]["metrics"]["revenue"] == 1000
    assert period_by_fp(result, "Q2")["metrics"]["revenue"] == 300


def test_native_direct_q2_without_a_completed_annual_year():
    raw = payload({"NetIncomeLoss": ("USD", [
        observation(20, "2025-04-01", "2025-06-30", fy=2025, fp="Q2", form="10-Q", filed="2025-08-01"),
    ])})
    result = normalize_company_facts(raw)
    assert len(result["quarterly"]) == 1
    assert result["quarterly"][0]["fiscal_period"] == "Q2"
    assert result["quarterly"][0]["fiscal_year"] == 2025


def test_comparative_quarter_in_later_native_filing_is_not_mislabeled():
    raw = payload({
        "Revenues": ("USD", [
            observation(100, "2024-04-01", "2024-06-30", fp="Q3", form="10-Q", filed="2024-11-01", accn="0000000001-24-000003"),
        ]),
        "UnmappedNativeQuarterAmount": ("USD", [
            observation(500, "2024-07-01", "2024-09-30", fp="Q3", form="10-Q", filed="2024-11-01", accn="0000000001-24-000003"),
        ]),
    })
    result = normalize_company_facts(raw)
    assert result["quarterly"] == []
    assert any(item["code"] == "ambiguous_fiscal_period" for item in result["warnings"])


def test_later_comparative_value_keeps_original_native_quarter_identity():
    raw = payload({
        "Revenues": ("USD", [
            observation(100, "2024-04-01", "2024-06-30", fp="Q2", form="10-Q", filed="2024-08-01", accn="0000000001-24-000002"),
            observation(120, "2024-04-01", "2024-06-30", fp="Q3", form="10-Q", filed="2024-11-01", accn="0000000001-24-000003"),
        ]),
        "UnmappedNativeQuarterAmount": ("USD", [
            observation(500, "2024-07-01", "2024-09-30", fp="Q3", form="10-Q", filed="2024-11-01", accn="0000000001-24-000003"),
        ]),
    })
    result = normalize_company_facts(raw)
    assert len(result["quarterly"]) == 1
    assert result["quarterly"][0]["fiscal_period"] == "Q2"
    assert result["quarterly"][0]["metrics"]["revenue"] == 120


def test_native_conflicting_quarter_labels_remain_ambiguous():
    raw = payload({"Revenues": ("USD", [
        observation(100, "2024-04-01", "2024-06-30", fp="Q2", form="10-Q", filed="2024-08-01"),
        observation(100, "2024-04-01", "2024-06-30", fp="Q3", form="10-Q", filed="2024-08-01"),
    ])})
    result = normalize_company_facts(raw)
    assert result["quarterly"] == []
    assert any(item["code"] == "ambiguous_fiscal_period" for item in result["warnings"])


def test_ytd_cash_flow_and_q4_are_not_double_counted():
    result = normalize_company_facts(cash_flow_payload())
    assert result["annual"][0]["metrics"]["free_cash_flow"] == 430
    expected = {"Q1": (100, 20, 80), "Q2": (120, 25, 95), "Q3": (150, 35, 115), "Q4": (180, 40, 140)}
    for fp, (ocf, capex, fcf) in expected.items():
        values = period_by_fp(result, fp)["metrics"]
        assert (values["operating_cash_flow"], values["capital_expenditures"], values["free_cash_flow"]) == (ocf, capex, fcf)
    assert sum(period["metrics"]["free_cash_flow"] for period in result["quarterly"]) == 430
    assert period_by_fp(result, "Q2")["start_date"] == "2024-04-01"
    assert {item["coefficient"] for item in period_by_fp(result, "Q2")["provenance"]["operating_cash_flow"]} == {1, -1}


def test_eps_and_weighted_shares_are_never_differenced():
    raw = cash_flow_payload()
    for concept, unit, values in (("EarningsPerShareDiluted", "USD/shares", (1.1, 2.3)), ("WeightedAverageNumberOfDilutedSharesOutstanding", "shares", (100, 105))):
        raw["facts"]["us-gaap"][concept] = {"units": {unit: [
            observation(values[0], end="2024-03-31", fp="Q1", form="10-Q", filed="2024-05-01", accn="0000000001-24-000001"),
            observation(values[1], end="2024-06-30", fp="Q2", form="10-Q", filed="2024-08-01", accn="0000000001-24-000002"),
        ]}}
    result = normalize_company_facts(raw)
    q1, q2 = period_by_fp(result, "Q1"), period_by_fp(result, "Q2")
    assert q1["metrics"]["diluted_eps"] == 1.1
    assert q2["metrics"]["diluted_eps"] is None
    assert q2["metrics"]["weighted_average_diluted_shares"] is None


def test_noncalendar_fiscal_quarters_follow_fiscal_start_not_frames():
    raw = payload({"NetCashProvidedByUsedInOperatingActivities": ("USD", [
        observation(50, "2024-10-01", "2024-12-31", fy=2025, fp="Q1", form="10-Q", filed="2025-02-01", frame="CY2024Q4"),
        observation(250, "2024-10-01", "2025-09-30", fy=2025, filed="2025-11-15", frame="CY2025"),
    ])})
    result = normalize_company_facts(raw)
    assert result["annual"][0]["fiscal_year"] == 2025
    assert period_by_fp(result, "Q1")["fiscal_year"] == 2025
    assert period_by_fp(result, "Q1")["end_date"] == "2024-12-31"


def test_missing_preceding_ytd_does_not_fabricate_q4():
    raw = payload({"NetCashProvidedByUsedInOperatingActivities": ("USD", [observation(550)])})
    result = normalize_company_facts(raw)
    assert result["quarterly"] == []
    assert any(item["code"] == "missing_aligned_ytd_period" for item in result["warnings"])


def test_amended_annual_cannot_mix_with_unrevised_nine_month_basis_for_q4():
    raw = cash_flow_payload()
    raw["facts"]["us-gaap"]["NetCashProvidedByUsedInOperatingActivities"]["units"]["USD"].append(
        observation(570, form="10-K/A", filed="2025-03-01", accn="0000000001-25-000099")
    )
    result = normalize_company_facts(raw)
    assert result["annual"][0]["metrics"]["operating_cash_flow"] == 570
    assert period_by_fp(result, "Q4")["metrics"]["operating_cash_flow"] is None
    assert any(item["code"] == "incompatible_ytd_basis" for item in period_by_fp(result, "Q4")["warnings"])


def test_q4_can_use_same_amended_filing_comparative_basis():
    raw = cash_flow_payload()
    for concept, annual, nine_month in (("NetCashProvidedByUsedInOperatingActivities", 570, 390), ("PaymentsToAcquirePropertyPlantAndEquipment", 130, 90)):
        raw["facts"]["us-gaap"][concept]["units"]["USD"].extend([
            observation(annual, form="10-K/A", filed="2025-03-01", accn="0000000001-25-000099"),
            observation(nine_month, end="2024-09-30", form="10-K/A", filed="2025-03-01", accn="0000000001-25-000099"),
        ])
    result = normalize_company_facts(raw)
    q4 = period_by_fp(result, "Q4")
    assert q4["metrics"]["operating_cash_flow"] == 180
    assert q4["metrics"]["capital_expenditures"] == 40
    assert q4["metrics"]["free_cash_flow"] == 140


def test_same_filing_restated_ytd_pair_is_compatible():
    raw = cash_flow_payload()
    for concept, val in (("NetCashProvidedByUsedInOperatingActivities", 110), ("PaymentsToAcquirePropertyPlantAndEquipment", 25)):
        raw["facts"]["us-gaap"][concept]["units"]["USD"].append(
            observation(val, end="2024-03-31", fp="Q2", form="10-Q", filed="2024-08-01", accn="0000000001-24-000002")
        )
    result = normalize_company_facts(raw)
    q2 = period_by_fp(result, "Q2")
    assert q2["metrics"]["operating_cash_flow"] == 110
    assert q2["metrics"]["capital_expenditures"] == 20
    assert q2["metrics"]["free_cash_flow"] == 90


def test_incompatible_restated_ytd_pair_is_not_subtracted():
    raw = cash_flow_payload()
    raw["facts"]["us-gaap"]["NetCashProvidedByUsedInOperatingActivities"]["units"]["USD"].append(
        observation(140, end="2024-03-31", fp="Q1", form="10-Q/A", filed="2024-08-10", accn="0000000001-24-000099")
    )
    result = normalize_company_facts(raw)
    q2 = period_by_fp(result, "Q2")
    assert q2["metrics"]["operating_cash_flow"] is None
    assert q2["metrics"]["free_cash_flow"] is None
    assert any(item["code"] == "incompatible_ytd_basis" for item in q2["warnings"])


def test_missing_capex_never_substitutes_zero():
    raw = payload({"NetCashProvidedByUsedInOperatingActivities": ("USD", [observation(100)])})
    result = normalize_company_facts(raw)
    assert result["annual"][0]["metrics"]["capital_expenditures"] is None
    assert result["annual"][0]["metrics"]["free_cash_flow"] is None
    assert any(item["code"] == "missing_capex" for item in result["warnings"])


def test_differing_duration_starts_cannot_make_fcf():
    raw = payload({
        "NetCashProvidedByUsedInOperatingActivities": ("USD", [observation(100)]),
        "PaymentsToAcquirePropertyPlantAndEquipment": ("USD", [observation(20, "2024-01-03")]),
    })
    result = normalize_company_facts(raw)
    assert all(period["metrics"]["free_cash_flow"] is None for period in result["annual"])


def test_annual_balance_sheet_aligns_exact_period_end(raw_facts):
    raw = copy.deepcopy(raw_facts)
    raw["facts"]["us-gaap"]["Assets"]["units"]["USD"].append(observation(999999, None, "2025-01-15"))
    result = normalize_company_facts(raw)
    assert result["annual"][0]["metrics"]["total_assets"] == 1500
    assert result["annual"][0]["metrics"]["shares_outstanding"] is None


def test_debt_components_are_complete_and_not_double_counted():
    base = {"Revenues": ("USD", [observation(1000)]),
            "DebtCurrent": ("USD", [observation(40, None)]),
            "LongTermDebtCurrent": ("USD", [observation(15, None)]),
            "LongTermDebtNoncurrent": ("USD", [observation(100, None)])}
    result = normalize_company_facts(payload(base))
    # DebtCurrent also permits capital leases; its conventional debt scope is
    # unverified. Preserve it separately instead of calling the sum total debt.
    assert result["annual"][0]["metrics"]["total_debt"] is None
    assert result["annual"][0]["metrics"]["current_debt_including_lease_obligations"] == 40
    base.pop("DebtCurrent")
    base["ShortTermBorrowings"] = ("USD", [observation(25, None)])
    result = normalize_company_facts(payload(base))
    assert result["annual"][0]["metrics"]["total_debt"] == 140
    base.pop("LongTermDebtCurrent")
    result = normalize_company_facts(payload(base))
    assert result["annual"][0]["metrics"]["total_debt"] is None


def test_total_revenue_precedes_contract_subtotal_and_alias_conflict_is_clear():
    result = normalize_company_facts(payload({
        "Revenues": ("USD", [observation(1000)]),
        "RevenueFromContractWithCustomerExcludingAssessedTax": ("USD", [observation(400)]),
        "CostOfRevenue": ("USD", [observation(600)]),
    }))
    annual = result["annual"][0]
    assert annual["metrics"]["revenue"] == 1000
    assert annual["provenance"]["revenue"][0]["concept"] == "Revenues"
    assert annual["metrics"]["gross_profit"] == 400
    assert calculate_metrics(result["annual"])["periods"][0]["metrics"]["gross_margin"] == pytest.approx(0.4)
    assert any(item["field"] == "revenue" and item["code"] == "conflicting_concept_aliases" for item in result["warnings"])


def test_nci_inclusive_facts_do_not_substitute_parent_earnings_or_equity():
    raw = payload({
        "Revenues": ("USD", [observation(1000)]),
        "ProfitLoss": ("USD", [observation(200)]),
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": ("USD", [observation(1000, None)]),
    })
    result = normalize_company_facts(raw)
    assert result["annual"][0]["metrics"]["net_income"] is None
    assert result["annual"][0]["metrics"]["shareholders_equity"] is None
    originals = extract_observations(raw)
    assert {item["concept"]: item["value"] for item in originals}["ProfitLoss"] == 200
    assert {item["field"] for item in result["warnings"] if item["code"] == "unverified_ownership_basis"} == {"net_income", "shareholders_equity"}


def test_parent_specific_tags_are_used_when_nci_inclusive_tags_also_exist():
    result = normalize_company_facts(payload({
        "NetIncomeLoss": ("USD", [observation(150)]),
        "ProfitLoss": ("USD", [observation(200)]),
        "StockholdersEquity": ("USD", [observation(800, None)]),
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": ("USD", [observation(1000, None)]),
    }))
    assert result["annual"][0]["metrics"]["net_income"] == 150
    assert result["annual"][0]["metrics"]["shareholders_equity"] == 800
    assert not any(item["code"] == "unverified_ownership_basis" for item in result["warnings"])


def test_invalid_units_duplicates_and_conflicts_are_warned():
    raw = payload({"Revenues": ("USD", [observation(100), observation(100), observation(200)]),
                   "EarningsPerShareDiluted": ("USD", [observation(2.5)])})
    assert len(extract_observations(raw)) == 4
    result = normalize_company_facts(raw)
    assert result["annual"][0]["metrics"]["revenue"] is None
    assert result["annual"][0]["metrics"]["diluted_eps"] is None
    assert {item["code"] for item in result["warnings"]} >= {"ambiguous_fact", "duplicate_observation", "inconsistent_units"}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), None, "100", True])
def test_invalid_numerical_facts_never_reach_normalized_financials(value):
    result = normalize_company_facts(payload({"Revenues": ("USD", [observation(value)])}))
    assert result["annual"] == []
    assert any(item["code"] == "invalid_value" for item in result["warnings"])


def test_invalid_negative_assets_and_capex_are_excluded():
    result = normalize_company_facts(payload({"Revenues": ("USD", [observation(100)]),
        "Assets": ("USD", [observation(-100, None)]),
        "PaymentsToAcquirePropertyPlantAndEquipment": ("USD", [observation(-20)])}))
    assert result["annual"][0]["metrics"]["total_assets"] is None
    assert result["annual"][0]["metrics"]["capital_expenditures"] is None
    assert any(item["code"] == "invalid_negative_value" for item in result["warnings"])


def test_mismatched_balance_sheet_is_reported(raw_facts):
    raw = copy.deepcopy(raw_facts)
    raw["facts"]["us-gaap"]["Assets"]["units"]["USD"][-1]["val"] = 2000
    result = normalize_company_facts(raw)
    assert any(item["code"] == "inconsistent_balance_sheet" for item in result["warnings"])


def test_delayed_comparative_only_context_does_not_invent_fiscal_year():
    raw = payload({"Revenues": ("USD", [observation(100, filed="2026-02-15", fy=2025)])})
    result = normalize_company_facts(raw)
    assert result["annual"] == []
    assert any(item["code"] == "ambiguous_fiscal_period" for item in result["warnings"])


@pytest.mark.parametrize("raw", [None, [], {}, {"facts": None}, {"facts": []}, {"facts": {"us-gaap": None}}, {"facts": {"us-gaap": {"Revenues": {"units": None}}}}, {"facts": {"us-gaap": {"Revenues": {"units": {"USD": None}}}}}])
def test_malformed_or_missing_nested_concepts_remain_structured(raw):
    assert extract_observations(raw) == []
    result = normalize_company_facts(raw)
    assert result["annual"] == []
    assert result["quarterly"] == []
    assert any(item["code"] == "missing_financial_data" for item in result["warnings"])


def test_missing_accn_and_invalid_periods_are_not_trusted():
    records = [observation(100, accn=None), observation(200, filed="2024-01-01")]
    result = normalize_company_facts(payload({"Revenues": ("USD", records)}))
    assert result["annual"] == []
    assert {item["code"] for item in result["warnings"]} >= {"invalid_source_metadata", "unexpected_reporting_period"}


def test_derived_cash_flow_overflow_is_excluded():
    result = normalize_company_facts(payload({
        "NetCashProvidedByUsedInOperatingActivities": ("USD", [observation(-1e308)]),
        "PaymentsToAcquirePropertyPlantAndEquipment": ("USD", [observation(1e308)]),
    }))
    assert result["annual"][0]["metrics"]["free_cash_flow"] is None
    assert any(item["code"] == "invalid_derived_value" for item in result["warnings"])


def test_financial_ratios_growth_and_average_equity(raw_facts):
    raw = copy.deepcopy(raw_facts)
    raw["facts"]["us-gaap"]["DebtLongtermAndShorttermCombinedAmount"] = {"units": {"USD": [observation(150, None)]}}
    result = normalize_company_facts(raw)
    calculated = calculate_metrics(result["annual"])
    values = calculated["periods"][0]["metrics"]
    assert values["revenue_growth"] == pytest.approx(0.25)
    assert values["net_profit_margin"] == pytest.approx(0.1)
    assert values["free_cash_flow_margin"] == pytest.approx(0.1)
    assert values["return_on_equity"] == pytest.approx(100 / ((720 + 900) / 2))
    assert values["debt_to_equity"] == pytest.approx(150 / 900)
    assert values["net_debt"] == -50
    assert values["historical_eps_growth"] == pytest.approx(0.25)
    assert values["historical_free_cash_flow_growth"] == pytest.approx(0.25)


def test_growth_rejects_missing_negative_and_noncomparable_bases():
    periods = [
        {"fiscal_year": 2024, "fiscal_period": "FY", "start_date": "2024-01-01", "end_date": "2024-12-31", "metrics": {"revenue": 100, "diluted_eps": 1, "free_cash_flow": 10}},
        {"fiscal_year": 2023, "fiscal_period": "FY", "start_date": "2023-01-01", "end_date": "2023-12-31", "metrics": {"revenue": -100, "diluted_eps": -1, "free_cash_flow": 0}},
    ]
    result = calculate_metrics(periods)
    assert result["periods"][0]["metrics"]["revenue_growth"] is None
    assert result["periods"][0]["metrics"]["historical_eps_growth"] is None
    periods[1]["start_date"] = "2023-07-01"  # Six-month transition year is not comparable.
    periods[1]["metrics"]["revenue"] = 50
    assert calculate_metrics(periods)["periods"][0]["metrics"]["revenue_growth"] is None


def test_quarterly_growth_compares_same_fiscal_quarter_and_not_previous_quarter():
    periods = [
        {"fiscal_year": 2025, "fiscal_period": "Q2", "start_date": "2025-04-01", "end_date": "2025-06-30", "metrics": {"revenue": 120}},
        {"fiscal_year": 2025, "fiscal_period": "Q1", "start_date": "2025-01-01", "end_date": "2025-03-31", "metrics": {"revenue": 1000}},
        {"fiscal_year": 2024, "fiscal_period": "Q2", "start_date": "2024-04-01", "end_date": "2024-06-30", "metrics": {"revenue": 100}},
    ]
    ratios = calculate_metrics(periods)["periods"][0]["metrics"]
    assert ratios["revenue_growth"] == pytest.approx(0.2)
    assert ratios["return_on_equity"] is None


def test_roe_requires_actual_consecutive_equity_endpoints():
    periods = [
        {"fiscal_year": 2024, "fiscal_period": "FY", "start_date": "2024-01-01", "end_date": "2024-12-31", "metrics": {"net_income": 20, "shareholders_equity": 100}},
        {"fiscal_year": 2023, "fiscal_period": "FY", "start_date": "2023-01-01", "end_date": "2023-12-29", "metrics": {"net_income": 10, "shareholders_equity": 80}},
    ]
    result = calculate_metrics(periods)
    assert result["periods"][0]["metrics"]["return_on_equity"] is None
    assert any(item["field"] == "return_on_equity" and item["code"] == "unavailable_average_equity" for item in result["warnings"])
    periods[1]["end_date"] = "2023-12-31"
    assert calculate_metrics(periods)["periods"][0]["metrics"]["return_on_equity"] == pytest.approx(20 / 90)


def test_roe_supports_consecutive_noncalendar_52_week_years():
    periods = [
        {"fiscal_year": 2025, "fiscal_period": "FY", "start_date": "2024-09-28", "end_date": "2025-09-26", "metrics": {"net_income": 20, "shareholders_equity": 100}},
        {"fiscal_year": 2024, "fiscal_period": "FY", "start_date": "2023-09-30", "end_date": "2024-09-27", "metrics": {"net_income": 10, "shareholders_equity": 80}},
    ]
    assert calculate_metrics(periods)["periods"][0]["metrics"]["return_on_equity"] == pytest.approx(20 / 90)


def test_reported_productive_asset_capex_retains_scope_and_fcf_provenance():
    result = normalize_company_facts(payload({
        'NetCashProvidedByUsedInOperatingActivities': ('USD',[observation(100)]),
        'PaymentsToAcquireProductiveAssets': ('USD',[observation(20)]),
    }))
    period = result['annual'][0]
    assert period['metrics']['capital_expenditures'] == 20
    assert period['metrics']['free_cash_flow'] == 80
    assert any(warning['code']=='capital_expenditure_scope' for warning in result['warnings'])
    assert {source['concept']:source['coefficient'] for source in period['provenance']['free_cash_flow']} == {
        'NetCashProvidedByUsedInOperatingActivities':1, 'PaymentsToAcquireProductiveAssets':-1}


def test_commercial_paper_and_reported_total_debt_do_not_double_count():
    concepts = {
        'Revenues':('USD',[observation(100)]),
        'CommercialPaper':('USD',[observation(5,None)]),
        'LongTermDebtCurrent':('USD',[observation(10,None)]),
        'LongTermDebtNoncurrent':('USD',[observation(80,None)]),
    }
    # A commercial-paper subtotal does not establish complete short borrowing.
    assert normalize_company_facts(payload(concepts))['annual'][0]['metrics']['total_debt'] is None
    concepts['DebtLongtermAndShorttermCombinedAmount'] = ('USD',[observation(96,None)])
    period = normalize_company_facts(payload(concepts))['annual'][0]
    assert period['metrics']['total_debt'] == 96
    assert len(period['provenance']['total_debt']) == 1


def test_liability_derivation_uses_total_equity_including_nci_and_same_filing():
    concepts = {
        'Revenues':('USD',[observation(100)]),
        'LiabilitiesAndStockholdersEquity':('USD',[observation(1000,None)]),
        'StockholdersEquity':('USD',[observation(250,None)]),
        'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest':('USD',[observation(300,None)]),
    }
    period = normalize_company_facts(payload(concepts))['annual'][0]
    assert period['metrics']['shareholders_equity'] == 250
    assert period['metrics']['total_liabilities'] == 700
    concepts.pop('StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest')
    assert normalize_company_facts(payload(concepts))['annual'][0]['metrics']['total_liabilities'] is None


def test_new_fiscal_year_quarter_follows_completed_annual_boundary():
    raw = payload({'Revenues':('USD',[
        observation(1000,'2025-06-01','2026-05-31',fy=2026,filed='2026-06-22',accn='0000000001-26-000001'),
        observation(250,'2026-06-01','2026-08-31',fy=2026,fp='Q1',form='10-Q',filed='2026-09-11',accn='0000000001-26-000002'),
    ])})
    period = normalize_company_facts(raw)['quarterly'][0]
    assert (period['fiscal_year'],period['fiscal_period']) == (2027,'Q1')
    assert period['metrics']['revenue'] == 250
    assert period['provenance']['revenue'][0]['fy'] == 2026


def test_derived_quarter_fcf_coefficients_compose_ytd_and_capex_subtraction():
    period = period_by_fp(normalize_company_facts(cash_flow_payload()),'Q2')
    terms = {(source['concept'],source['start'],source['end'],source['value'],source['coefficient']) for source in period['provenance']['free_cash_flow']}
    assert sum(value*coefficient for _,_,_,value,coefficient in terms) == 95
