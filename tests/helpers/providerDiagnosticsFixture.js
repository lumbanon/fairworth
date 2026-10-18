import { automaticProviderValuationFixture } from "./providerValuationFixture.js";

// Deterministic transport fixture only; these are not current company facts,
// provider observations, or independent expectations for valuation mathematics.
export function providerDiagnosticsFixture(ticker = "MSFT", { request = {}, mode = "multiple", price = 100 } = {}) {
  const response = automaticProviderValuationFixture(ticker, { request, price });
  const user = Object.hasOwn(request.assumptions ?? {}, "target_pe");
  const sources = [{ source: "SEC EDGAR", concept: "RevenueFromContractWithCustomerExcludingAssessedTax", accn: "0000000000-26-000001", filed: "2026-02-10", start: "2025-01-01", end: "2025-12-31", value: 125000000.125, unit: "USD", filing_url: "https://www.sec.gov/Archives/edgar/data/1/fixture.htm" }];
  const fields = {
    "reported.revenue": { value: 125000000.125, unit: "USD", source_type: "reported", provider: "SEC EDGAR", observation_date: "2025-12-31", period: { start_date: "2025-01-01", end_date: "2025-12-31" }, retrieved_at: "2026-10-14T10:00:00Z", source_identifiers: ["fixture:revenue:2025"], provenance: sources, warnings: [] },
    "derived.total_debt": { value: 15000000, unit: "USD", source_type: "derived", provider: "SEC EDGAR", observation_date: "2025-12-31", period: { end_date: "2025-12-31" }, retrieved_at: "2026-10-14T10:00:00Z", derivation: "Complete same-period conventional debt components; lease liabilities kept separate.", source_identifiers: ["fixture:debt:2025"], provenance: [], warnings: [] },
    "assumptions.wacc": { value: null, unit: "fraction", source_type: "unavailable", provider: "Unavailable", observation_date: null, period: null, retrieved_at: null, provenance: [], source_identifiers: [], warnings: ["A sourced cost of capital is unavailable."] },
    "assumptions.target_pe": { value: user ? request.assumptions.target_pe : 22.5, unit: "multiple", source_type: user ? "user_input" : "benchmark_assumption", provider: user ? "User" : "Fairworth research policy", observation_date: null, period: null, retrieved_at: null, derivation: user ? "Explicit analyst override" : "Documented illustrative policy", provenance: [], source_identifiers: [], warnings: [] },
    "market.price": { value: price, unit: "USD/share", source_type: price == null ? "unavailable" : "market_observation", provider: "fixture-market", observation_date: price == null ? null : "2026-01-15T16:00:00Z", period: null, retrieved_at: "2026-10-14T10:00:00Z", provenance: [], source_identifiers: ["fixture:quote:2026-01-15"], warnings: price == null ? ["Provider endpoint restricted (HTTP 402)."] : ["Dated quote is stale."] },
    "reported.book_equity": { value: null, unit: "USD", source_type: "unavailable", provider: "SEC EDGAR", observation_date: "2025-12-31", period: { end_date: "2025-12-31" }, retrieved_at: "2026-10-14T10:00:00Z", source_identifiers: [], provenance: [], warnings: ["A compatible common-share equity basis is not verified."] },
  };
  const completeness = {
    methodology_version: "phase6-transport-fixture-1", reporting_period: { fiscal_year: 2025, fiscal_period: "FY", end_date: "2025-12-31" }, as_of: "2026-10-14", quote_observation_date: price == null ? null : "2026-01-15T16:00:00Z",
    groups: { available: ["reported.revenue", "derived.total_debt", "assumptions.target_pe", ...(price == null ? [] : ["market.price"])], missing: ["assumptions.wacc", ...(price == null ? ["market.price"] : [])], stale: price == null ? [] : ["market.price"], incompatible: ["reported.book_equity"], restricted: price == null ? ["market.price"] : [], derived: ["derived.total_debt"], policy: user ? [] : ["assumptions.target_pe"], user: user ? ["assumptions.target_pe"] : [] }, fields,
  };
  for (const scenario of Object.values(response.scenarios)) {
    const secondId = mode === "correlated" ? "peg" : "fcff";
    const contributes = mode === "none" ? [] : mode === "single" ? ["pe"] : ["pe", secondId];
    const disabled = request.enabled_models && !request.enabled_models.includes(secondId);
    if (disabled) contributes.splice(contributes.indexOf(secondId), contributes.includes(secondId) ? 1 : 0);
    const effective = Object.fromEntries(contributes.map((id) => [id, contributes.length === 1 ? 1 : id === "pe" ? 0.4 : 0.6]));
    for (const model of scenario.models) {
      const valid = contributes.includes(model.id);
      model.status = valid ? "valid" : "unavailable";
      model.fair_value = valid ? model.id === "pe" ? 777.77 : 650.125 : null;
      model.upside = valid && price != null ? -12.34 : null;
      model.classification = valid ? user ? "user_defined" : "policy_based" : "unavailable";
      model.source_quality = { level: valid ? "low" : "unavailable", warnings: [] };
      model.eligibility = { ...model.eligibility, status: valid ? "available_with_warnings" : "unavailable", required_inputs: model.id === "pe" ? [["forward_eps", "target_pe"]] : [model.eligibility.required_inputs],
        missing_inputs: valid ? [] : model.id === "fcfe" ? ["net_borrowing", "change_nwc"] : ["supported_financial_inputs"],
        input_paths: valid ? [{ required_inputs: ["forward_eps", "target_pe"], available_inputs: ["forward_eps", "target_pe"], missing_inputs: [] }] : [{ required_inputs: ["wacc", "cash"], available_inputs: ["cash"], missing_inputs: ["wacc"] }], reason: valid ? "Illustrative synthetic input basis; independent source review remains necessary." : "Complete compatible inputs are unavailable.",
        weight_explanation: "Related methods share a family weighting budget; this grouping does not establish independence." };
    }
    const families = contributes.length === 0 ? [] : mode === "correlated" || contributes.length === 1 ? [{ id: "earnings", label: "Earnings methods", model_ids: contributes }]
      : [{ id: "earnings", label: "Earnings methods", model_ids: ["pe"] }, { id: "cash_flow", label: "Cash-flow methods", model_ids: ["fcff"] }];
    const warnings = contributes.length === 0 ? ["No supported valuation is available."] : contributes.length === 1 ? ["Single-model estimate; independent confirmation is unavailable."] : ["Model availability alone does not establish independent confirmation."];
    scenario.summary = { ...scenario.summary, fair_value: contributes.length ? 701.183 : null, upside: contributes.length && price != null ? -12.34 : null, count: contributes.length, effective_weights: effective, warnings, classification: contributes.length ? user ? "user_defined" : "policy_based" : "unavailable" };
    scenario.confidence = { level: contributes.length ? "low" : "unavailable", factors: [{ name: "Assumption dependence", status: "limited", explanation: "Research-policy assumptions and shared inputs limit confidence." }], disclaimer: "Heuristic quality assessment, not statistical certainty." };
    scenario.data_completeness = structuredClone(completeness);
    scenario.diagnostics = { methodology_version: "phase6-diagnostics-fixture-1", data_quality: { level: "limited", reasons: ["Stale market observations and incompatible common-share equity remain disclosed."] },
      coverage: { eligible_count: contributes.length, applicable_count: 9, contributing_count: contributes.length, contributing_models: contributes, method_family_count: families.length, families,
        excluded_models: scenario.models.filter((model) => !contributes.includes(model.id)).map((model) => ({ model_id: model.id, status: model.status, reason: model.eligibility.reason, missing_inputs: model.eligibility.missing_inputs, input_paths: model.eligibility.input_paths })) },
      aggregation: { methodology_version: "group-aware-fixture-1", method: "Weighted average of valid enabled models; unavailable models contribute no value.", weight_source: Object.keys(request.weights ?? {}).length ? "mixed" : "default", per_model_weight_sources: Object.fromEntries(contributes.map((id) => [id, Object.hasOwn(request.weights ?? {}, id) ? "user" : "default"])),
        estimate_range: contributes.length > 1 ? { minimum: 650.125, maximum: 777.77 } : null, dispersion: { status: contributes.length > 1 ? "moderate" : "unavailable", relative_spread: contributes.length > 1 ? 0.164115 : null }, shared_assumptions: mode === "correlated" ? [{ key: "forward_eps", model_ids: contributes }] : [], warnings } };
  }
  response.data_completeness = completeness;
  response.financials = { facts: { revenue: structuredClone(fields["reported.revenue"]) }, reporting_period: completeness.reporting_period };
  response.automatic_evidence = { provider_status: { historical_prices: { status: price == null ? "restricted" : "stale" } } };
  response.enabled_models = request.enabled_models ?? (mode === "none" ? ["pe"] : mode === "single" ? ["pe"] : ["pe", mode === "correlated" ? "peg" : "fcff"]);
  response.configured_weights = { ...response.configured_weights, fcff: 35, peg: 10, ...request.weights };
  return response;
}
