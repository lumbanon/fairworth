// Presentation adapter only: every Provider valuation number comes from Python.
// Reported statement values continue to use the separate financial-fact adapter.
export const providerModelIds = ["fcff", "fcfe", "pe", "evEbitda", "evRevenue", "peg", "graham", "dividend", "residual", "pb", "affo"];
export const providerScenarioNames = ["bear", "base", "bull"];
export const providerEditableAssumptions = new Set([
  "revenue_growth", "earnings_growth", "cash_flow_growth", "dividend_growth", "wacc", "cost_of_equity",
  "target_pe", "target_ev_ebitda", "target_ev_revenue", "target_peg", "target_pb", "target_p_affo",
  "book_value_meaningful", "common_equity_basis_confirmed", "clean_surplus_confirmed", "stable_dividend_confirmed", "share_basis_confirmed", "affo_basis_confirmed", "is_bank", "is_reit", "growth_fade_to_terminal",
  "forward_eps", "forecast_revenue", "forecast_ebitda", "fcff", "fcfe", "net_borrowing", "change_nwc", "preferred_equity", "minority_interest", "other_nonoperating_assets", "debt", "cash", "book_equity", "affo", "forecast_affo", "dividend_per_share", "capex", "depreciation_and_amortization", "ebit", "net_income",
  "operating_margin", "net_margin", "ebitda_margin", "tax_rate", "capex_ratio", "da_ratio", "nwc_ratio", "return_on_equity", "terminal_roe", "payout_ratio", "reinvestment_rate",
  "projected_fcff", "projected_fcfe", "projected_dividends", "terminal_growth", "forecast_years", "shares", "lookback_years",
]);

const formulas = {
  fcff: "PV(EBIT × (1 − tax) + D&A − capex − ΔNWC) + PV(terminal FCFF), then the enterprise-to-equity bridge, divided by shares.",
  fcfe: "PV(net income + D&A − capex − ΔNWC + net borrowing) + PV(terminal FCFE), divided by shares. No second debt adjustment.",
  pe: "Forward EPS × justified target P/E.",
  evEbitda: "Forecast EBITDA × target EV/EBITDA, then the enterprise-to-equity bridge, divided by shares.",
  evRevenue: "Forecast revenue × target EV/revenue, then the enterprise-to-equity bridge, divided by shares.",
  peg: "Forward EPS × target PEG × earnings growth in percentage points.",
  graham: "√(22.5 × positive reported EPS × positive book value per share).",
  dividend: "Next dividend per share / (cost of equity − perpetual dividend growth).",
  residual: "Beginning book equity + PV(earnings above the equity capital charge) + PV(terminal residual income), divided by shares.",
  pb: "Meaningful book value per share × justified target P/B.",
  affo: "Reliable forecast AFFO per share × justified target P/AFFO.",
};

function strings(values = []) {
  return values.map((value) => typeof value === "string" ? value : value.message).filter(Boolean);
}

