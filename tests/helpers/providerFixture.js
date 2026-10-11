const annualMetrics = {
  revenue: 1400000000,
  cost_of_revenue: 600000000,
  gross_profit: 800000000,
  operating_income: 180000000,
  pretax_income: 160000000,
  income_tax_expense: 40000000,
  net_income: 120000000,
  basic_eps: 10,
  diluted_eps: 10,
  weighted_average_diluted_shares: 12000000,
  cash_and_cash_equivalents: 200000000,
  total_assets: 1000000000,
  total_liabilities: 500000000,
  shareholders_equity: 500000000,
  short_term_debt: 40000000,
  long_term_debt: 60000000,
  total_debt: 100000000,
  shares_outstanding: 12000000,
  operating_cash_flow: 160000000,
  capital_expenditures: 60000000,
  free_cash_flow: 100000000,
  depreciation_and_amortization: null,
  dividends_paid: 20000000,
  share_repurchases: null,
};

export function providerFixture(ticker = "MSFT") {
  const period = {
    fiscal_year: 2025,
    fiscal_period: "FY",
    start_date: "2025-01-01",
    end_date: "2025-12-31",
    metrics: { ...annualMetrics },
    provenance: {
      revenue: [
        {
          concept: "RevenueFromContractWithCustomerExcludingAssessedTax",
          reported_value: 1400000000,
          unit: "USD",
          period_start: "2025-01-01",
          period_end: "2025-12-31",
          filing_date: "2026-02-10",
          accession_number: "0000000001-26-000001",
          form_type: "10-K",
        },
      ],
    },
  };
  const quarter = {
    ...period,
    fiscal_period: "Q1",
    end_date: "2025-03-31",
    metrics: {
      ...annualMetrics,
      revenue: 300000000,
      net_income: 30000000,
      diluted_eps: 2.5,
      basic_eps: 2.5,
      operating_cash_flow: 40000000,
      capital_expenditures: 15000000,
      free_cash_flow: 25000000,
    },
  };
  const warning = {
    field: "price",
    code: "stale_market_price",
    message: "The configured market price is stale; consult its timestamp.",
  };
  return {
    profile: {
      company: {
        ticker,
        name: "API Fixture Corporation",
        cik: "0000000001",
        exchange: "NASDAQ",
        sector: "Technology",
        industry: "Software",
        description:
          "Mocked provider company profile used only by automated tests.",
        currency: "USD",
        is_bank: false,
        is_reit: false,
      },
      market: {
        price: 100,
        currency: "USD",
        exchange: "NASDAQ",
        price_timestamp: "2026-01-15T16:00:00Z",
        market_cap: 1200000000,
        shares_outstanding: 12000000,
        provider: "fixture-market",
        retrieved_at: "2026-02-11T10:00:00Z",
        status: "stale",
        warnings: [warning],
      },
      status: "partial",
      warnings: [warning],
      source_references: [
        { url: "https://www.sec.gov/Archives/edgar/data/1/example.htm" },
      ],
    },
    annual: {
      ticker,
      currency: "USD",
      period: "annual",
      periods: [period],
      retrieved_at: "2026-02-11T10:00:00Z",
      status: "partial",
      warnings: [
        {
          field: "depreciation_and_amortization",
          code: "missing_fact",
          message: "Depreciation and amortization is unavailable.",
        },
      ],
      source_references: [],
    },
    quarterly: {
      ticker,
      currency: "USD",
      period: "quarterly",
      periods: [quarter],
      status: "partial",
      warnings: [],
      source_references: [],
    },
    metrics: {
      ticker,
      periods: [
        {
          ...period,
          metrics: {
            revenue_growth: 1 / 6,
            gross_margin: 4 / 7,
            operating_margin: 180 / 1400,
          },
        },
      ],
      status: "partial",
      warnings: [],
    },
    dataStatus: {
      ticker,
      status: "partial",
      last_financial_update: "2026-02-11T10:00:00Z",
      last_market_update: "2026-01-15T16:00:00Z",
      available_periods: { annual: [period], quarterly: [quarter] },
      missing_fields: ["depreciation_and_amortization"],
      provider_status: {
        financial: { provider: "sec-edgar", status: "partial" },
        market: { provider: "fixture-market", status: "stale" },
      },
      warnings: [warning],
    },
  };
}
