"""Conservative boundary between reported financial data and valuation inputs.

Amounts remain in absolute reporting currency and shares are actual counts.
An unsupported value is None, including claims that might happen to be zero.
No provider financial ratio or presentation-scale amount is trusted as a fact.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import math
import re
from typing import Any

from app.services.normalization import METRIC_DEFINITIONS


ALIASES = {
    "operating_income": "ebit", "capital_expenditures": "capex",
    "weighted_average_diluted_shares": "shares", "total_debt": "debt",
    "cash_and_cash_equivalents": "cash", "shareholders_equity": "book_equity",
    "diluted_eps": "trailing_eps",
}
UNSUPPORTED = (
    "fcff", "fcfe", "net_borrowing", "change_nwc", "affo", "forecast_affo",
    "preferred_equity", "minority_interest", "other_nonoperating_assets",
    "dividend_per_share",
)


def number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except (OverflowError, ValueError):
        return None
    return result if math.isfinite(result) else None


def day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _warning(field: str, code: str, message: str) -> dict:
    return {"field": field, "code": code, "message": message}


def _json_safe(value):
    """Invalid original numerics remain unavailable rather than invalid JSON."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _fact(field: str, raw: Any, period: dict, currency: str | None, retrieved_at: Any) -> dict:
    """Check explicit unit, period, and source metadata before accepting a fact."""
    value = number(raw)
    records = deepcopy(period.get("provenance", {}).get(field, []))
    unit = "shares" if "shares" in field else f"{currency}/shares" if field in ("basic_eps", "diluted_eps") else currency
    kind = METRIC_DEFINITIONS.get(field, ((), None, "duration"))[2]
    if field in {"total_debt", "preferred_equity", "other_nonoperating_assets"}:
        kind = "instant"
    warnings = []
    if value is not None:
        if field == "depreciation_and_amortization" and isinstance(records, list) and any(
                isinstance(record, dict) and record.get("source") == "sec"
                and record.get("concept") == "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment"
                for record in records):
            warnings.append(_warning(field, "incomplete_depreciation_amortization_scope", "Legacy property, plant and equipment depreciation/depletion/amortization observations do not establish company-wide depreciation and intangible amortization; original source evidence is retained."))
        if field == "total_debt" and isinstance(records, list) and any(record.get("source") == "sec" for record in records if isinstance(record, dict)):
            from app.services.normalization import complete_conventional_debt_provenance
            if not complete_conventional_debt_provenance(records, end_date=period.get("end_date")):
                warnings.append(_warning(field, "incomplete_conventional_debt_scope", "Legacy debt observations do not establish complete conventional debt without lease overlap or missing borrowing components."))
        if not currency or not isinstance(records, list) or not records:
            warnings.append(_warning(field, "missing_fact_provenance", "A declared currency and original source observations are required."))
        else:
            if any(not isinstance(record, dict) or record.get("unit") != unit for record in records):
                warnings.append(_warning(field, "incompatible_fact_units", "Source observation units disagree with the declared financial unit."))
            for record in records:
                if not isinstance(record, dict):
                    continue
                if (not record.get("accn") or day(record.get("filed")) is None
                        or not record.get("source") or number(record.get("value", record.get("val"))) is None):
                    warnings.append(_warning(field, "missing_fact_provenance", "Source identifiers, finite reported values, and filing dates are required."))
                    break
                if day(record.get("end")) != day(period.get("end_date")):
                    warnings.append(_warning(field, "incompatible_fact_period", "A source observation ends outside the selected reporting period."))
                    break
                if kind == "duration" and not record.get("derivation") and day(record.get("start")) != day(period.get("start_date")):
                    warnings.append(_warning(field, "incompatible_fact_period", "Duration observations must match the full selected fiscal period."))
                    break
            if not warnings and not any(record.get("derivation") for record in records):
                if any(not math.isclose(number(record.get("value", record.get("val"))), value, rel_tol=1e-10, abs_tol=0.005) for record in records):
                    warnings.append(_warning(field, "reported_value_mismatch", "The normalized amount does not match its original reported observations."))
            elif not warnings:
                components = {}
                for record in records:
                    coefficient = number(record.get("coefficient", 1))
                    component = (record.get("component"), record.get("metric"), record.get("concept"),
                                 record.get("start"), record.get("end"), coefficient)
                    reported = number(record.get("value", record.get("val")))
                    if coefficient is None or (component in components and components[component] != reported):
                        warnings.append(_warning(field, "ambiguous_derivation_provenance", "Derived components lack a consistent signed source value."))
                        break
                    components[component] = reported
                if not warnings:
                    amount = sum(component[-1] * reported for component, reported in components.items())
                    if not math.isfinite(amount) or not math.isclose(amount, value, rel_tol=1e-10, abs_tol=0.005):
                        warnings.append(_warning(field, "derived_value_mismatch", "The normalized derived amount does not reconcile to its original signed components."))
    elif raw is not None:
        warnings.append(_warning(field, "invalid_financial_value", "The supplied financial amount is not finite numeric data."))
    if warnings:
        value = None
    derived = isinstance(records, list) and any(isinstance(item, dict) and item.get("derivation") for item in records)
    return {
        "value": value, "reported_value": number(raw), "unit": unit,
        "source_type": "unavailable" if value is None else "derived" if derived else "reported",
        "period": {key: period.get(key) for key in ("fiscal_year", "fiscal_period", "start_date", "end_date")},
        "retrieved_at": retrieved_at.isoformat() if isinstance(retrieved_at, datetime) else retrieved_at,
        "provenance": _json_safe(records) if isinstance(records, list) else [], "warnings": warnings,
    }


