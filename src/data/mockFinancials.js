// Entirely fictional, distinct FY2023–FY2025 datasets. USD millions; shares millions.
// Array columns: year, revenue, gross margin, operating margin, net income, cash,
// debt, assets, liabilities, operating cash flow, capex, D&A, interest, shares,
// dividends paid, AFFO (REIT only). No external data is represented here.
function statements(rows, bank = false) {
  return rows.map(
    ([
      year,
      revenue,
      grossMargin,
      operatingMargin,
      netIncome,
      cash,
      debt,
      assets,
      liabilities,
      operatingCashFlow,
      capex,
      depreciation,
      interestExpense,
      shares,
      dividends,
      affo,
    ]) => {
      const freeCashFlow = operatingCashFlow - capex
      return {
        year,
        revenue,
        grossProfit: bank ? null : revenue * grossMargin,
        operatingIncome: revenue * operatingMargin,
        netIncome,
        eps: netIncome / shares,
        cash,
        debt,
        assets,
        liabilities,
        bookEquity: assets - liabilities,
        operatingCashFlow,
        capex,
        depreciation,
        interestExpense,
        shares,
        dividends,
        affo: affo ?? null,
        freeCashFlow,
        fcfe: freeCashFlow,
        fcff: freeCashFlow + interestExpense * 0.79,
        ebitda: bank ? null : revenue * operatingMargin + depreciation,
      }
    },
  )
}

