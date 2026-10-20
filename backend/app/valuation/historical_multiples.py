"""Reproducible, publication-aware company valuation benchmarks.

Historical annual observations are paired with the first subsequent trading
close, never with a close preceding publication. Original filing vintages and
an explicit split basis are required. A median is a research estimate, not a
claim that the market's historical pricing was intrinsically correct.
"""

from __future__ import annotations

from datetime import timedelta
import math
from statistics import median, quantiles

from app.valuation.history import _aligned
from app.valuation.inputs import day, number

METHODOLOGY_VERSION = "historical-company-multiples-1"
TARGETS = {"pe": "target_pe", "ev_ebitda": "target_ev_ebitda", "ev_revenue": "target_ev_revenue"}
BRIDGE_FIELDS = {
    "debt": ("total_debt", "debt"), "cash": ("cash_and_cash_equivalents", "cash"),
    "preferred_equity": ("preferred_equity",), "minority_interest": ("minority_interest",),
    "other_nonoperating_assets": ("other_nonoperating_assets",),
}


def _warning(field, code, message):
    return {"field": field, "code": code, "message": message}


def _record(field, value=None, warnings=(), **extra):
    return {"value": value, "unit": "multiple", "source_type": "historical_estimate" if value is not None else "unavailable",
            "source_category": "historical_company_valuation" if value is not None else "unavailable",
            "source_provider": None, "source_description": "Publication-aligned historical company valuation; a benchmark estimate, not proof of intrinsic value." if value is not None else "No sufficiently compatible historical company valuation benchmark is available.",
            "observation_date": None, "observation_period": None, "financial_period": None,
            "derivation_method": None, "derivation_formula": None, "evidence_type": "estimate" if value is not None else "unavailable",
            "editable": True, "overridden": False, "warnings": list(warnings), "quality": "moderate" if value is not None else "unavailable",
            "dependency_fields": [], "policy_dependencies": [], "source_identifiers": [], **extra}


def _settings(policy):
    def value(key, default):
        return policy.get(key, default) if isinstance(policy, dict) else getattr(policy, key, default)
    return {"minimum_forecast_growth": value("minimum_forecast_growth", -0.15),
            "maximum_forecast_growth": value("maximum_forecast_growth", 0.20),
            "historical_multiple_years": value("historical_multiple_years", 5),
            "historical_multiple_minimum_years": value("historical_multiple_minimum_years", 3),
            "maximum_growth_dispersion": value("maximum_annual_growth_dispersion", 1.0)}


def _facts(period, fields):
    for field in fields:
        fact = period.get("facts", {}).get(field)
        if not isinstance(fact, dict):
            continue
        value = number(fact.get("value"))
        metric = number(period.get("metrics", {}).get(field, value))
        if value is not None and metric is not None and math.isclose(value, metric, rel_tol=1e-10, abs_tol=0.005):
            return value, fact
    return None, None


def _publication(facts):
    dates = []
    for fact in facts:
        if not isinstance(fact, dict) or not fact.get("provenance"):
            return None
        for source in fact["provenance"]:
            if not isinstance(source, dict) or not source.get("source") or not source.get("accn"):
                return None
            filed = day(source.get("filed"))
            if filed is None:
                return None
            dates.append(filed)
    return max(dates) if dates else None


def _valid_period(period, currency):
    start, end = day(period.get("start_date")), day(period.get("end_date"))
    return (isinstance(currency, str) and len(currency) == 3 and currency.isupper()
            and period.get("fiscal_period") == "FY" and type(period.get("fiscal_year")) is int
            and start is not None and end is not None and 335 <= (end - start).days + 1 <= 395
            and period.get("currency") == currency)


def _prices(envelope, currency, as_of):
    rows = envelope.get("prices", []) if isinstance(envelope, dict) else []
    grouped, rejected = {}, []
    for row in rows:
        if not isinstance(row, dict):
            continue
        observed, close = day(row.get("date")), number(row.get("close"))
        if observed is None or observed > as_of or close is None or close <= 0 or row.get("currency", envelope.get("currency")) != currency:
            continue
        item = {**row, "date": observed.isoformat(), "close": close,
                "provider": row.get("provider") or envelope.get("provider"),
                "adjustment_basis": row.get("adjustment_basis") or envelope.get("adjustment_basis"),
                "adjustment_date": row.get("adjustment_date") or envelope.get("adjustment_date")}
        adjusted = day(item.get("adjustment_date"))
        if item.get("adjustment_basis") == "split_adjusted" and adjusted is not None and adjusted > as_of:
            rejected.append({"date": observed.isoformat(), "reason": "price_adjustment_after_snapshot"})
            continue
        grouped.setdefault(observed, []).append(item)
    valid = []
    for observed, group in sorted(grouped.items()):
        if len({(item["close"], item.get("adjustment_basis"), item.get("adjustment_date")) for item in group}) != 1:
            rejected.append({"date": observed.isoformat(), "reason": "conflicting_price_observations"})
        else:
            valid.append(group[0])
    return valid, rejected