def normalize_annual_period(period: dict, currency: str | None, retrieved_at: Any = None) -> dict | None:
    """Validate an annual duration and each financial fact independently."""
    start, end = day(period.get("start_date")), day(period.get("end_date"))
    fiscal_year = period.get("fiscal_year")
    if (period.get("fiscal_period") != "FY" or start is None or end is None
            or not 335 <= (end - start).days + 1 <= 395
            or isinstance(fiscal_year, bool) or not isinstance(fiscal_year, int)):
        return None
    declared_currency = period.get("currency", currency)
    if not isinstance(declared_currency, str) or len(declared_currency) != 3 or not declared_currency.isupper():
        declared_currency = None
    facts = {field: _fact(field, value, period, declared_currency, retrieved_at)
             for field, value in period.get("metrics", {}).items()}
    warnings = list(period.get("warnings", []))
    warnings.extend(item for fact in facts.values() for item in fact["warnings"])
    return {
        **{key: period.get(key) for key in ("fiscal_year", "fiscal_period", "start_date", "end_date")},
        "currency": declared_currency, "metrics": {field: fact["value"] for field, fact in facts.items()},
        "facts": facts, "warnings": warnings,
    }


def build_valuation_inputs(profile: dict, normalized: dict, retrieved_at: Any = None) -> dict:
    """Build auditable inputs without fetching or persisting any data."""
    company = deepcopy(profile.get("company", profile))
    if company.get("instrument_id"):
        annual_sources = [item for item in normalized.get("source_references", []) if isinstance(item, dict)
                          and item.get("form") in {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}]
        if annual_sources:
            latest_source = max(annual_sources, key=lambda item: str(item.get("filed") or ""))
            source_regime = "foreign_private_issuer" if latest_source["form"].startswith(("20-F", "40-F")) else "us_domestic_reporter"
            # A foreign annual statement cannot acquire domestic share/currency
            # assumptions merely because the directory describes common shares.
            if source_regime == "foreign_private_issuer" or not company.get("filing_regime"):
                company["filing_regime"] = source_regime
    currency = normalized.get("currency")
    periods = []
    warnings = list(profile.get("warnings", [])) + list(normalized.get("warnings", []))
    for period in normalized.get("annual", normalized.get("periods", [])):
        usable = normalize_annual_period(period, currency, retrieved_at)
        if usable is None:
            warnings.append(_warning("financial_period", "incompatible_annual_period", "A malformed or nonannual financial observation was excluded."))
        else:
            periods.append(usable)
    # The same selection rule protects both the current valuation snapshot and
    # its historical trend from conflicting fiscal calendars/restatements.
    from app.valuation.history import select_annual_periods
    periods, selection_warnings = select_annual_periods(periods)
    warnings.extend(selection_warnings)
    periods.sort(key=lambda item: item["end_date"])
    latest = periods[-1] if periods else None
    facts = deepcopy(latest["facts"]) if latest else {}
    values = dict(latest["metrics"]) if latest else {}
    if latest:
        warnings.extend(latest["warnings"])
        if latest["currency"] != currency:
            warnings.append(_warning("currency", "incompatible_reporting_currency", "The latest period and dataset declare incompatible reporting currencies."))
            values = dict.fromkeys(values)
    for source, target in ALIASES.items():
        values[target] = values.get(source)
    values.update(dict.fromkeys(UNSUPPORTED))
    shares, income, eps = (values.get(key) for key in ("shares", "net_income", "trailing_eps"))
    multiple = company.get("has_multiple_share_classes") is True
    unknown_class = ((company.get("has_multiple_share_classes") is None
                      or company.get("share_class_basis_verified") is False)
                     and re.search(r"[.-][A-Z]$", str(company.get("ticker") or "").upper()) is not None)
    share_basis = not (multiple or unknown_class) or company.get("share_class_basis_verified") is True
    if company.get("instrument_id"):
        from app.services.security_identity import applicability
        kind = company.get("security_form", company.get("instrument_type"))
        foreign = kind in {"foreign_ordinary", "foreign_ordinary_share", "adr", "ads"} or company.get("filing_regime") in {"foreign_private_issuer", "20-F", "40-F"}
        if foreign:
            share_basis = not applicability(company) and company.get("share_basis_verified", (company.get("adr_metadata") or {}).get("share_basis_verified")) is True
        else:
            share_basis = (company.get("share_class_basis_verified") is True
                           or company.get("has_multiple_share_classes") is False and kind in
                           {"common_stock", "reit", "financial_institution", "insurance"})
    income_basis = shares is not None and shares > 0 and income is not None and eps is not None and abs(income / shares - eps) <= 0.02
    if not income_basis and income is not None and eps is not None:
        warnings.append(_warning("net_income", "incompatible_earnings_basis", "Consolidated net income and diluted EPS do not reconcile on the reported diluted share denominator; common-equity earnings are not inferred."))
    if not share_basis:
        values["shares"] = values["trailing_eps"] = None
        warnings.append(_warning("shares", "share_class_basis_unverified", "Company-level share and EPS facts cannot be assigned to this quoted class without explicit basis confirmation."))
    elif shares is not None:
        warnings.append(_warning("shares", "historical_diluted_share_denominator", "The model denominator is the annual diluted weighted-average share count, an explicitly dated historical modeling assumption, not current shares outstanding."))
    if (values.get("ebit") is not None and values.get("depreciation_and_amortization") is not None
            and math.isfinite(values["ebit"] + values["depreciation_and_amortization"])):
        values["ebitda"] = values["ebit"] + values["depreciation_and_amortization"]
        facts["ebitda"] = {"value": values["ebitda"], "unit": currency, "source_type": "derived",
                           "derivation_method": "Operating income (EBIT proxy) + reported depreciation and amortization for the same annual period.",
                           "period": facts["operating_income"]["period"], "retrieved_at": retrieved_at,
                           "provenance": facts["operating_income"]["provenance"] + facts["depreciation_and_amortization"]["provenance"],
                           "warnings": [_warning("ebitda", "ebitda_proxy", "Operating income is used as an EBIT proxy; company-specific adjustments are not fabricated.")]}
        warnings.extend(facts["ebitda"]["warnings"])
    else:
        values["ebitda"] = None
    market = deepcopy(profile.get("market"))
    if market:
        for field in ("price", "market_cap", "shares_outstanding"):
            value = number(market.get(field))
            market[field] = value if value is not None and value > 0 else None
        warnings.extend(market.get("warnings", []))
        if market.get("currency") != currency:
            warnings.append(_warning("market_price", "incompatible_market_currency", "Market and reporting currencies are incompatible; no foreign-exchange rate was invented."))
    references = deepcopy(normalized.get("source_references", [])) + deepcopy(profile.get("source_references", []))
    return {
        "company": company, "currency": currency, "normalization_version": normalized.get("normalization_version"),
        "reporting_period": {key: latest.get(key) for key in ("fiscal_year", "fiscal_period", "start_date", "end_date")} if latest else None,
        "financial_retrieved_at": retrieved_at.isoformat() if isinstance(retrieved_at, datetime) else retrieved_at,
        "market": market, "values": values, "facts": facts, "annual_periods": periods,
        "source_references": references, "warnings": warnings,
        "basis": {"share_basis_verified": share_basis, "income_earnings_basis_verified": income_basis,
                  "share_denominator": "annual diluted weighted-average shares",
                  "share_observation_period": latest.get("end_date") if latest else None,
                  "current_shares_available": bool(market and market.get("shares_outstanding")),
                  "book_equity_basis": "reported parent shareholder equity; common-share claims require explicit confirmation"},
    }