const stocks = [
  {
    ticker: 'MSFT',
    name: 'Microsoft',
    companyName: 'Microsoft Corporation',
    exchange: 'NASDAQ',
    sector: 'Technology',
    industry: 'Software',
    description:
      'A diversified software and cloud business. This fictional dataset illustrates a profitable company with recurring revenue and positive cash flow.',
    profile: 'Mature technology',
    price: 420,
    rows: [
      [
        2023, 220000, 0.68, 0.4, 78000, 70000, 60000, 410000, 220000, 100000,
        28000, 13000, 2800, 7500, 21000,
      ],
      [
        2024, 245000, 0.69, 0.41, 86000, 76000, 62000, 460000, 240000, 116000,
        34000, 15000, 2900, 7450, 23000,
      ],
      [
        2025, 270000, 0.7, 0.42, 96000, 80000, 65000, 510000, 260000, 130000,
        40000, 16000, 3000, 7400, 25000,
      ],
    ],
    growth: 0.11,
    cashGrowth: 0.1,
    epsGrowth: 0.12,
    multiples: [32, 23, 10.5],
  },
  {
    ticker: 'AAPL',
    name: 'Apple',
    companyName: 'Apple Inc.',
    exchange: 'NASDAQ',
    sector: 'Technology',
    industry: 'Consumer electronics',
    description:
      'A consumer hardware and services business. The demonstration assumes substantial free cash flow and a comparatively small book-equity base.',
    profile: 'Mature technology',
    price: 225,
    rows: [
      [
        2023, 365000, 0.44, 0.29, 91000, 54000, 110000, 350000, 290000, 102000,
        11000, 11000, 3800, 15700, 14500,
      ],
      [
        2024, 382000, 0.45, 0.3, 96000, 57000, 108000, 360000, 298000, 107000,
        11500, 11500, 3600, 15300, 15000,
      ],
      [
        2025, 400000, 0.46, 0.31, 102000, 60000, 105000, 370000, 302000, 112000,
        12000, 12000, 3500, 15000, 15500,
      ],
    ],
    growth: 0.055,
    cashGrowth: 0.06,
    epsGrowth: 0.07,
    multiples: [28, 22, 7.5],
  },
  {
    ticker: 'NVDA',
    name: 'NVIDIA',
    companyName: 'NVIDIA Corporation',
    exchange: 'NASDAQ',
    sector: 'Technology',
    industry: 'Semiconductors',
    description:
      'A semiconductor and accelerated-computing business. This demonstration uses high margins and rapid growth, with substantial forecasting uncertainty.',
    profile: 'Profitable growth',
    price: 135,
    rows: [
      [
        2023, 62000, 0.68, 0.45, 30000, 27000, 12000, 65000, 25000, 33000, 3000,
        2200, 350, 25000, 400,
      ],
      [
        2024, 102000, 0.71, 0.52, 52000, 42000, 11500, 92000, 31000, 56000,
        4500, 2700, 330, 24700, 600,
      ],
      [
        2025, 140000, 0.73, 0.55, 70000, 58000, 11000, 125000, 39000, 76000,
        6000, 3300, 300, 24500, 800,
      ],
    ],
    growth: 0.25,
    cashGrowth: 0.24,
    epsGrowth: 0.28,
    multiples: [38, 30, 16],
    wacc: 0.105,
  },
  {
    ticker: 'GOOG',
    name: 'Alphabet',
    companyName: 'Alphabet Inc.',
    exchange: 'NASDAQ',
    sector: 'Communication services',
    industry: 'Internet services',
    description:
      'A digital advertising, cloud, and internet-services business. The fictional statements include a net-cash balance sheet and growing infrastructure investment.',
    profile: 'Mature technology',
    price: 185,
    rows: [
      [
        2023, 305000, 0.56, 0.28, 85000, 88000, 26000, 410000, 120000, 98000,
        37000, 13000, 700, 12600, 0,
      ],
      [
        2024, 337000, 0.57, 0.3, 97000, 93000, 28000, 445000, 132000, 112000,
        46000, 14000, 750, 12300, 2000,
      ],
      [
        2025, 370000, 0.58, 0.32, 110000, 98000, 30000, 485000, 145000, 128000,
        55000, 15000, 800, 12000, 5000,
      ],
    ],
    growth: 0.1,
    cashGrowth: 0.11,
    epsGrowth: 0.13,
    multiples: [23, 18, 6.5],
  },
  {
    ticker: 'AMZN',
    name: 'Amazon',
    companyName: 'Amazon.com, Inc.',
    exchange: 'NASDAQ',
    sector: 'Consumer discretionary',
    industry: 'Retail and cloud services',
    description:
      'A retail, logistics, and cloud-services business. This fictional example emphasizes reinvestment needs and the difference between earnings and free cash flow.',
    profile: 'Profitable growth',
    price: 205,
    rows: [
      [
        2023, 540000, 0.45, 0.055, 35000, 72000, 78000, 480000, 290000, 86000,
        57000, 45000, 2600, 10400, 0,
      ],
      [
        2024, 595000, 0.46, 0.065, 47000, 78000, 81000, 530000, 315000, 101000,
        66000, 48000, 2800, 10550, 0,
      ],
      [
        2025, 650000, 0.47, 0.08, 62000, 85000, 85000, 590000, 345000, 116000,
        75000, 50000, 3000, 10700, 0,
      ],
    ],
    growth: 0.12,
    cashGrowth: 0.16,
    epsGrowth: 0.2,
    multiples: [35, 20, 3],
    wacc: 0.095,
  },
  {
    ticker: 'TSLA',
    name: 'Tesla',
    companyName: 'Tesla, Inc.',
    exchange: 'NASDAQ',
    sector: 'Consumer discretionary',
    industry: 'Automotive',
    description:
      'An automotive and energy business. This fictional stress-case dataset has negative earnings and free cash flow; only a revenue-based estimate is enabled.',
    profile: 'Unprofitable growth',
    price: 235,
    rows: [
      [
        2023, 92000, 0.2, 0.08, 8500, 27000, 5000, 102000, 42000, 11000, 6500,
        4500, 250, 3200, 0,
      ],
      [
        2024, 98000, 0.15, 0.02, 1800, 29000, 6000, 109000, 47000, 6000, 7000,
        5000, 280, 3250, 0,
      ],
      [
        2025, 105000, 0.1, -0.06, -2000, 30000, 7000, 115000, 52000, 2400, 6000,
        5500, 300, 3300, 0,
      ],
    ],
    growth: 0.18,
    cashGrowth: 0.15,
    epsGrowth: 0.15,
    multiples: [30, 18, 3.5],
    wacc: 0.12,
  },
  {
    ticker: 'ORCL',
    name: 'Oracle',
    companyName: 'Oracle Corporation',
    exchange: 'NYSE',
    sector: 'Technology',
    industry: 'Enterprise software',
    description:
      'An enterprise software and cloud-infrastructure business. The fictional dataset demonstrates the equity-value adjustment for a significant net-debt position.',
    profile: 'Mature technology',
    price: 155,
    rows: [
      [
        2023, 48000, 0.7, 0.3, 10000, 10000, 82000, 140000, 119000, 17000, 5000,
        4000, 3600, 2750, 4200,
      ],
      [
        2024, 54000, 0.71, 0.31, 12000, 12000, 86000, 155000, 128000, 20500,
        6000, 4300, 3800, 2780, 4500,
      ],
      [
        2025, 60000, 0.72, 0.32, 14000, 14000, 90000, 172000, 140000, 24000,
        7000, 4700, 4000, 2800, 4800,
      ],
    ],
    growth: 0.12,
    cashGrowth: 0.13,
    epsGrowth: 0.1,
    multiples: [28, 22, 8],
    wacc: 0.09,
  },
  {
    ticker: 'JPM',
    name: 'JPMorgan Chase',
    companyName: 'JPMorgan Chase & Co.',
    exchange: 'NYSE',
    sector: 'Financials',
    industry: 'Banking',
    description:
      'A diversified banking business. This fictional example uses equity-based valuation because bank funding and regulatory capital make enterprise cash-flow multiples less suitable.',
    profile: 'Bank',
    isBank: true,
    stableDividend: true,
    grahamSuitable: true,
    price: 210,
    rows: [
      [
        2023, 155000, 0, 0.36, 44000, 480000, 320000, 3600000, 3300000, 72000,
        12000, 8000, 42000, 2900, 12500,
      ],
      [
        2024, 168000, 0, 0.38, 50000, 505000, 340000, 3850000, 3525000, 78000,
        13000, 8500, 46000, 2850, 14000,
      ],
      [
        2025, 180000, 0, 0.4, 55000, 530000, 360000, 4100000, 3750000, 85000,
        14000, 9000, 50000, 2800, 15500,
      ],
    ],
    growth: 0.06,
    cashGrowth: 0.05,
    epsGrowth: 0.07,
    multiples: [12, 0, 0],
    costOfEquity: 0.1,
    targetPB: 1.8,
  },
  {
    ticker: 'KO',
    name: 'Coca-Cola',
    companyName: 'The Coca-Cola Company',
    exchange: 'NYSE',
    sector: 'Consumer staples',
    industry: 'Beverages',
    description:
      'A mature branded-beverage business. The fictional example supports cash-flow, earnings, and stable-dividend valuation approaches.',
    profile: 'Mature dividend payer',
    stableDividend: true,
    grahamSuitable: true,
    price: 62,
    rows: [
      [
        2023, 44000, 0.6, 0.27, 10000, 9000, 35000, 90000, 65000, 12000, 2000,
        1900, 1600, 4300, 7400,
      ],
      [
        2024, 47000, 0.61, 0.28, 11000, 10000, 37000, 95000, 67500, 13000, 2200,
        2000, 1700, 4250, 7900,
      ],
      [
        2025, 50000, 0.62, 0.29, 12000, 11000, 39000, 100000, 70000, 14000,
        2400, 2100, 1800, 4200, 8400,
      ],
    ],
    growth: 0.05,
    cashGrowth: 0.055,
    epsGrowth: 0.055,
    multiples: [25, 19, 6],
    wacc: 0.075,
    costOfEquity: 0.08,
    dividendGrowth: 0.04,
  },
  {
    ticker: 'O',
    name: 'Realty Income',
    companyName: 'Realty Income Corporation',
    exchange: 'NYSE',
    sector: 'Real estate',
    industry: 'Net-lease REIT',
    description:
      'A real estate investment trust. This fictional dataset uses AFFO as a cash-earnings proxy; conventional EPS and enterprise multiples are not applied.',
    profile: 'REIT',
    isREIT: true,
    stableDividend: true,
    price: 58,
    rows: [
      [
        2023, 4300, 0.55, 0.25, 600, 900, 21000, 59000, 29000, 3100, 600, 1500,
        700, 820, 2500, 3000,
      ],
      [
        2024, 4900, 0.56, 0.26, 700, 1000, 23000, 64500, 32000, 3500, 700, 1650,
        800, 880, 2850, 3400,
      ],
      [
        2025, 5500, 0.57, 0.27, 800, 1100, 25000, 70000, 35000, 3900, 800, 1800,
        900, 950, 3200, 3800,
      ],
    ],
    growth: 0.05,
    cashGrowth: 0.045,
    epsGrowth: 0.05,
    multiples: [0, 0, 0],
    targetPAFFO: 16,
  },
]

export const mockFinancials = Object.fromEntries(
  stocks.map(({ rows, ...stock }) => {
    const financials = statements(rows, stock.isBank)
    return [
      stock.ticker,
      {
        ...stock,
        financials,
        latest: financials.at(-1),
        otherClaims: 0,
        updatedLabel: 'Fictional FY2025 snapshot · Phase 2',
        quarterly: null,
      },
    ]
  }),
)