def _split_factor(basis_date, price, splits):
    """Convert original reported EPS/shares to the price's explicit split basis."""
    basis = day(basis_date)
    if basis is None or not isinstance(splits, dict) or splits.get("complete") is not True:
        return None, "unverified_split_history"
    kind = price.get("adjustment_basis")
    target = day(price.get("adjustment_date")) if kind == "split_adjusted" else day(price["date"]) if kind == "unadjusted" else None
    if target is None or basis > target:
        return None, "incompatible_price_adjustment_basis"
    start, end = day(splits.get("coverage_start")), day(splits.get("coverage_end"))
    if (start is not None and start > basis) or (end is not None and end < target):
        return None, "insufficient_split_history_coverage"
    factor, seen = 1.0, {}
    for event in splits.get("splits", []):
        if not isinstance(event, dict):
            return None, "invalid_split_observation"
        observed = day(event.get("date"))
        numerator, denominator = number(event.get("numerator")), number(event.get("denominator"))
        if observed is None or numerator is None or denominator is None or numerator <= 0 or denominator <= 0:
            return None, "invalid_split_observation"
        ratio = numerator / denominator
        if not math.isfinite(ratio) or observed in seen and not math.isclose(seen[observed], ratio):
            return None, "conflicting_split_observations"
        if observed not in seen and basis < observed <= target:
            factor *= ratio
        seen[observed] = ratio
    return (factor, None) if math.isfinite(factor) and factor > 0 else (None, "nonfinite_split_adjustment")


def _adjusted_eps(period, price, splits):
    eps, fact = _facts(period, ("diluted_eps",))
    if eps is None or eps <= 0:
        return None, "nonpositive_or_missing_earnings"
    if fact.get("unit") != f"{period.get('currency')}/shares":
        return None, "incompatible_earnings_unit"
    published = _publication([fact])
    if published is None or published >= day(price["date"]):
        return None, "earnings_not_known_at_price_date"
    verified = fact.get("split_basis_verified", period.get("eps_split_basis_verified"))
    basis = fact.get("split_basis_date") or period.get("eps_split_basis_date")
    if verified is not True or day(basis) is None:
        return None, "unverified_earnings_split_basis"
    if day(basis) > published:
        return None, "earnings_split_basis_after_publication"
    factor, error = _split_factor(basis, price, splits)
    if error:
        return None, error
    result = eps / factor
    return (result, None) if math.isfinite(result) and result > 0 else (None, "nonfinite_adjusted_earnings")


def _as_of_periods(periods, price, currency):
    """Use the latest usable vintage already public at the observation date."""
    groups = {}
    for period in periods:
        if not _valid_period(period, currency):
            continue
        _, fact = _facts(period, ("diluted_eps",))
        published = _publication([fact])
        if published is not None and published < day(price["date"]):
            groups.setdefault(period["fiscal_year"], []).append((published, period))
    selected = []
    for candidates in groups.values():
        latest = max(item[0] for item in candidates)
        group = [period for published, period in candidates if published == latest]
        identities = {(period.get("start_date"), period.get("end_date"), period.get("metrics", {}).get("diluted_eps")) for period in group}
        if len(identities) == 1:
            selected.append(group[0])
    return sorted(selected, key=lambda period: period["fiscal_year"])


def _forward_growth(period, periods, price, splits, settings, currency):
    known = [item for item in _as_of_periods(periods, price, currency) if item["fiscal_year"] <= period["fiscal_year"]]
    window = known[-4:]
    if len(window) != 4 or window[-1]["fiscal_year"] != period["fiscal_year"] or any(not _aligned(left, right) for left, right in zip(window, window[1:])):
        return None, None, "insufficient_as_of_forecast_history"
    amounts = [_adjusted_eps(item, price, splits)[0] for item in window]
    if any(value is None for value in amounts):
        return None, None, "incompatible_as_of_earnings_history"
    changes = [current / previous - 1 for previous, current in zip(amounts, amounts[1:])]
    if any(not math.isfinite(value) for value in changes) or max(changes) - min(changes) > settings["maximum_growth_dispersion"]:
        return None, None, "unstable_as_of_earnings_forecast"
    try:
        raw = math.expm1((math.log(amounts[-1]) - math.log(amounts[0])) / 3)
    except (ArithmeticError, ValueError):
        return None, None, "nonfinite_as_of_growth"
    rate = min(settings["maximum_forecast_growth"], max(settings["minimum_forecast_growth"], raw))
    return rate, {"raw_cagr": raw, "used_growth": rate, "years": 3, "start": window[0]["end_date"],
                  "end": window[-1]["end_date"], "policy_bounded": raw != rate}, None