export function adaptProviderValuation(response, expectedTicker) {
  if (!response?.scenarios?.base?.summary || !Array.isArray(response.scenarios.base.models))
    throw new Error("The valuation service returned an incomplete Python calculation response.");
  const canonicalTicker = (value) => String(value ?? "").toUpperCase().replaceAll(".", "-");
  if (expectedTicker && canonicalTicker(response.company?.ticker) !== canonicalTicker(expectedTicker))
    throw new Error("The Python valuation response does not match the requested company.");
  const scenarios = Object.fromEntries(providerScenarioNames.map((name) => {
    const scenario = response.scenarios[name];
    if (!scenario?.summary || !Array.isArray(scenario.models))
      throw new Error(`The valuation service omitted the ${name} scenario.`);
    const results = scenario.models.map((model) => {
      if (model.fair_value != null && !Number.isFinite(model.fair_value))
        throw new Error("The Python valuation response contains a nonfinite model result.");
      const eligibility = model.eligibility ?? {};
      const warnings = [...new Set([
        ...strings(model.warnings),
        ...strings(eligibility.warnings),
        ...(eligibility.reason ? [eligibility.reason] : []),
        ...(eligibility.missing_inputs?.length ? [`Missing inputs: ${eligibility.missing_inputs.join(", ")}.`] : []),
      ])];
      return {
        id: model.id,
        name: model.name,
        shortName: model.short_name || model.name,
        fairValue: model.fair_value ?? null,
        upside: model.upside ?? null,
        status: model.status === "valid" ? "valid" : model.status === "invalid_input" ? "invalid-input" : eligibility.status === "ineligible" ? "not-applicable" : "insufficient-data",
        applicable: eligibility.status !== "ineligible",
        warnings,
        details: model.details ?? {},
        eligibility,
        definition: {
          id: model.id,
          name: model.name,
          description: eligibility.reason || "Python determines suitability from the financial basis and available inputs.",
          formula: formulas[model.id] || "See the Python calculation explanation.",
          condition: eligibility.reason || eligibility.status || "Review required financial inputs.",
          requiredInputs: eligibility.required_inputs ?? [],
        },
      };
    });
    return [name, {
      results,
      summary: {
        fairValue: scenario.summary.fair_value ?? null,
        upside: scenario.summary.upside ?? null,
        marginOfSafety: scenario.summary.margin_of_safety ?? null,
        normalizedWeights: scenario.summary.effective_weights ?? {},
        count: scenario.summary.count ?? 0,
        warnings: strings(scenario.summary.warnings),
      },
      metadata: scenario.assumptions?.metadata ?? {},
      values: scenario.assumptions?.values ?? {},
      confidence: scenario.confidence,
    }];
  }));
  const reverse = response.reverse_dcf ?? {};
  return {
    scenarios,
    defaults: response.defaults ?? {},
    suggestedWeights: response.suggested_weights ?? {},
    configuredWeights: response.configured_weights ?? {},
    enabledModels: response.enabled_models ?? [],
    market: response.market ?? { price: null, source_type: "unavailable" },
    comparisonPrice: response.market?.price ?? null,
    sensitivity: response.sensitivity,
    confidence: response.confidence,
    warnings: strings(response.warnings),
    reverseDCF: {
      status: reverse.status,
      impliedGrowth: reverse.implied_growth,
      warnings: strings(reverse.warnings),
      explanation: reverse.details?.explanation || reverse.solver?.reason || strings(reverse.warnings).join(" "),
      solvedVariable: (reverse.solved_variable || reverse.details?.solved_variable)?.replaceAll("_", " "),
      bounds: reverse.solver?.bounds || reverse.details?.bounds,
      convergence: reverse.solver?.status || reverse.details?.convergence_status,
      heldConstants: reverse.held_constants ?? {},
      details: reverse.details,
    },
    engineVersion: response.engine_version,
    currency: response.currency,
    calculatedAt: response.calculated_at,
  };
}

export function emptyProviderValuation() {
  return {
    scenarios: Object.fromEntries(providerScenarioNames.map((name) => [name, {
      results: [],
      summary: { fairValue: null, upside: null, marginOfSafety: null, normalizedWeights: {}, count: 0, warnings: [] },
      values: {}, metadata: {},
    }])),
    defaults: {}, suggestedWeights: {}, configuredWeights: {}, enabledModels: [],
    market: { price: null, source_type: "unavailable" }, comparisonPrice: null,
    sensitivity: null, reverseDCF: null, warnings: [],
  };
}

export function providerInputErrors(assumptions, scenarios, weights, manualPrice) {
  const errors = [];
  for (const [scenario, values] of Object.entries({ assumptions, ...scenarios })) {
    for (const [key, value] of Object.entries(values)) {
      if (value === "" || (typeof value !== "boolean" && (!Number.isFinite(value) && !Array.isArray(value))))
        errors.push(`${scenario}: ${key.replaceAll("_", " ")} requires a finite input.`);
      if (Array.isArray(value) && (!value.length || value.length > 30 || !value.every(Number.isFinite)))
        errors.push(`${scenario}: ${key.replaceAll("_", " ")} requires 1–30 finite annual values.`);
    }
  }
  for (const [id, weight] of Object.entries(weights ?? {}))
    if (!Number.isFinite(weight) || weight < 0 || weight > 1000)
      errors.push(`${id}: model weight must be between 0 and 1000.`);
  if (manualPrice !== null && (!Number.isFinite(manualPrice) || manualPrice <= 0))
    errors.push("User-provided market price must be positive and finite.");
  return errors;
}
