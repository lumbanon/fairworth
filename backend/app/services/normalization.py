"""Conservative SEC company-facts normalization with observation-level provenance.

SEC companyfacts values already use the declared absolute unit, not statement
presentation scales. A fact's ``fy``/``fp`` describe its filing context and can
therefore differ from a comparative observation's actual fiscal period. Dates,
duration, native filing context, and accession are considered together here.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

NORMALIZATION_VERSION = 4

# Ordered alternatives are never summed. Explicit total revenue takes priority
# over a contract-revenue subtotal; differing aliases produce a quality warning.
# Debt and lease scopes are deliberately separate. DebtCurrent can include
# capital leases, while CommercialPaper does not establish all short borrowing.
METRIC_DEFINITIONS = {
    "revenue": (("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"), "USD", "duration"),
    "cost_of_revenue": (("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"), "USD", "duration"),
    "gross_profit": (("GrossProfit",), "USD", "duration"),
    "operating_income": (("OperatingIncomeLoss",), "USD", "duration"),
    "pretax_income": (("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterest"), "USD", "duration"),
    "income_tax_expense": (("IncomeTaxExpenseBenefit",), "USD", "duration"),
    "net_income": (("NetIncomeLoss",), "USD", "duration"),
    "basic_eps": (("EarningsPerShareBasic",), "USD/shares", "duration"),
    "diluted_eps": (("EarningsPerShareDiluted",), "USD/shares", "duration"),
    "weighted_average_diluted_shares": (("WeightedAverageNumberOfDilutedSharesOutstanding",), "shares", "duration"),
    "weighted_average_basic_shares": (("WeightedAverageNumberOfSharesOutstandingBasic",), "shares", "duration"),
    "cash_and_cash_equivalents": (("CashAndCashEquivalentsAtCarryingValue",), "USD", "instant"),
    "short_term_investments": (("ShortTermInvestments", "MarketableSecuritiesCurrent"), "USD", "instant"),
    "total_current_assets": (("AssetsCurrent",), "USD", "instant"),
    "total_assets": (("Assets",), "USD", "instant"),
    "short_term_debt": (("ShortTermBorrowings",), "USD", "instant"),
    "current_debt_including_lease_obligations": (("DebtCurrent",), "USD", "instant"),
    "commercial_paper": (("CommercialPaper",), "USD", "instant"),
    "current_long_term_debt": (("LongTermDebtCurrent",), "USD", "instant"),
    "long_term_debt": (("LongTermDebtNoncurrent",), "USD", "instant"),
    "long_term_debt_including_current": (("LongTermDebt",), "USD", "instant"),
    "gross_debt_instrument_carrying_amount": (("DebtInstrumentCarryingAmount",), "USD", "instant"),
    "reported_total_debt": (("DebtLongtermAndShorttermCombinedAmount",), "USD", "instant"),
    "long_term_investments": (("LongTermInvestments",), "USD", "instant"),
    "noncurrent_marketable_securities": (("MarketableSecuritiesNoncurrent",), "USD", "instant"),
    "finance_lease_liability": (("FinanceLeaseLiability",), "USD", "instant"),
    "finance_lease_liability_current": (("FinanceLeaseLiabilityCurrent",), "USD", "instant"),
    "finance_lease_liability_noncurrent": (("FinanceLeaseLiabilityNoncurrent",), "USD", "instant"),
    "operating_lease_liability": (("OperatingLeaseLiability",), "USD", "instant"),
    "operating_lease_liability_current": (("OperatingLeaseLiabilityCurrent",), "USD", "instant"),
    "operating_lease_liability_noncurrent": (("OperatingLeaseLiabilityNoncurrent",), "USD", "instant"),
    "total_liabilities": (("Liabilities",), "USD", "instant"),
    "liabilities_and_equity": (("LiabilitiesAndStockholdersEquity",), "USD", "instant"),
    "total_equity_including_noncontrolling_interests": (("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",), "USD", "instant"),
    "shareholders_equity": (("StockholdersEquity",), "USD", "instant"),
    "shares_outstanding": (("EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"), "shares", "instant"),
    "operating_cash_flow": (("NetCashProvidedByUsedInOperatingActivities",), "USD", "duration"),
    "capital_expenditures": (("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"), "USD", "duration"),
    "depreciation_and_amortization": (("DepreciationDepletionAndAmortization", "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment", "DepreciationAndAmortization"), "USD", "duration"),
    "depreciation_expense": (("Depreciation",), "USD", "duration"),
    "intangible_amortization_expense": (("AmortizationOfIntangibleAssets",), "USD", "duration"),
    "minority_interest": (("MinorityInterest",), "USD", "instant"),
    "preferred_stock_value_outstanding": (("PreferredStockValueOutstanding",), "USD", "instant"),
    "preferred_stock_stated_value": (("PreferredStockValue",), "USD", "instant"),
    "accounts_receivable": (("AccountsReceivableNetCurrent",), "USD", "instant"),
    "inventory": (("InventoryNet",), "USD", "instant"),
    "accounts_payable": (("AccountsPayableCurrent",), "USD", "instant"),
    "dividends_paid": (("PaymentsOfDividends", "PaymentsOfDividendsCommonStock"), "USD", "duration"),
    "share_repurchases": (("PaymentsForRepurchaseOfCommonStock",), "USD", "duration"),
    "interest_expense": (("InterestExpense", "InterestExpenseNonoperating"), "USD", "duration"),
    "stock_based_compensation": (("ShareBasedCompensation",), "USD", "duration"),
    "long_term_debt_proceeds": (("ProceedsFromIssuanceOfLongTermDebt",), "USD", "duration"),
    "long_term_debt_repayments": (("RepaymentsOfLongTermDebt",), "USD", "duration"),
    "total_debt_repayments": (("RepaymentsOfDebt",), "USD", "duration"),
    "debt_repayments_maturing_over_three_months": (("RepaymentsOfDebtMaturingInMoreThanThreeMonths",), "USD", "duration"),
    "net_commercial_paper_borrowing": (("ProceedsFromRepaymentsOfCommercialPaper",), "USD", "duration"),
    "change_in_accounts_receivable": (("IncreaseDecreaseInAccountsReceivable",), "USD", "duration"),
    "change_in_inventory": (("IncreaseDecreaseInInventories",), "USD", "duration"),
    "change_in_accounts_payable": (("IncreaseDecreaseInAccountsPayable",), "USD", "duration"),
}
CONCEPT_METRICS = {
    concept: metric for metric, (concepts, _, _) in METRIC_DEFINITIONS.items() for concept in concepts
}
FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A"}
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
NON_ADDITIVE = {"basic_eps", "diluted_eps", "weighted_average_diluted_shares", "weighted_average_basic_shares"}
NON_NEGATIVE = {
    "cash_and_cash_equivalents", "short_term_investments", "total_current_assets", "total_assets",
    "short_term_debt", "current_long_term_debt", "long_term_debt", "total_liabilities",
    "reported_total_debt", "liabilities_and_equity",
    "shares_outstanding", "weighted_average_diluted_shares", "capital_expenditures",
    "dividends_paid", "share_repurchases",
    "weighted_average_basic_shares", "preferred_stock_value_outstanding", "preferred_stock_stated_value",
    "accounts_receivable", "inventory", "accounts_payable",
    "current_debt_including_lease_obligations", "commercial_paper", "long_term_debt_including_current",
    "gross_debt_instrument_carrying_amount", "long_term_investments", "noncurrent_marketable_securities",
    "finance_lease_liability", "finance_lease_liability_current", "finance_lease_liability_noncurrent",
    "operating_lease_liability", "operating_lease_liability_current", "operating_lease_liability_noncurrent",
    "long_term_debt_proceeds", "long_term_debt_repayments", "total_debt_repayments",
    "debt_repayments_maturing_over_three_months",
}


def extract_observations(raw: dict) -> list[dict]:
    """Preserve every reported fact, including unrecognized concepts and units."""
    observations = []
    facts = raw.get("facts") if isinstance(raw, dict) else None
    if not isinstance(facts, dict):
        return observations
    for taxonomy, concepts in facts.items():
        if not isinstance(concepts, dict):
            continue
        for concept, definition in concepts.items():
            if not isinstance(definition, dict):
                continue
            units = definition.get("units")
            if not isinstance(units, dict):
                continue
            for unit, facts in units.items():
                if not isinstance(facts, list):
                    continue
                for fact in facts:
                    if not isinstance(fact, dict):
                        continue
                    observations.append({
                        **fact,
                        "concept": concept,
                        "taxonomy": taxonomy,
                        "unit": unit,
                        "value": fact.get("val"),
                        "start": fact.get("start"),
                        "end": fact.get("end"),
                        "filed": fact.get("filed"),
                        "accn": fact.get("accn"),
                        "form": fact.get("form"),
                        "fy": fact.get("fy"),
                        "fp": fact.get("fp"),
                        "frame": fact.get("frame"),
                        "metric": CONCEPT_METRICS.get(concept) if taxonomy in ("us-gaap", "dei") else None,
                        "source": "sec",
                    })
    return observations


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _length(obs: dict) -> int | None:
    start, end = _day(obs.get("start")), _day(obs.get("end"))
    return (end - start).days + 1 if start is not None and end is not None else None


def _warn(warnings: list, field: str, code: str, message: str) -> None:
    warning = {"field": field, "code": code, "message": message}
    if warning not in warnings:
        warnings.append(warning)


def _cumulative_quarter(length: int | None) -> int | None:
    if length is None:
        return None
    for quarter, low, high in ((1, 60, 120), (2, 150, 210), (3, 240, 300), (4, 335, 395)):
        if low <= length <= high:
            return quarter
    return None


def _period_year(records: list[dict], annual: bool, warnings: list, filing_duration_ends: dict[str, str]) -> int | None:
    eligible = []
    for obs in records:
        filed, end = _day(obs.get("filed")), _day(obs.get("end"))
        length = _length(obs)
        expected = "FY" if annual else f"Q{_cumulative_quarter(length)}"
        if filed is None or end is None or not 0 <= (filed - end).days <= 180:
            continue
        if obs.get("end") != filing_duration_ends.get(obs.get("accn")):
            continue
        matching_fp = obs.get("fp") == expected
        if not annual and _cumulative_quarter(length) == 1:
            matching_fp = obs.get("fp") in ("Q1", "Q2", "Q3")
        if not matching_fp or (annual and obs.get("form") not in ANNUAL_FORMS):
            continue
        if isinstance(obs.get("fy"), int) and 1900 <= obs["fy"] <= 2200:
            eligible.append(obs)
    if not eligible:
        _warn(warnings, "fiscal_period", "ambiguous_fiscal_period", "A reporting period has no identifiable native fiscal-year filing context and was excluded.")
        return None
    first_filed = min(obs["filed"] for obs in eligible)
    years = {obs["fy"] for obs in eligible if obs["filed"] == first_filed}
    if len(years) != 1:
        _warn(warnings, "fiscal_year", "ambiguous_fiscal_year", "Native observations disagree on the fiscal year; the reporting period was excluded.")
        return None
    return years.pop()


def _select(records: list[dict], metric: str, warnings: list, period: str) -> tuple[float | None, list[dict]]:
    candidates = [obs for obs in records if obs["metric"] == metric]
    if not candidates:
        return None, []
    concepts = METRIC_DEFINITIONS[metric][0]
    priority = min(concepts.index(obs["concept"]) for obs in candidates)
    selected_concept = concepts[priority]
    alias_values = set()
    for concept in {obs["concept"] for obs in candidates}:
        concept_records = [obs for obs in candidates if obs["concept"] == concept]
        concept_filed = max(obs.get("filed") or "" for obs in concept_records)
        alias_values.update(obs["value"] for obs in concept_records if (obs.get("filed") or "") == concept_filed)
    if len(alias_values) > 1 and len({obs["concept"] for obs in candidates}) > 1:
        _warn(warnings, metric, "conflicting_concept_aliases", f"{period}: alternative reported concepts differ; {selected_concept} is selected explicitly and other concepts are not added or substituted.")
    candidates = [obs for obs in candidates if concepts.index(obs["concept"]) == priority]
    # Only compare observations of the already selected exact period/unit/tag.
    latest = max(obs.get("filed") or "" for obs in candidates)
    current = [obs for obs in candidates if (obs.get("filed") or "") == latest]
    amendments = [obs for obs in current if (obs.get("form") or "").endswith("/A")]
    if amendments:
        current = amendments
    values = {obs["value"] for obs in current}
    if len(values) != 1:
        _warn(warnings, metric, "ambiguous_fact", f"{period}: conflicting values in the same latest filing context were excluded.")
        return None, []
    value = values.pop()
    if len({obs["value"] for obs in candidates}) > 1:
        _warn(warnings, metric, "restated_fact", f"{period}: a later filing revised this exact reporting period; the latest unambiguous reported value is used.")
    # Equivalent-value observations are retained for cross-filing alignment.
    sources = [obs for obs in candidates if obs["value"] == value]
    sources.sort(key=lambda obs: (obs.get("filed") or "", obs.get("accn") or ""), reverse=True)
    return float(value), sources


def _compatible(sources: list[list[dict]], *, cumulative: bool = False, fiscal_year: int | None = None) -> bool:
    """Require a common filing or unchanged, contemporaneous native contexts."""
    if not sources or any(not group for group in sources):
        return False
    accessions = [set(obs["accn"] for obs in group if obs.get("accn")) for group in sources]
    if set.intersection(*accessions):
        if not cumulative:
            return True
        units = {group[0]["unit"] for group in sources}
        concepts = {(group[0]["taxonomy"], group[0]["concept"]) for group in sources}
        starts = {group[0]["start"] for group in sources}
        return len(units) == len(concepts) == len(starts) == 1
    native_groups = []
    for group in sources:
        native = []
        for obs in group:
            filed, end = _day(obs.get("filed")), _day(obs.get("end"))
            length = _length(obs)
            if (obs.get("form") or "").endswith("/A") or filed is None or end is None:
                continue
            if not 0 <= (filed - end).days <= 150 or obs.get("fy") != fiscal_year:
                continue
            if length is not None:
                quarter = _cumulative_quarter(length)
                expected = "FY" if quarter == 4 else f"Q{quarter}"
                if obs.get("fp") != expected:
                    continue
            native.append(obs)
        if not native:
            return False
        native_groups.append(native)
    if cumulative:
        firsts = [group[0] for group in native_groups]
        return len({(obs["taxonomy"], obs["concept"], obs["unit"], obs["start"]) for obs in firsts}) == 1
    return True


def complete_conventional_debt_provenance(records: list[dict], *, end_date: str | None = None) -> bool:
    """Check SEC debt scope, independently of a caller's numeric reconciliation.

    Old snapshots may contain DebtCurrent (including lease obligations), or a
    commercial-paper subtotal labeled total debt. Retain those original facts,
    but do not reuse that aggregate as complete conventional financial debt.
    This function does not validate user overrides or license provider records.
    """
    if not isinstance(records, list) or not records:
        return False
    groups = defaultdict(list)
    ends = set()
    for record in records:
        if not isinstance(record, dict):
            return False
        value = record.get("value", record.get("val"))
        end, filed = _day(record.get("end")), _day(record.get("filed"))
        if (record.get("taxonomy") != "us-gaap" or record.get("source") != "sec"
                or record.get("unit") != "USD" or record.get("start") is not None
                or record.get("form") not in FORMS or isinstance(record.get("coefficient", 1), bool)
                or record.get("coefficient", 1) != 1
                or isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0 or end is None or filed is None or filed < end
                or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", str(record.get("accn") or ""))):
            return False
        ends.add(record["end"])
        groups[record.get("concept")].append(record)
    if len(ends) != 1 or (end_date is not None and ends != {end_date}):
        return False
    concepts = frozenset(groups)
    allowed = {
        frozenset({"DebtLongtermAndShorttermCombinedAmount"}),
        frozenset({"ShortTermBorrowings", "LongTermDebt"}),
        frozenset({"ShortTermBorrowings", "LongTermDebtCurrent", "LongTermDebtNoncurrent"}),
    }
    if concepts not in allowed:
        return False
    if any(len({record.get("value", record.get("val")) for record in group}) != 1 for group in groups.values()):
        return False
    years = {record.get("fy") for record in records}
    year = next(iter(years)) if len(years) == 1 else None
    return _compatible(list(groups.values()), fiscal_year=year)


def _new_period(start: str, end: str, year: int, fp: str) -> dict:
    return {
        "fiscal_year": year,
        "fiscal_period": fp,
        "start_date": start,
        "end_date": end,
        "currency": "USD",
        "metrics": {**dict.fromkeys(METRIC_DEFINITIONS), "free_cash_flow": None, "total_debt": None},
        "provenance": {},
        "warnings": [],
    }


def _populate(period: dict, durations: list[dict], instants: list[dict]) -> None:
    label = f"FY{period['fiscal_year']} {period['fiscal_period']} ({period['end_date']})"
    for metric, (_, _, kind) in METRIC_DEFINITIONS.items():
        value, provenance = _select(durations if kind == "duration" else instants, metric, period["warnings"], label)
        period["metrics"][metric] = value
        if provenance:
            period["provenance"][metric] = provenance


def _derive_period(period: dict) -> None:
    metrics, sources, warnings = period["metrics"], period["provenance"], period["warnings"]
    label = f"FY{period['fiscal_year']} {period['fiscal_period']} ({period['end_date']})"

    def derive(target: str, components: tuple[str, ...], value: float, coefficients=None) -> None:
        if not math.isfinite(value):
            _warn(warnings, target, "invalid_derived_value", f"{label}: the derived amount is non-finite and was excluded.")
            return
        provenance = [sources.get(component, []) for component in components]
        if _compatible(provenance, fiscal_year=period["fiscal_year"]):
            metrics[target] = value
            signs = coefficients or tuple(1 for _ in components)
            sources[target] = [{**obs, "derivation": target, "component": component,
                                "coefficient": obs.get("coefficient", 1) * sign}
                               for component, group, sign in zip(components, provenance, signs) for obs in group]
        else:
            _warn(warnings, target, "incompatible_source_context", f"{label}: source components could not be aligned to a compatible filing context.")

    ocf, capex = metrics["operating_cash_flow"], metrics["capital_expenditures"]
    if ocf is not None and capex is not None:
        derive("free_cash_flow", ("operating_cash_flow", "capital_expenditures"), ocf - capex, (1, -1))
    elif capex is None:
        _warn(warnings, "free_cash_flow", "missing_capex", f"{label}: capital expenditure data is unavailable; free cash flow cannot be calculated.")
    else:
        _warn(warnings, "free_cash_flow", "missing_operating_cash_flow", f"{label}: operating cash flow data is unavailable; free cash flow cannot be calculated.")

    if metrics["gross_profit"] is None and metrics["revenue"] is not None and metrics["cost_of_revenue"] is not None:
        derive("gross_profit", ("revenue", "cost_of_revenue"), metrics["revenue"] - metrics["cost_of_revenue"], (1, -1))

    if sources.get("capital_expenditures", [{}])[0].get("concept") == "PaymentsToAcquireProductiveAssets":
        _warn(warnings, "capital_expenditures", "capital_expenditure_scope", f"{label}: reported capital expenditures include property, plant, equipment, software, and other intangible assets; the source scope is preserved.")

    if metrics["total_liabilities"] is None and metrics["liabilities_and_equity"] is not None and metrics["total_equity_including_noncontrolling_interests"] is not None:
        liability_value = metrics["liabilities_and_equity"] - metrics["total_equity_including_noncontrolling_interests"]
        if liability_value >= 0:
            derive("total_liabilities", ("liabilities_and_equity", "total_equity_including_noncontrolling_interests"), liability_value, (1, -1))

    # These are scope-matched identities, not financial-debt fallbacks. A
    # reported aggregate always remains the original reported observation.
    conflicting_aggregates = set()
    for target, components in (
        ("long_term_debt_including_current", ("current_long_term_debt", "long_term_debt")),
        ("finance_lease_liability", ("finance_lease_liability_current", "finance_lease_liability_noncurrent")),
        ("operating_lease_liability", ("operating_lease_liability_current", "operating_lease_liability_noncurrent")),
    ):
        if any(metrics[component] is None for component in components):
            continue
        component_sources = [sources.get(component, []) for component in components]
        if not _compatible(component_sources, fiscal_year=period["fiscal_year"]):
            _warn(warnings, target, "incompatible_source_context", f"{label}: aggregate components do not share a compatible filing context; no reconciliation or derivation was applied.")
            continue
        amount = sum(metrics[component] for component in components)
        if metrics[target] is None:
            derive(target, components, amount)
        elif not math.isfinite(amount) or not math.isclose(metrics[target], amount, rel_tol=1e-9, abs_tol=1):
            conflicting_aggregates.add(target)
            _warn(warnings, target, "conflicting_aggregate_components", f"{label}: the reported aggregate differs from its compatible current/noncurrent components; original amounts are retained and the aggregate is not used to derive complete debt.")

    short, long = metrics["short_term_debt"], metrics["long_term_debt_including_current"]
    if metrics["reported_total_debt"] is not None:
        metrics["total_debt"] = metrics["reported_total_debt"]
        sources["total_debt"] = sources["reported_total_debt"]
        if short is not None and long is not None:
            groups = [sources.get("short_term_debt", []), sources.get("long_term_debt_including_current", []),
                      sources.get("reported_total_debt", [])]
            if (_compatible(groups, fiscal_year=period["fiscal_year"])
                    and not math.isclose(metrics["total_debt"], short + long, rel_tol=1e-9, abs_tol=1)):
                _warn(warnings, "total_debt", "conflicting_debt_components", f"{label}: reported complete debt differs from compatible short-term borrowing and long-term debt totals; the reported amount and all original components are retained for review.")
    elif short is not None and long is not None and "long_term_debt_including_current" not in conflicting_aggregates:
        derive("total_debt", ("short_term_debt", "long_term_debt_including_current"), short + long)
        if metrics["total_debt"] is not None and not complete_conventional_debt_provenance(sources["total_debt"], end_date=period["end_date"]):
            metrics["total_debt"] = None
            sources.pop("total_debt", None)
            _warn(warnings, "total_debt", "unverified_debt_scope", f"{label}: source records do not establish complete conventional financial-debt scope.")
    elif metrics["current_debt_including_lease_obligations"] is not None or metrics["commercial_paper"] is not None:
        _warn(warnings, "total_debt", "unverified_debt_scope", f"{label}: DebtCurrent can include capital leases and commercial paper is only a short-term borrowing subtotal; neither establishes complete conventional financial debt.")
    else:
        _warn(warnings, "total_debt", "missing_debt_components", f"{label}: complete current and noncurrent debt components are unavailable.")

    if metrics["weighted_average_diluted_shares"] is None and metrics["shares_outstanding"] is None:
        _warn(warnings, "shares", "missing_share_count", f"{label}: no share count is available for this reporting period.")
    for required in ("revenue", "net_income", "total_assets", "total_liabilities", "shareholders_equity"):
        if metrics[required] is None:
            _warn(warnings, required, "missing_financial_field", f"{label}: the financial field is unavailable or ambiguous.")
    assets, liabilities, equity = (metrics[key] for key in ("total_assets", "total_liabilities", "shareholders_equity"))
    if all(value is not None for value in (assets, liabilities, equity)):
        if abs(assets - liabilities - equity) > max(1.0, abs(assets) * 0.01):
            _warn(warnings, "balance_sheet", "inconsistent_balance_sheet", f"{label}: assets do not reconcile to liabilities plus the reported equity within 1%; noncontrolling interests or differing contexts may be involved.")


def normalize_company_facts(raw: dict, cik: str | int | None = None) -> dict:
    observations = extract_observations(raw)
    warnings: list[dict] = []
    valid = []
    seen = set()
    filing_duration_ends: dict[str, str] = {}
    parent_periods: dict[str, set] = defaultdict(set)
    for obs in observations:
        if obs.get("metric") in ("net_income", "shareholders_equity"):
            parent_periods[obs["metric"]].add((obs.get("start"), obs.get("end"), obs.get("unit")))
        end, filed, length = _day(obs.get("end")), _day(obs.get("filed")), _length(obs)
        accession = obs.get("accn")
        # Use reported duration ends across the filing, including unmapped
        # entity-wide financial concepts. Instant share counts on the filing
        # date and future contractual maturities cannot redefine its report end.
        if obs.get("form") in FORMS and isinstance(accession, str) and end is not None and filed is not None and end <= filed and length is not None and 60 <= length <= 395:
            filing_duration_ends[accession] = max(filing_duration_ends.get(accession, ""), obs["end"])
    for obs in observations:
        metric = obs["metric"]
        if obs.get("taxonomy") == "us-gaap" and obs.get("form") in FORMS:
            ownership_metric = {
                "ProfitLoss": "net_income",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": "shareholders_equity",
            }.get(obs.get("concept"))
            if ownership_metric is not None and (obs.get("start"), obs.get("end"), obs.get("unit")) not in parent_periods[ownership_metric]:
                _warn(warnings, ownership_metric, "unverified_ownership_basis", f"{obs['concept']} includes noncontrolling interests and was not substituted for parent-attributable {ownership_metric}; the original observation is preserved.")
        if metric is None or obs.get("form") not in FORMS:
            continue
        expected_unit, kind = METRIC_DEFINITIONS[metric][1:]
        if obs["unit"] != expected_unit:
            code = "incompatible_currency" if expected_unit == "USD" and re.fullmatch(r"[A-Z]{3}", obs["unit"]) else "inconsistent_units"
            _warn(warnings, metric, code, f"Reported {obs['unit']} values cannot be used as {expected_unit}; no implicit currency or unit conversion was applied.")
            continue
        value = obs["value"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            _warn(warnings, metric, "invalid_value", "A non-finite or non-numeric reported value was excluded.")
            continue
        if metric in NON_NEGATIVE and (value < 0 or (expected_unit == "shares" and value == 0)):
            _warn(warnings, metric, "invalid_negative_value" if value < 0 else "invalid_share_count", "A value with an invalid sign or a zero share count was excluded.")
            continue
        end, start, filed = _day(obs["end"]), _day(obs["start"]), _day(obs["filed"])
        if end is None or filed is None or filed < end or (kind == "duration" and (start is None or start > end)) or (kind == "instant" and start is not None):
            _warn(warnings, metric, "unexpected_reporting_period", "A reported fact has an invalid or incompatible instant/duration period and was excluded.")
            continue
        if not isinstance(obs.get("accn"), str) or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", obs["accn"]):
            _warn(warnings, metric, "invalid_source_metadata", "A fact without a valid SEC accession number was excluded from normalized statements; the raw observation was preserved.")
            continue
        identity = (obs["taxonomy"], obs["concept"], obs["unit"], obs["start"], obs["end"], obs["filed"], obs["accn"], obs["form"], obs["fy"], obs["fp"], obs["frame"], value)
        if identity in seen:
            _warn(warnings, metric, "duplicate_observation", "Duplicate source observations were retained in raw provenance but counted once in normalized statements.")
            continue
        seen.add(identity)
        valid.append(obs)

    duration_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    instant_groups: dict[str, list[dict]] = defaultdict(list)
    for obs in valid:
        if METRIC_DEFINITIONS[obs["metric"]][2] == "instant":
            instant_groups[obs["end"]].append(obs)
        else:
            duration_groups[(obs["start"], obs["end"])].append(obs)

    annual = []
    for (start, end), records in sorted(duration_groups.items()):
        length = (_day(end) - _day(start)).days + 1
        if not 335 <= length <= 395:
            continue
        year = _period_year(records, True, warnings, filing_duration_ends)
        if year is None:
            continue
        period = _new_period(start, end, year, "FY")
        _populate(period, records, instant_groups[end])
        annual.append(period)

    def quarter_identity(start: str, end: str, records: list[dict]) -> tuple[int, int] | None:
        containers = [period for period in annual if period["start_date"] <= start <= end <= period["end_date"]]
        if len(containers) == 1:
            annual_period = containers[0]
            elapsed = (_day(end) - _day(annual_period["start_date"])).days + 1
            quarter = _cumulative_quarter(elapsed)
            if quarter is not None:
                return annual_period["fiscal_year"], quarter
        previous_annual = [period for period in annual if period["end_date"] < start]
        if previous_annual:
            prior = max(previous_annual, key=lambda period: period["end_date"])
            fiscal_start = _day(prior["end_date"]) + timedelta(days=1)
            elapsed = (_day(end) - fiscal_start).days + 1
            quarter = _cumulative_quarter(elapsed)
            length = (_day(end) - _day(start)).days + 1
            native = [obs for obs in records if obs.get("end") == filing_duration_ends.get(obs.get("accn"))
                      and obs.get("fp") == f"Q{quarter}" and obs.get("form") in ("10-Q", "10-Q/A")
                      and 0 <= (_day(obs["filed"]) - _day(end)).days <= 180]
            aligned = _day(start) == fiscal_start if length > 120 else quarter is not None and 60 <= elapsed - (quarter - 1) * 91 <= 125
            if quarter in (1, 2, 3) and native and aligned and fiscal_start <= _day(start):
                year = prior["fiscal_year"] + 1
                if any(obs.get("fy") != year for obs in native):
                    _warn(warnings, "fiscal_year", "filing_context_year_mismatch", "A current quarter's filing FY differs from its aligned fiscal-calendar year; the preceding annual boundary determines the fiscal-year label.")
                return year, quarter
        year = _period_year(records, False, warnings, filing_duration_ends)
        quarter = _cumulative_quarter((_day(end) - _day(start)).days + 1)
        if year is None or quarter is None:
            return None
        # A direct Q2/Q3 quarter has a ~90-day duration, but filing fp is Q2/Q3.
        timely = [obs for obs in records if obs.get("fy") == year and obs.get("fp") in ("Q1", "Q2", "Q3") and obs.get("end") == filing_duration_ends.get(obs.get("accn")) and _day(obs["filed"]) is not None and 0 <= (_day(obs["filed"]) - _day(end)).days <= 180]
        if quarter == 1 and timely:
            earliest = min(obs["filed"] for obs in timely)
            fps = {obs["fp"] for obs in timely if obs["filed"] == earliest}
            if len(fps) == 1:
                quarter = int(fps.pop()[1])
            else:
                _warn(warnings, "fiscal_period", "ambiguous_fiscal_period", "Native observations disagree on the fiscal quarter; the reporting period was excluded.")
                return None
        return year, quarter

    quarterly: dict[tuple[str, str], dict] = {}
    cumulative = []
    for (start, end), records in sorted(duration_groups.items()):
        length = (_day(end) - _day(start)).days + 1
        identity = quarter_identity(start, end, records)
        if identity is None:
            if _cumulative_quarter(length) is None:
                _warn(warnings, "fiscal_period", "unexpected_reporting_period", "A nonstandard duration could not be treated as an annual or quarterly reporting period.")
            continue
        year, quarter = identity
        if 60 <= length <= 120:
            period = _new_period(start, end, year, f"Q{quarter}")
            _populate(period, records, instant_groups[end])
            quarterly[(start, end)] = period
        if _cumulative_quarter(length) == quarter:
            cumulative.append((start, end, year, quarter, records))

    # Work only with exact fiscal-start-aligned adjacent cumulative intervals.
    # EPS and weighted shares are nonadditive and are never differenced.
    for start, end, year, quarter, records in cumulative:
        if quarter == 1:
            continue
        previous = [item for item in cumulative if item[0] == start and item[2] == year and item[3] == quarter - 1 and item[1] < end and 60 <= (_day(end) - _day(item[1])).days <= 120]
        if len(previous) != 1:
            _warn(warnings, "quarterly_cash_flow", "missing_aligned_ytd_period", f"FY{year} Q{quarter}: no unique aligned preceding cumulative period is available; standalone values were not inferred.")
            continue
        prior = previous[0]
        quarter_start = (_day(prior[1]) + timedelta(days=1)).isoformat()
        key = (quarter_start, end)
        period = quarterly.get(key)
        if period is None:
            period = _new_period(quarter_start, end, year, f"Q{quarter}")
            _populate(period, duration_groups.get(key, []), instant_groups[end])
            quarterly[key] = period
        label = f"FY{year} Q{quarter} ({end})"
        for metric, (_, _, kind) in METRIC_DEFINITIONS.items():
            if kind != "duration" or metric in NON_ADDITIVE or period["metrics"][metric] is not None:
                continue
            current_value, current_sources = _select(records, metric, period["warnings"], label)
            prior_value, prior_sources = _select(prior[4], metric, period["warnings"], label)
            if current_value is None or prior_value is None:
                continue
            if not _compatible([current_sources, prior_sources], cumulative=True, fiscal_year=year):
                _warn(period["warnings"], metric, "incompatible_ytd_basis", f"{label}: cumulative observations do not share a compatible concept, unit, fiscal start, and filing/restatement basis.")
                continue
            value = current_value - prior_value
            if not math.isfinite(value) or (metric in NON_NEGATIVE and value < 0):
                _warn(period["warnings"], metric, "invalid_derived_value", f"{label}: cumulative subtraction would produce an invalid or non-finite value; it was excluded.")
                continue
            period["metrics"][metric] = value
            period["provenance"][metric] = [
                {**obs, "derivation": "standalone_quarter_from_ytd", "coefficient": coefficient}
                for coefficient, group in ((1, current_sources), (-1, prior_sources)) for obs in group
            ]

    all_periods = annual + list(quarterly.values())
    for period in all_periods:
        _derive_period(period)
        for warning in period["warnings"]:
            if warning not in warnings:
                warnings.append(warning)
    if not all_periods:
        _warn(warnings, "financials", "missing_financial_data", "No unambiguous annual or quarterly USD reporting periods could be normalized.")
    identifier = str(cik or (raw.get("cik") if isinstance(raw, dict) else None) or "")
    references = {}
    for period in all_periods:
        for group in period["provenance"].values():
            for obs in group:
                accession = obs.get("accn")
                if not accession:
                    continue
                url = None
                if identifier.isascii() and identifier.isdigit() and re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
                    url = f"https://www.sec.gov/Archives/edgar/data/{int(identifier)}/{accession.replace('-', '')}/{accession}-index.html"
                references[accession] = {
                    "provider": "sec", "cik": identifier.zfill(10), "accession_number": accession,
                    "form": obs.get("form"), "filed": obs.get("filed"), "url": url,
                }
    return {
        "normalization_version": NORMALIZATION_VERSION,
        "annual": sorted(annual, key=lambda period: period["end_date"], reverse=True),
        "quarterly": sorted(quarterly.values(), key=lambda period: period["end_date"], reverse=True),
        "currency": "USD",
        "status": "partial" if warnings else "complete",
        "warnings": warnings,
        "source_references": list(references.values()),
    }