def _first_after(prices, published):
    # Filing time is not supplied: use the next trading day, never same-day close.
    return next((price for price in prices if published < day(price["date"]) <= published + timedelta(days=7)), None)


def _identifiers(facts):
    return sorted({str(record.get("accn")) for fact in facts if isinstance(fact, dict)
                   for record in fact.get("provenance", []) if record.get("accn")})


def _statistics(samples, rejected, minimum):
    values = [item["multiple"] for item in samples]
    fences = None
    retained = samples
    if len(values) >= 4:
        q1, _, q3 = quantiles(values, n=4, method="inclusive")
        iqr = q3 - q1
        fences = [q1 - 1.5 * iqr, q3 + 1.5 * iqr]
        retained = [item for item in samples if fences[0] <= item["multiple"] <= fences[1]]
        rejected = [*rejected, *[{**item, "reason": "tukey_iqr_outlier"} for item in samples if item not in retained]]
    values = [item["multiple"] for item in retained]
    years = sorted({item["fiscal_year"] for item in retained})
    available = len(years) >= minimum
    return {"status": "available" if available else "unavailable", "median": median(values) if values else None,
            "minimum": min(values) if values else None, "maximum": max(values) if values else None,
            "fiscal_years": years, "independent_fiscal_years": len(years), "observations": retained,
            "excluded_observations": rejected, "outlier_method": "Tukey fences at Q1/Q3 +/- 1.5 IQR; inclusive quartiles; applied only with at least four independent annual observations.",
            "outlier_fences": fences, "minimum_required_years": minimum}


def _enterprise_sample(period, prices, splits):
    facts, bridge = [], {}
    for key, aliases in BRIDGE_FIELDS.items():
        value, fact = _facts(period, aliases)
        if value is None or value < 0 or fact.get("unit") != period["currency"]:
            return None, "incomplete_enterprise_bridge"
        if key in {"preferred_equity", "minority_interest", "other_nonoperating_assets"} and fact.get("scope_complete") is not True:
            return None, "unverified_claim_scope"
        if fact.get("value_state") in {"unknown", "unavailable", "user_supplied"}:
            return None, "unverified_claim_value"
        facts.append(fact)
        bridge[key] = value
    shares, share_fact = _facts(period, ("shares_outstanding",))
    if shares is None or shares <= 0 or share_fact.get("unit") != "shares":
        return None, "missing_period_end_common_shares"
    if share_fact.get("share_class_basis_verified", period.get("share_class_basis_verified")) is not True:
        return None, "incompatible_historical_share_classes"
    facts.append(share_fact)
    revenue, revenue_fact = _facts(period, ("revenue",))
    if revenue is None or revenue <= 0:
        return None, "nonpositive_or_missing_revenue"
    facts.append(revenue_fact)
    published = _publication(facts)
    if published is None or not 0 <= (published - day(period["end_date"])).days <= 180:
        return None, "incompatible_enterprise_publication_period"
    price = _first_after(prices, published)
    if price is None:
        return None, "missing_post_publication_price"
    factor, error = _split_factor(share_fact.get("split_basis_date"), price, splits)
    if error:
        return None, error
    adjusted_shares = shares * factor
    equity = price["close"] * adjusted_shares
    enterprise = equity + bridge["debt"] - bridge["cash"] + bridge["preferred_equity"] + bridge["minority_interest"] - bridge["other_nonoperating_assets"]
    if not math.isfinite(enterprise) or enterprise <= 0:
        return None, "nonpositive_or_nonfinite_enterprise_value"
    ebit, ebit_fact = _facts(period, ("operating_income", "ebit"))
    da, da_fact = _facts(period, ("depreciation_and_amortization",))
    ebitda = ebit + da if ebit is not None and da is not None and da >= 0 else None
    if ebitda is not None and (not math.isfinite(ebitda) or ebitda <= 0 or _publication([ebit_fact, da_fact]) is None or _publication([ebit_fact, da_fact]) >= day(price["date"])):
        ebitda = None
    return {"fiscal_year": period["fiscal_year"], "financial_period": period["end_date"], "date": price["date"],
            "price": price["close"], "provider": price.get("provider"), "period_end_common_shares": shares,
            "adjusted_period_end_common_shares": adjusted_shares, "market_equity_proxy": equity,
            "enterprise_value_proxy": enterprise, "bridge": bridge, "revenue": revenue, "ebitda": ebitda,
            "source_identifiers": _identifiers([*facts, ebit_fact, da_fact]),
            "policy_dependencies": ["dated_period_end_share_proxy", "reported_bridge_carrying_value_proxy"]}, None


