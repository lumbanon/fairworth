// Synthetic transport fixtures, not company observations or financial-model
// expectations. Mathematical verification belongs to independent Python tests.
const definitions = [
  ["fcff", "Discounted Cash Flow (FCFF)", "FCFF DCF"],
  ["fcfe", "Discounted Cash Flow (FCFE)", "FCFE DCF"],
  ["pe", "Forward P/E", "Forward P/E"],
  ["evEbitda", "EV/EBITDA", "EV/EBITDA"],
  ["evRevenue", "EV/Revenue", "EV/Revenue"],
  ["peg", "PEG-Based Valuation", "PEG"],
  ["graham", "Graham Number", "Graham number"],
  ["dividend", "Dividend Discount Model", "Dividend discount"],
  ["residual", "Residual Income Model", "Residual income"],
  ["pb", "Price-to-Book", "Price-to-book"],
  ["affo", "REIT AFFO Valuation", "REIT AFFO"],
];

export function providerValuationFixture(ticker = "MSFT", {
  request = {}, price = 100, missingShares = false, fairValue = 165,
  forceActive = false, currency = "USD", sensitivityValue = 432.10,
} = {}) {
  const active = forceActive || Number.isFinite(request.assumptions?.earnings_growth) && Number.isFinite(request.assumptions?.target_pe);
  const manual = request.manual_market_price;
  const comparison = manual?.value ?? price;
  const defaults = Object.fromEntries(["bear", "base", "bull"].map((name) => {
    const values = { earnings_growth: null, forward_eps: null, target_pe: null, shares: missingShares ? null : 12000000 };
    const metadata = Object.fromEntries(Object.entries(values).map(([key, value]) => [key, {
      value, unit: key === "earnings_growth" ? "fraction" : key === "target_pe" ? "multiple" : key === "shares" ? "shares" : `${currency}/share`,
      source_type: value == null ? "unavailable" : "derived_estimate",
      source_description: key === "shares" && value != null ? "Reported same-period diluted weighted shares; current shares unavailable." : "A supported user input is required; history is insufficient.",
      observation_period: "FY2025", derivation_method: "Synthetic API response fixture", editable: true, overridden: false, warnings: [],
    }]));
    return [name, { values, metadata }];
  }));
  const weights = request.weights ?? Object.fromEntries(definitions.map(([id]) => [id, id === "pe" ? 70 : 0]));
  const enabled = request.enabled_models ?? ["pe"];
  const contributes = active && !missingShares && (weights.pe ?? 0) > 0 && enabled.includes("pe");
  const scenarios = Object.fromEntries(["bear", "base", "bull"].map((name) => {
    const sceneValue = name === "base" ? fairValue : name === "bear" ? 145 : 195;
    const custom = request.scenario_overrides?.[name] ?? {};
    const values = { ...defaults[name].values, ...(name === "base" ? request.assumptions : custom) };
    const metadata = Object.fromEntries(Object.entries(defaults[name].metadata).map(([key, value]) => [key, { ...value, value: values[key], overridden: Object.hasOwn(name === "base" ? request.assumptions ?? {} : custom, key) }]));
    const models = definitions.map(([id, modelName, shortName]) => {
      const valid = id === "pe" && active && !missingShares;
      const missing = id === "pe" ? missingShares ? ["shares", "compatible_earnings_basis"] : active ? [] : ["earnings_growth", "target_pe"] : ["supported_financial_inputs"];
      const reason = missingShares && id === "pe" ? "A same-period net income, diluted weighted share count and compatible EPS basis are required." : id === "fcff" ? "Unlevered cash flows require D&A, working capital and a complete enterprise bridge; ordinary FCF is not FCFF." : id === "pe" ? "Forward earnings and a supported target multiple are required." : "This synthetic provider response has no supported inputs for this model.";
      return { id, name: modelName, short_name: shortName, status: valid ? "valid" : "unavailable", fair_value: valid ? sceneValue : null,
        upside: valid && comparison ? 37.25 : null, warnings: [], details: {},
        eligibility: { status: id === "pe" ? missingShares ? "unavailable" : valid ? "eligible" : "available_with_warnings" : "ineligible", reason, reason_codes: [], required_inputs: id === "pe" ? ["forward_eps", "target_pe"] : missing, missing_inputs: missing, warnings: [] },
      };
    });
    return [name, { models, assumptions: { values, metadata },
      summary: { fair_value: contributes ? sceneValue : null, upside: contributes && comparison ? 65 : null, margin_of_safety: contributes && comparison ? 39.393939 : null, effective_weights: contributes ? { pe: 1 } : {}, count: contributes ? 1 : 0, warnings: contributes ? ["Single-model estimate; independent confirmation is unavailable."] : [] },
      confidence: { level: "low", breakdown: { coverage: "One supported earnings model." }, warnings: [] },
    }];
  }));
  return {
    engine_version: "4.0.0-fixture", calculated_at: "2026-10-14T10:00:00Z", ticker, currency,
    company: { ticker, name: "API Fixture Corporation" }, financials: {}, defaults, scenarios,
    configured_weights: weights, suggested_weights: Object.fromEntries(definitions.map(([id]) => [id, id === "pe" ? 70 : 0])), enabled_models: enabled,
    market: { price: comparison, currency, source_type: manual ? "user" : comparison == null ? "unavailable" : "provider", label: manual ? "User-provided market price" : comparison == null ? "Market provider price unavailable" : "Observed provider quote · delayed", provider_price: price, price_timestamp: manual ? null : "2026-01-15T16:00:00Z", provider: manual ? null : "fixture-market", status: manual ? "user_provided" : "stale" },
    reverse_dcf: { status: "unavailable", implied_growth: null, warnings: ["Valid FCFF assumptions are required."], details: { explanation: "Valid FCFF assumptions are required." } },
    sensitivity: contributes && request.sensitivity ? { model_id: request.sensitivity.model_id, x_parameter: request.sensitivity.x_parameter, y_parameter: request.sensitivity.y_parameter,
      x_values: [13, 14, 15, 16, 17], y_values: [9, 10, 11, 12, 13], rows: [9, 10, 11, 12, 13].map((y_value) => ({ y_value, cells: [13, 14, 15, 16, 17].map((x_value) => ({ x_value, fair_value: sensitivityValue, status: "valid", warnings: [] })) })), unit: `${currency}/share`, warnings: [] } : null,
    warnings: [], confidence: { level: "low", breakdown: { coverage: "One model is not independent multi-model confirmation." } },
  };
}

