// Statement presentation uses millions; API facts retain absolute units.
// Provider valuations use the Python response adapter, never these display units.
const metricNames = {
  revenue: ["revenue"],
  costOfRevenue: ["cost_of_revenue"],
  grossProfit: ["gross_profit"],
  operatingIncome: ["operating_income"],
  pretaxIncome: ["pretax_income"],
  incomeTaxExpense: ["income_tax_expense"],
  netIncome: ["net_income"],
  basicEPS: ["basic_eps", "eps_basic"],
  eps: ["diluted_eps", "eps_diluted"],
  shares: [
    "weighted_average_diluted_shares",
    "weighted_average_shares_diluted",
    "diluted_weighted_average_shares",
  ],
  cash: ["cash_and_cash_equivalents", "cash"],
  shortTermInvestments: ["short_term_investments"],
  currentAssets: ["total_current_assets", "current_assets"],
  assets: ["total_assets", "assets"],
  shortTermDebt: ["short_term_debt"],
  longTermDebt: ["long_term_debt"],
  debt: ["total_debt"],
  liabilities: ["total_liabilities", "liabilities"],
  bookEquity: ["shareholders_equity", "stockholders_equity"],
  sharesOutstanding: ["shares_outstanding"],
  operatingCashFlow: ["operating_cash_flow"],
  capex: ["capital_expenditures", "capex"],
  freeCashFlow: ["free_cash_flow"],
  depreciation: ["depreciation_and_amortization"],
  dividends: ["dividends_paid"],
  repurchases: ["share_repurchases"],
};

function metric(values, aliases) {
  for (const key of aliases) {
    if (typeof values[key] === "number" && Number.isFinite(values[key]))
      return values[key];
  }
  return null;
}

function periodKey(period) {
  return `${period.start_date ?? ""}/${period.end_date ?? ""}/${period.fiscal_period ?? ""}`;
}

export function adaptFinancialPeriod(period, derived = {}) {
  const fields = period.metrics ?? {};
  const result = {
    year: period.fiscal_year,
    fiscalPeriod: period.fiscal_period,
    periodStart: period.start_date,
    periodEnd: period.end_date,
    provenance: period.provenance ?? {},
    rawMetrics: fields,
    revenueGrowth:
      metric(derived, ["revenue_growth"]) == null
        ? null
        : derived.revenue_growth * 100,
    // FCF is not FCFE, and a fixed demonstration tax rate cannot create FCFF.
    fcff: null,
    fcfe: null,
    ebitda: null,
    affo: null,
  };
  for (const [key, aliases] of Object.entries(metricNames)) {
    const value = metric(fields, aliases);
    result[key] =
      value == null || ["eps", "basicEPS"].includes(key) ? value : value / 1e6;
  }
  for (const [key, source] of Object.entries({
    grossMargin: "gross_margin",
    operatingMargin: "operating_margin",
    netProfitMargin: "net_profit_margin",
    freeCashFlowMargin: "free_cash_flow_margin",
    reportedROE: "return_on_equity",
    historicalEPSGrowth: "historical_eps_growth",
    historicalFreeCashFlowGrowth: "historical_free_cash_flow_growth",
  })) {
    const value = metric(derived, [source]);
    result[key] = value == null ? null : value * 100;
  }
  result.debtToEquity = metric(derived, ["debt_to_equity"]);
  const netDebt = metric(derived, ["net_debt"]);
  result.netDebt = netDebt == null ? null : netDebt / 1e6;
  return result;
}

function collectWarnings(...responses) {
  const unique = new Map();
  for (const response of responses) {
    for (const warning of response?.warnings ?? []) {
      const normalized =
        typeof warning === "string" ? { message: warning } : warning;
      unique.set(
        `${normalized.field ?? ""}|${normalized.code ?? ""}|${normalized.message}`,
        normalized,
      );
    }
  }
  return [...unique.values()];
}

