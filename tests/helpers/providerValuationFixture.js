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