// Phase 4.5 transport coverage uses deliberately synthetic server outputs.
// These values test UI provenance and request handling, not valuation formulas.
export function automaticProviderValuationFixture(ticker = "MSFT", options = {}) {
  const request = options.request ?? {};
  const response = providerValuationFixture(ticker, { ...options, request, forceActive: true, fairValue: options.fairValue ?? 777.77 });
  const automatic = {
    earnings_growth: { value: 0.08, unit: "fraction", source_type: "historical_estimate", source_category: "derived_historical_estimate", source_provider: "SEC EDGAR", evidence_type: "estimate", source_description: "Comparable synthetic fiscal EPS history informs a disclosed forward estimate.", observation_date: "2026-02-10", financial_period: { start: "2021-12-31", end: "2025-12-31" }, derivation_formula: "Aligned annual EPS CAGR; financial basis verified by the synthetic provider.", quality: { level: "medium", warnings: [] }, source_identifiers: ["fixture:eps:2025"], editable: true },
    forward_eps: { value: 10.8, unit: "USD/share", source_type: "derived_estimate", source_category: "derived_historical_estimate", source_provider: "SEC EDGAR", evidence_type: "estimate", source_description: "Forward EPS is regenerated from current growth assumptions; it is not trailing EPS.", observation_date: "2026-02-10", financial_period: "FY2025", derivation_formula: "Compatible reported EPS × (1 + forward earnings growth)", quality: { level: "medium", warnings: [] }, source_identifiers: ["fixture:eps:2025"], computed_only: true, editable: true },
    target_pe: { value: 22.5, unit: "multiple", source_type: "historical_estimate", source_category: "historical_company_valuation", source_provider: "FMP + SEC EDGAR", evidence_type: "estimate", source_description: "Historical company valuation from a synthetic matched price and earnings series.", observation_date: "2026-01-15", financial_period: { start: "2021-12-31", end: "2025-12-31" }, derivation_formula: "Median of valid, filing-date-aligned historical P/E observations", quality: { level: "medium", warnings: ["Historical multiples are evidence, not a guarantee of fair value."] }, source_identifiers: ["fixture:historical-multiple:2025-12-31"], editable: true },
    cost_of_equity: { value: 0.1, unit: "fraction", source_type: "benchmark_assumption", source_category: "research_policy", source_provider: "Fairworth research policy", evidence_type: "policy", source_description: "Illustrative configurable required return, not an observed company rate.", observation_date: null, financial_period: null, derivation_formula: "Documented illustrative policy", quality: { level: "low", warnings: ["Calibrate company risk before relying on this policy."] }, editable: true },
    beta: { value: 1.2, unit: "ratio", source_type: "derived_estimate", source_category: "market_estimate", source_provider: "FMP", evidence_type: "estimate", source_description: "Synthetic sourced beta observation; not fabricated from a missing value.", observation_date: "2026-01-15", derivation_formula: "Provider-documented market return regression", quality: "moderate", editable: false },
    preferred_equity: { value: 0, unit: "USD", source_type: "reported_input", source_category: "sec_reported_fact", source_provider: "SEC EDGAR", evidence_type: "fact", input_status: "verified_zero", source_description: "Synthetic filing evidence verifies the zero claim; missing is not zero.", observation_date: "2026-02-10", financial_period: "FY2025", derivation_formula: "Reported preferred claim", quality: { level: "medium", warnings: [] }, editable: true },
  };
  for (const name of ["bear", "base", "bull"]) {
    const defaultMetadata = { ...response.defaults[name].metadata, ...structuredClone(automatic) };
    const defaultValues = Object.fromEntries(Object.entries(defaultMetadata).map(([key, metadata]) => [key, metadata.computed_only ? null : metadata.value]));
    response.defaults[name] = { values: defaultValues, metadata: defaultMetadata };
    const overrides = { ...request.assumptions, ...request.scenario_overrides?.[name] };
    const metadata = structuredClone(defaultMetadata);
    if (overrides.earnings_growth === 0.12) metadata.forward_eps.value = 12.34;
    for (const [field, value] of Object.entries(overrides)) {
      metadata[field] = { ...(metadata[field] ?? {}), value, overridden: true, evidence_type: "user", source_type: "user_input", source_category: "user_override", source_provider: "User", source_description: "Explicit synthetic analyst override; not a provider financial fact.", input_status: "user_supplied", computed_only: false };
    }
    const scenario = response.scenarios[name];
    scenario.assumptions = { values: { ...defaultValues, ...overrides }, metadata };
    const classification = Object.keys(overrides).length ? "user_defined" : "evidence_supported";
    const pe = scenario.models.find((model) => model.id === "pe");
    pe.classification = classification;
    pe.classification_reasons = ["The server classifies this synthetic estimate from the effective assumption sources."];
    pe.source_quality = { level: "medium", warnings: ["One earnings model is not independent multi-model confirmation."], categories: ["derived_historical_estimate", "historical_company_valuation"] };
    for (const model of scenario.models.filter((model) => model.id !== "pe")) model.classification = "unavailable";
    scenario.summary.classification = scenario.summary.count ? classification : "unavailable";
    scenario.summary.composition = scenario.summary.count ? [{ classification, weight: 1, model_ids: ["pe"] }] : [];
    scenario.summary.source_warnings = ["The synthetic historical multiple requires economic relevance review."];
  }
  response.assumption_methodology_version = "automatic-assumptions-fixture-1";
  response.snapshot_dates = { financial_period: "2025-12-31", market_observation: response.market.price_timestamp };
  response.source_identifiers = ["fixture:financial-snapshot:2025", "fixture:historical-multiple:2025-12-31"];
  return response;
}