export function adaptProviderStock({
  profile,
  annual,
  quarterly,
  metrics,
  dataStatus,
  coverage,
  requestWarnings = [],
}) {
  if (!profile?.company || (annual != null && !Array.isArray(annual.periods)))
    throw new Error(
      "The financial data service returned an incomplete company response.",
    );
  const sourceCompany = profile.company;
  const metricPeriods = new Map(
    (metrics?.periods ?? []).map((period) => [
      periodKey(period),
      period.metrics ?? {},
    ]),
  );
  function periods(response) {
    return [...(response?.periods ?? [])]
      .sort((a, b) => String(a.end_date).localeCompare(String(b.end_date)))
      .map((period) =>
        adaptFinancialPeriod(period, metricPeriods.get(periodKey(period))),
      );
  }
  const financials = periods(annual);
  const quarterlyFinancials = periods(quarterly);
  const latest = financials.at(-1) ?? adaptFinancialPeriod({ metrics: {} });
  const market = profile.market;
  const currency = annual?.currency ?? sourceCompany.currency;
  const warnings = collectWarnings(
    profile,
    market,
    annual,
    quarterly,
    metrics,
    dataStatus,
    { warnings: requestWarnings },
  );
  for (const [field, response] of [
    ["company", profile],
    ["annual", annual],
    ["quarterly", quarterly],
    ["metrics", metrics],
  ]) {
    if (["stale", "partial", "unavailable"].includes(response?.status))
      warnings.push({
        field,
        code: `source_${response.status}`,
        message: `The ${field} response is ${response.status}; consult its source dates and missing-field notices.`,
      });
  }
  const modelCompatibility = {};
  const shareClassUnknown =
    sourceCompany.has_multiple_share_classes == null &&
    /[.-][A-Z]$/.test(sourceCompany.ticker);
  if (sourceCompany.has_multiple_share_classes === true || shareClassUnknown) {
    const message =
      "Issuer-wide SEC earnings and share counts have not been verified for this ticker’s share class. Python checks each model’s required share basis; no share-class conversion is assumed.";
    modelCompatibility.all = message;
    warnings.push({
      field: "shares",
      code: "unverified_share_class_basis",
      message,
    });
  }
  const latestYearPeriods = financials.filter(
    (period) => period.year === latest.year,
  );
  if (
    new Set(
      latestYearPeriods.map(
        (period) => `${period.periodStart}/${period.periodEnd}`,
      ),
    ).size > 1
  ) {
    const message = `More than one distinct annual reporting period is available for FY${latest.year}. A single compatible valuation basis cannot be selected.`;
    modelCompatibility.all = message;
    warnings.push({
      field: "fiscal_period",
      code: "ambiguous_annual_basis",
      message,
    });
  }
  const equitySources =
    latest.provenance.shareholders_equity ??
    latest.provenance.stockholders_equity ??
    [];
  if (
    (Array.isArray(equitySources) ? equitySources : [equitySources]).some(
      (source) =>
        String(source.concept ?? source.original_concept ?? "").includes(
          "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ),
    )
  ) {
    const message =
      "Reported book equity includes noncontrolling interests. A compatible common-share equity basis needs verification for book-value methods.";
    for (const id of ["pb", "residual", "graham"])
      modelCompatibility[id] = message;
    warnings.push({
      field: "shareholders_equity",
      code: "incompatible_common_equity_basis",
      message,
    });
  }
  if (latest.shares == null || latest.netIncome == null || latest.eps == null) {
    const message =
      "A same-period net income, diluted weighted share count, and reported diluted EPS are required to check the earnings basis.";
    for (const id of ["pe", "peg", "graham"]) modelCompatibility[id] = message;
  } else if (
    Math.abs(latest.netIncome / latest.shares - latest.eps) >
    0.02
  ) {
    const message =
      "Reported diluted EPS does not reconcile with net income divided by diluted weighted shares. Python validates the model-specific earnings basis before using historical per-share estimates.";
    for (const id of ["pe", "peg", "graham"]) modelCompatibility[id] = message;
    warnings.push({
      field: "diluted_eps",
      code: "incompatible_earnings_basis",
      message,
    });
  }
  const incompatibleFinancialUnits = (annual?.periods ?? []).some((period) =>
    Object.entries(period.provenance ?? {}).some(([field, sources]) => {
      const expectedUnit = field.includes("shares") ? "shares" : field.includes("eps") ? `${currency}/shares` : currency;
      return Array.isArray(sources) && sources.some((source) => source.unit != null && source.unit !== expectedUnit);
    }),
  );
  if (
    !/^[A-Z]{3}$/.test(currency ?? "") ||
    incompatibleFinancialUnits ||
    (market?.price != null && market.currency !== currency)
  ) {
    modelCompatibility.all =
      "Financial and market currencies are unavailable or incompatible. Python validates intrinsic-value units and comparison-price currency separately; no currency conversion is invented.";
    warnings.push({
      field: "currency",
      code: "incompatible_currency",
      message: modelCompatibility.all,
    });
  }
  return {
    ticker: sourceCompany.ticker,
    displaySymbol: coverage?.identity?.display_symbol ?? sourceCompany.display_symbol ?? sourceCompany.ticker,
    instrumentId: sourceCompany.instrument_id ?? coverage?.identity?.instrument_id ?? null,
    listingId: sourceCompany.listing_id ?? coverage?.identity?.listing_id ?? null,
    issuerId: sourceCompany.issuer_id ?? coverage?.identity?.issuer_id ?? null,
    identity: { ...sourceCompany, ...(coverage?.identity ?? {}) },
    instrumentType: sourceCompany.instrument_type ?? coverage?.identity?.instrument_type,
    securityForm: coverage?.identity?.security_form ?? sourceCompany.security_form,
    issuerBusinessCategory: coverage?.identity?.issuer_business_category ?? sourceCompany.issuer_business_category,
    listingVerification: coverage?.identity?.listing_verification ?? sourceCompany.listing_verification,
    shareClass: sourceCompany.share_class ?? coverage?.identity?.share_class,
    listingStatus: sourceCompany.listing_status ?? coverage?.identity?.listing_status,
    identityStatus: sourceCompany.identity_status ?? coverage?.identity?.identity_status,
    adrMetadata: sourceCompany.adr_metadata ?? coverage?.identity?.adr_metadata ?? {},
    coverage,
    companyName: sourceCompany.name,
    exchange: sourceCompany.exchange,
    sector: sourceCompany.sector,
    industry: sourceCompany.industry,
    description: sourceCompany.description,
    cik: sourceCompany.cik,
    currency,
    dataMode: "provider",
    isBank:
      typeof sourceCompany.is_bank === "boolean" ? sourceCompany.is_bank : null,
    isREIT:
      typeof sourceCompany.is_reit === "boolean" ? sourceCompany.is_reit : null,
    stableDividend: sourceCompany.stable_dividend === true,
    grahamSuitable: sourceCompany.graham_suitable === true,
    otherClaims: null,
    price:
      typeof market?.price === "number" &&
      Number.isFinite(market.price) &&
      market.price > 0
        ? market.price
        : null,
    marketCap:
      typeof market?.market_cap === "number" &&
      Number.isFinite(market.market_cap)
        ? market.market_cap / 1e6
        : null,
    market,
    latest,
    financials,
    quarterlyFinancials,
    dataStatus,
    profileStatus: profile.status,
    financialStatus: annual?.status ?? "unavailable",
    warnings,
    modelCompatibility,
    sourceReferences: [
      ...(profile.source_references ?? []),
      ...(annual?.source_references ?? []),
    ],
    financialRetrievedAt: annual?.retrieved_at,
    updatedLabel: latest.periodEnd
      ? `Latest annual period ended ${latest.periodEnd}`
      : "Annual financial statements unavailable",
  };
}
