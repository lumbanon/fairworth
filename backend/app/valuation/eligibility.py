"""Financial applicability and missing-input explanations precede calculations."""
from app.valuation.models import missing_inputs, required_inputs
from app.services.security_identity import applicability

ELIGIBILITY_METHODOLOGY_VERSION = "instrument-eligibility-2"

MODEL_NAMES = {
    "fcff": ("Discounted Cash Flow (FCFF)", "FCFF DCF"),
    "fcfe": ("Discounted Cash Flow (FCFE)", "FCFE DCF"),
    "pe": ("Forward P/E", "Forward P/E"),
    "evEbitda": ("EV/EBITDA", "EV/EBITDA"),
    "evRevenue": ("EV/Revenue", "EV/Revenue"),
    "peg": ("PEG-Based Valuation", "PEG"),
    "graham": ("Graham Number", "Graham"),
    "dividend": ("Dividend Discount Model", "Dividend discount"),
    "residual": ("Residual Income Model", "Residual income"),
    "pb": ("Price-to-Book", "Price-to-book"),
    "affo": ("REIT AFFO Valuation", "REIT AFFO"),
}


def eligibility(model_id, inputs, values, overridden=()):
    company, basis = inputs.get("company", {}), inputs.get("basis", {})
    reasons, warnings, missing = [], [], list(missing_inputs(model_id, values))
    unsuitable = False
    instrument_gate = applicability(company)
    if instrument_gate:
        code, message = instrument_gate
        reasons.append(code)
        if code in {"unsupported_instrument_type", "inactive_listing"}:
            unsuitable = True
        else:
            missing.append(code)
        warnings.append(message)
    bank = company.get("is_bank") if company.get("instrument_id") else values.get("is_bank") if isinstance(values.get("is_bank"), bool) else company.get("is_bank")
    reit = company.get("is_reit") if company.get("instrument_id") else values.get("is_reit") if isinstance(values.get("is_reit"), bool) else company.get("is_reit")
    bank = True if company.get("instrument_type") == "financial_institution" else bank
    reit = True if company.get("instrument_type") == "reit" else reit
    business = company.get("issuer_business_category")
    bank = True if business == "bank" else bank
    reit = True if business == "reit" else reit
    if bank is None and business in {"operating_company", "insurance", "reit"}:
        bank = False
    if reit is None and business in {"operating_company", "bank", "insurance", "financial_institution"}:
        reit = False
    if company.get("instrument_id") and reit is None and model_id in {"pe", "peg", "graham"}:
        reasons.append("business_classification_unavailable")
        missing.append("business_classification")
    share_verified = basis.get("share_basis_verified") or values.get("share_basis_confirmed") is True
    explicit_per_share = model_id in {"pe", "peg"} and "forward_eps" in overridden and values.get("forward_eps") is not None
    explicit_dividend = model_id == "dividend" and "dividend_per_share" in overridden and values.get("dividend_per_share") is not None
    if not inputs.get("currency"):
        reasons.append("unverified_reporting_currency")
        missing.append("reporting_currency")
    if any(warning.get("code") == "incompatible_reporting_currency" for warning in inputs.get("warnings", [])):
        reasons.append("incompatible_reporting_currency")
        missing.append("compatible_reporting_currency")
    if not share_verified and not explicit_per_share and not explicit_dividend:
        reasons.append("share_class_basis_unverified")
        missing.append("share_basis_confirmed")
    elif not share_verified:
        warnings.append("The user-supplied per-share forecast is assumed to apply to the selected ticker's quoted common share class; issuer-wide shares were not rescaled.")
    if values.get("share_basis_confirmed"):
        warnings.append("Share-class compatibility is a user confirmation, not a provider-verified fact.")
    try:
        financial_sic = 6000 <= int(company.get("sic") or 0) <= 6999
    except (TypeError, ValueError):
        financial_sic = False
    financial = bank or (financial_sic and not reit) or company.get("instrument_type") == "insurance" or business in {"insurance", "financial_institution"}
    if model_id in {"fcff", "evEbitda", "evRevenue"} and financial:
        reasons.append("financial_institution_enterprise_framework")
        unsuitable = True
    if model_id in {"fcff", "evEbitda", "evRevenue"} and bank is None:
        reasons.append("business_classification_unavailable")
        missing.append("business_classification")
    if reit and model_id in {"pe", "peg", "graham"}:
        reasons.append("reit_gaap_earnings_not_cash_earnings")
        unsuitable = True
    if model_id == "affo":
        if reit is False:
            reasons.append("not_a_reit")
            unsuitable = True
        elif reit is None:
            missing.append("reit_classification")
        if not (values.get("affo_basis_confirmed") is True or inputs.get("basis", {}).get("affo_verified")):
            missing.append("affo_basis_confirmed")
            reasons.append("affo_basis_unverified")
    if model_id in {"graham", "pb", "residual"}:
        if not (basis.get("common_equity_verified") or values.get("common_equity_basis_confirmed") is True or "book_equity" in overridden):
            missing.append("common_equity_basis_confirmed")
            reasons.append("preferred_and_common_book_scope_unverified")
        if not (bank is True or values.get("book_value_meaningful") is True):
            missing.append("book_value_meaningful")
            reasons.append("economic_book_value_unconfirmed")
        if basis.get("book_equity_basis") == "consolidated_including_noncontrolling_interests" and "book_equity" not in overridden:
            missing.append("common_book_equity")
            reasons.append("noncontrolling_equity_scope")
        warnings.append("Book equity may differ from economic asset value; book-based methods require suitable common-equity scope.")
    if model_id == "residual":
        if values.get("clean_surplus_confirmed") is not True:
            missing.append("clean_surplus_confirmed")
            reasons.append("clean_surplus_unconfirmed")
        warnings.append("Residual income assumes a clean-surplus book roll-forward; OCI, buybacks and capital issuance require explicit review.")
    if model_id == "dividend":
        if not (basis.get("stable_dividend_verified") or values.get("stable_dividend_confirmed") is True):
            missing.append("stable_dividend_confirmed")
            reasons.append("dividend_sustainability_unconfirmed")
    if model_id == "fcfe" and not basis.get("income_earnings_basis_verified") and "net_income" not in overridden and values.get("fcfe") is None and values.get("projected_fcfe") is None:
        missing.append("common_equity_earnings_basis")
        reasons.append("income_earnings_basis_mismatch")
    for key in ("shares",):
        if values.get(key) is not None and model_id not in {"pe", "peg", "dividend"}:
            warnings.append("The share denominator is a dated historical modeling input or user estimate, not a verified current diluted share count.")
    if model_id == "graham":
        warnings.append("The Graham Number is a historical screening heuristic, not a comprehensive intrinsic valuation.")
    if model_id == "peg":
        warnings.append("PEG uses growth in percentage points and shares earnings risk with P/E; it is sensitive to growth assumptions.")
    if model_id == "evRevenue":
        warnings.append("Revenue multiples omit explicit profitability and reinvestment; confidence is lower when margins are uncertain.")
    missing = sorted(set(missing))
    if unsuitable:
        status, reason = "ineligible", "The financial characteristics do not support this valuation framework."
    elif missing:
        status, reason = "unavailable", "Required inputs or compatibility confirmations are unavailable: " + ", ".join(missing) + "."
    else:
        status, reason = ("available_with_warnings" if warnings else "eligible"), "Required financial inputs and assumptions are available."
    paths = [{"required_inputs": path,
              "available_inputs": [key for key in path if values.get(key) is not None],
              "missing_inputs": [key for key in path if values.get(key) is None]}
             for path in required_inputs(model_id)]
    return {"status": status, "reason": reason, "methodology_version": ELIGIBILITY_METHODOLOGY_VERSION,
            "reason_codes": reasons or (["missing_inputs"] if missing else ["inputs_complete"]),
            "required_inputs": required_inputs(model_id), "input_paths": paths,
            "missing_inputs": missing, "warnings": warnings}
