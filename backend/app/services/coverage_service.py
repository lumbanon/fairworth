"""Independent discovery, data, valuation and research capabilities.

This endpoint performs no AI generation and makes no market-wide acquisition.
Data acquisition, if needed, remains owned by the existing on-demand services.
"""
from app.core.database import utcnow
from app.core.exceptions import ApiError
from app.providers.base import ProviderError
from app.services.security_identity import applicability, security_identity, scope_kwargs, ORDINARY_TYPES, UNSUPPORTED_TYPES

METHODOLOGY_VERSION = "market-coverage-2"
PRIMARY_STAGES = ("symbol_resolution", "security_identity", "active_listing", "classification", "share_basis",
                  "profile", "statements", "normalization", "valuation", "ai_research")
RESTRICTED = {"provider_access_denied", "provider_subscription_required", "provider_disabled"}
TEMPORARY = {"provider_timeout", "provider_unavailable", "provider_rate_limited", "valuation_timeout", "database_unavailable",
             "cache_refresh_busy", "cache_lease_lost"}


def stage(status, reason, *codes, **metadata):
    return {"status": status, "reason": reason, "reason_codes": list(codes), **metadata}


def failure_stage(error):
    code = getattr(error, "code", "provider_unavailable")
    status = "provider_restricted" if code in RESTRICTED else "temporarily_unavailable" if code in TEMPORARY else "identity_ambiguous" if code in {"ambiguous_security", "identity_ambiguous", "incompatible_financial_identity", "incompatible_security_identity"} else "financially_inapplicable" if code in {"unsupported_instrument_type", "inactive_listing"} else "missing_evidence"
    return stage(status, getattr(error, "message", "This analysis stage is unavailable."), code)


def classification_stage(company):
    kind = company.get("security_form", company.get("instrument_type"))
    metadata = {"instrument_type": company.get("instrument_type"), "security_form": kind,
                "issuer_business_category": company.get("issuer_business_category", "unknown"),
                "classification_evidence": company.get("classification_evidence", {}),
                "issuer_classification_evidence": company.get("issuer_classification_evidence", {})}
    if kind in UNSUPPORTED_TYPES:
        return stage("available", "The security form is recorded; this class does not support operating-company valuation.", "classified_unsupported_instrument", supported_operating_company_valuation=False, **metadata)
    if kind not in ORDINARY_TYPES:
        return stage("missing_evidence", "The security form has not been verified.", "instrument_classification_unverified", **metadata)
    return stage("available", "Security form and issuer business category are recorded separately.", "classified_instrument", supported_operating_company_valuation=True, **metadata)


def identity_stages(company, inputs=None):
    verification = company.get("listing_verification") or {}
    conflict = company.get("identity_status") in {"ambiguous", "conflicting", "unresolved"} or verification.get("status") == "conflicting"
    verified = not conflict and company.get("identity_status") == "verified" and all(company.get(key) for key in ("issuer_id", "instrument_id", "listing_id", "cik"))
    identity = stage("available" if verified else "identity_ambiguous" if conflict else "missing_evidence",
                     "The selected issuer, security and listing identities are verified." if verified else "The selected security requires an unambiguous, verified issuer mapping.",
                     "verified_security_identity" if verified else "identity_ambiguous" if conflict else "security_identity_unverified")
    listing_status = company.get("listing_status", "unknown")
    # Legacy injected fixtures predate the observation projection. New registry
    # records explicitly include it; a reference-only record never proves active.
    listing_verified = verification.get("status") == "verified" if verification else company.get("identity_status") == "verified"
    listing_conflict = verification.get("status") == "conflicting" if verification else conflict
    stale = bool(verification) and (verification.get("stale") is True or company.get("registry_status") in {"stale", "partial"})
    active = listing_status == "active" and listing_verified and not listing_conflict and not stale
    inactive = listing_status in {"inactive", "delisted", "suspended"}
    listing = stage("available" if active else "identity_ambiguous" if listing_conflict else "financially_inapplicable" if inactive else "missing_evidence",
                    "An authoritative source records this US listing on its observation date; this does not assert live trading or absence of halts." if active else "The listing is inactive or suspended." if inactive else "The retained listing observation is stale." if stale else "An authoritative active US listing observation is unavailable or conflicting.",
                    "verified_active_listing" if active else "conflicting_listing_sources" if listing_conflict else "inactive_listing" if inactive else "stale_listing_verification" if stale else "listing_status_unverified",
                    listing_status=listing_status, verification=verification,
                    source_observed_on=verification.get("observed_on"), source_published_at=verification.get("published_at"),
                    source_retrieved_at=verification.get("retrieved_at"))
    basis = (inputs or {}).get("basis") or {}
    compatible = basis.get("share_basis_verified") is True or company.get("share_basis_verified") is True or company.get("share_class_basis_verified") is True
    if company.get("instrument_id"):
        kind = company.get("security_form", company.get("instrument_type"))
        # An issuer-wide or legacy snapshot flag cannot establish the selected
        # instrument's ownership/classification. Listing activity is separate:
        # a dated inactive security may still have a verified historical basis.
        if not verified or kind not in ORDINARY_TYPES:
            compatible = False
        if company.get("has_multiple_share_classes") is True and company.get("share_class_basis_verified") is not True:
            compatible = False
    gate = applicability(company)
    if gate and gate[0] in {"adr_share_basis_unverified", "adr_per_security_conversion_unsupported", "foreign_share_basis_unverified", "foreign_currency_basis_unverified", "unsupported_instrument_type", "identity_ambiguous"}:
        compatible = False
    share = stage("available" if compatible else "missing_evidence",
                  "The available financial share basis is compatible with the selected security." if compatible else "A compatible issuer and selected-security share basis is not established; listing verification alone is insufficient.",
                  "compatible_share_basis" if compatible else gate[0] if gate else "share_class_basis_unverified",
                  share_class=company.get("share_class"), basis=basis)
    return {"security_identity": identity, "active_listing": listing, "classification": classification_stage(company), "share_basis": share}