def derive_historical_multiples(inputs, evidence, policy=None):
    """Return metadata records and full inclusion/exclusion diagnostics, no I/O."""
    evidence = evidence or {}
    records = {target: _record(target) for target in TARGETS.values()}
    settings = _settings(policy)
    as_of = day(evidence.get("as_of_date")) or day(str((inputs.get("market") or {}).get("retrieved_at") or "")[:10]) or day(str(inputs.get("financial_retrieved_at") or "")[:10])
    envelope = evidence.get("historical_prices") or {}
    as_of = as_of or day(str(envelope.get("retrieved_at") or "")[:10])
    if as_of is None:
        warnings = [_warning("historical_multiples", "missing_valuation_snapshot_date", "Historical analytics require a dated reproducible financial or market snapshot.")]
        return {"assumptions": records, "statistics": {}, "warnings": warnings, "methodology_version": METHODOLOGY_VERSION}
    prices, rejected_prices = _prices(envelope, inputs.get("currency"), as_of)
    periods = evidence.get("historical_annual_periods") or inputs.get("annual_periods", [])
    periods = [period for period in periods if isinstance(period, dict) and _valid_period(period, inputs.get("currency"))]
    splits = evidence.get("splits") or {}
    latest_year = max((period["fiscal_year"] for period in inputs.get("annual_periods", periods)), default=None)
    lower_year = latest_year - settings["historical_multiple_years"] + 1 if latest_year is not None else None
    selected = [period for period in periods if lower_year is not None and lower_year <= period["fiscal_year"] <= latest_year]
    samples = {key: [] for key in TARGETS}
    rejected = {key: list(rejected_prices) for key in TARGETS}
    seen = {key: set() for key in TARGETS}
    share_verified = inputs.get("basis", {}).get("share_basis_verified") is True
    for period in sorted(selected, key=lambda item: (item["fiscal_year"], str(_publication([_facts(item, ("diluted_eps",))[1]])))):
        year = period["fiscal_year"]
        _, eps_fact = _facts(period, ("diluted_eps",))
        published = _publication([eps_fact])
        price = _first_after(prices, published) if published is not None else None
        failure = "share_class_basis_unverified" if not share_verified else "missing_post_publication_price" if price is None else None
        if published is not None and not 0 <= (published - day(period["end_date"])).days <= 180:
            failure = "future_restatement_not_original_annual_publication"
        adjusted, eps_error = _adjusted_eps(period, price, splits) if failure is None else (None, None)
        rate, growth_record, growth_error = _forward_growth(period, periods, price, splits, settings, inputs.get("currency")) if failure is None and eps_error is None else (None, None, None)
        failure = failure or eps_error or growth_error
        if failure:
            rejected["pe"].append({"fiscal_year": year, "reason": failure})
        elif year not in seen["pe"]:
            forward = adjusted * (1 + rate)
            multiple, trailing = price["close"] / forward, price["close"] / adjusted
            if not math.isfinite(multiple) or not 0 < multiple <= 1000:
                rejected["pe"].append({"fiscal_year": year, "reason": "invalid_historical_multiple"})
            else:
                margin_values = period.get("metrics", {})
                revenue, net_income = number(margin_values.get("revenue")), number(margin_values.get("net_income"))
                samples["pe"].append({"fiscal_year": year, "financial_period": period["end_date"], "date": price["date"],
                                      "earnings_publication_date": published.isoformat(), "price": price["close"],
                                      "adjusted_trailing_eps": adjusted, "forward_eps_proxy": forward,
                                      "multiple": multiple, "trailing_multiple": trailing, "as_of_growth": growth_record,
                                      "provider": price.get("provider"), "source_identifiers": _identifiers([eps_fact]),
                                      "net_margin": net_income / revenue if net_income is not None and revenue is not None and revenue > 0 else None,
                                      "policy_dependencies": ["historical_forward_growth_bound"] if growth_record["policy_bounded"] else []})
                seen["pe"].add(year)
        enterprise, error = _enterprise_sample(period, prices, splits) if share_verified else (None, "share_class_basis_unverified")
        for key, denominator in (("ev_revenue", "revenue"), ("ev_ebitda", "ebitda")):
            if enterprise is None:
                rejected[key].append({"fiscal_year": year, "reason": error})
            elif enterprise[denominator] is None:
                rejected[key].append({"fiscal_year": year, "reason": "missing_compatible_ebitda"})
            elif year not in seen[key]:
                multiple = enterprise["enterprise_value_proxy"] / enterprise[denominator]
                if math.isfinite(multiple) and 0 < multiple <= 1000:
                    samples[key].append({**enterprise, "multiple": multiple})
                    seen[key].add(year)
                else:
                    rejected[key].append({"fiscal_year": year, "reason": "invalid_historical_multiple"})
    statistics = {key: _statistics(samples[key], rejected[key], settings["historical_multiple_minimum_years"]) for key in TARGETS}
    for key, target in TARGETS.items():
        stats = statistics[key]
        reason = None
        if stats["status"] != "available":
            reason = "insufficient_independent_historical_years"
        elif latest_year - max(stats["fiscal_years"]) > 1:
            reason = "historical_multiple_economics_not_recent"
        elif key == "pe":
            latest_eps = number(inputs.get("values", {}).get("trailing_eps"))
            if latest_eps is None or latest_eps <= 0:
                reason = "nonpositive_or_incompatible_current_earnings"
            margins = [item["net_margin"] for item in stats["observations"] if item.get("net_margin") is not None and item["net_margin"] > 0]
            latest = inputs.get("values", {})
            revenue, income = number(latest.get("revenue")), number(latest.get("net_income"))
            current_margin = income / revenue if income is not None and revenue is not None and revenue > 0 else None
            if margins and current_margin is not None and abs(current_margin - median(margins)) > max(0.15, 0.5 * median(margins)):
                reason = "material_profitability_regime_change"
            stats["historical_trailing_median"] = median([item["trailing_multiple"] for item in stats["observations"]]) if stats["observations"] else None
        if reason:
            stats["status"] = "unavailable"
            records[target] = _record(target, warnings=[_warning(target, reason, "No defensible automatic target is established; inspect the excluded observations and provide an explicit analyst multiple if appropriate.")], statistics=stats)
            continue
        observations = stats["observations"]
        dates = [item["date"] for item in observations]
        policies = sorted({dependency for item in observations for dependency in item.get("policy_dependencies", [])})
        method = ("Median(price on first trading day after earnings publication / (split-compatible reported annual EPS × (1 + three-year EPS CAGR known at that date))); no future fundamentals enter historical forecasts."
                  if key == "pe" else "Median(publication-aligned historical EV proxy / same-period reported " + ("EBIT + compatible D&A" if key == "ev_ebitda" else "revenue") + "); EV proxy uses explicitly dated period-end common shares and complete reported claim scope.")
        warnings = [_warning(target, "historical_multiple_not_intrinsic_proof", "Historical pricing is a transparent company benchmark, not proof of intrinsic fair value; future growth, risk, reinvestment and profitability may differ.")]
        if key != "pe":
            warnings.append(_warning(target, "historical_trailing_enterprise_benchmark", "A trailing enterprise multiple is applied as a forward target estimate; period-end shares and reported claim values are dated approximations, not contemporaneous market-value capital structure."))
        if policies:
            warnings.append(_warning(target, "historical_multiple_policy_dependencies", "This historical estimate depends on explicitly disclosed forecasting or capital-value modeling policies."))
        records[target] = _record(target, stats["median"], warnings, source_provider="sec-edgar + " + str(envelope.get("provider") or "market provider"),
                                  observation_date=max(dates), observation_period={"start": min(dates), "end": max(dates)},
                                  financial_period={"fiscal_years": stats["fiscal_years"]}, derivation_method=method, derivation_formula=method,
                                  source_identifiers=sorted({identifier for item in observations for identifier in item["source_identifiers"]}),
                                  policy_dependencies=policies, statistics=stats, quality="low" if policies or len(observations) == 3 else "moderate")
    return {"assumptions": records, "statistics": statistics, "warnings": [], "methodology_version": METHODOLOGY_VERSION}