class CoverageService:
    def __init__(self, companies, financials, valuations, research=None):
        self.companies, self.financials, self.valuations, self.research = companies, financials, valuations, research

    async def coverage(self, ticker, instrument_id=None, listing_id=None):
        stages = {}
        try:
            company, _ = await self.companies.company_identity(ticker, **scope_kwargs(instrument_id, listing_id))
        except (ApiError, ProviderError) as error:
            stages["symbol_resolution"] = failure_stage(error)
            for name in (*PRIMARY_STAGES[1:], "freshness"):
                stages[name] = stage("missing_evidence", "A resolved security identity is required.", "unresolved_identity")
            return {"identity": None, "as_of": utcnow(), "methodology_version": METHODOLOGY_VERSION, "stages": stages}
        kwargs = scope_kwargs(company.get("instrument_id"), company.get("listing_id"))
        identity = security_identity(company)
        stages["symbol_resolution"] = stage("available", "The symbol resolves to the selected instrument and issuer reference.", "resolved_identity",
                                             identity_status=company.get("identity_status", "legacy_reference"), source_refs=company.get("source_refs", []))
        gate = applicability(company)
        stages.update(identity_stages(company))
        try:
            inputs = await self.valuations.inputs(ticker, **kwargs)
            company = inputs["company"]
            identity = security_identity(company)
            gate = applicability(company)
            stages.update(identity_stages(company, inputs))
        except (ApiError, ProviderError, TimeoutError) as error:
            unavailable = failure_stage(error)
            stages["profile"] = stage("missing_evidence", "A registry identity reference is available; company profile enrichment is unavailable.", "reference_profile_only", reference_available=True)
            for name in ("statements", "normalization", "freshness", "valuation", "ai_research"):
                stages[name] = dict(unavailable)
            return {"identity": identity, "as_of": utcnow(), "methodology_version": METHODOLOGY_VERSION, "stages": stages}
        warnings = [item for item in inputs.get("warnings", []) if isinstance(item, dict)]
        codes = {item.get("code") for item in warnings}
        provider_restricted = sorted(codes & RESTRICTED)
        profile_codes = {item.get("code") for item in warnings if item.get("field") in {"company_profile", "profile"}}
        profile_restricted = sorted(profile_codes & RESTRICTED)
        financial_source = inputs.get("financial_source_status") or {}
        financial_warnings = financial_source.get("warnings")
        if financial_warnings is None:
            financial_warnings = [item for item in warnings if item.get("field") in {"financial_statements", "financial", "sec", "sec-edgar"}]
        financial_codes = {item.get("code") for item in financial_warnings if isinstance(item, dict)}
        if financial_source.get("error_code"):
            financial_codes.add(financial_source["error_code"])
        financial_restricted = sorted(financial_codes & RESTRICTED)
        financial_temporary = sorted(financial_codes & TEMPORARY)
        enriched = any(company.get(field) for field in ("description", "industry", "sector"))
        stages["profile"] = stage("available" if enriched else "provider_restricted" if profile_restricted else "missing_evidence",
                                   "Company identity and available provider profile fields are retained." if enriched else "Only the verified identity reference is available; a complete company profile is unavailable.",
                                   *profile_restricted, reference_available=True, provider_restrictions=provider_restricted,
                                   profile_provider_restrictions=profile_restricted)
        periods = inputs.get("annual_periods", [])
        fields = [key for key, record in inputs.get("facts", {}).items() if record.get("value") is not None]
        absent_status = "financially_inapplicable" if gate and gate[0] in {"unsupported_instrument_type", "inactive_listing"} else "provider_restricted" if financial_restricted else "temporarily_unavailable" if financial_temporary else "missing_evidence"
        stages["statements"] = stage("available" if periods else absent_status,
                                      "Dated compatible annual periods are available." if periods else "No compatible annual financial statement periods are available.",
                                      *([] if periods else sorted(code for code in financial_codes if code) or [gate[0] if gate else "missing_annual_statements"]),
                                      annual_period_count=len(periods), reporting_period=inputs.get("reporting_period"))
        stages["normalization"] = stage("available" if fields else "missing_evidence",
                                         "Selected financial fields passed normalization checks; field-level gaps remain explicit." if fields else "No verified normalized valuation facts are available.",
                                         normalized_field_count=len(fields), normalization_version=inputs.get("normalization_version"))
        stale = inputs.get("data_status") == "stale" or company.get("registry_status") == "stale" or any("stale" in str(code) for code in codes)
        stages["freshness"] = stage("missing_evidence" if stale or not periods else "available",
                                     "One or more retained sources are stale; original observation dates are preserved." if stale else "Evidence retains its source observation dates; this status does not assert current financial periods." if periods else "Financial source freshness cannot be established.",
                                     *(["stale_sources"] if stale else []), source_status=inputs.get("data_status"),
                                     reporting_period=inputs.get("reporting_period"), quote_observation_date=(inputs.get("market") or {}).get("price_timestamp"),
                                     financial_retrieved_at=inputs.get("financial_retrieved_at"),
                                     registry_as_of=company.get("registry_as_of"), registry_retrieved_at=company.get("registry_retrieved_at"),
                                     registry_status=company.get("registry_status"), registry_version=company.get("registry_version"))
        try:
            valuation = await self.valuations.calculate(ticker, **kwargs)
            base = valuation.get("scenarios", {}).get("base", {})
            summary = base.get("summary", {})
            eligible = [row["id"] for row in base.get("models", []) if row.get("status") == "valid"]
            stages["valuation"] = stage("available" if eligible else absent_status if gate or not periods else "missing_evidence",
                                         "At least one deterministic model is eligible; quality and contributing weights remain separate." if eligible else gate[1] if gate else "Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate.",
                                         *([gate[0]] if gate else sorted(code for code in financial_codes if code) if not periods else []), eligible_models=eligible, contributing_model_count=summary.get("count", 0),
                                         classification=summary.get("classification", "unavailable"),
                                         quality=base.get("diagnostics", {}).get("data_quality", {}).get("level", "unavailable"),
                                         confidence=base.get("confidence", {}).get("level", "unavailable"),
                                         model_diagnostics=[{"id": row["id"], **row.get("eligibility", {})} for row in base.get("models", [])])
        except (ApiError, ProviderError, TimeoutError) as error:
            stages["valuation"] = failure_stage(error)
        ready = self.research.status() if self.research else {"available": False, "enabled": False, "configured": False}
        stages["ai_research"] = stage("available" if fields else "missing_evidence",
                                      "Verified structured research evidence is available; no AI request was made." if fields else "Only sparse identity evidence is available; financial findings cannot be generated from missing facts.",
                                      evidence_available=bool(fields), provider_ready=bool(ready.get("available")),
                                      provider_enabled=bool(ready.get("enabled")), provider_configured=bool(ready.get("configured")),
                                      limitations=["AI evidence coverage does not imply a generated or validated report.", "Research generation requires an enabled, configured provider and an explicit user request."])
        return {"identity": identity, "as_of": utcnow(), "methodology_version": METHODOLOGY_VERSION, "stages": stages}
