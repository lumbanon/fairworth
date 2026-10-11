export const valuationModels = [
  {
    name: 'Discounted Cash Flow (FCFF)',
    category: 'Cash flow',
    description:
      'Estimates enterprise value by discounting future free cash flow to the firm.',
    suitability:
      'Non-financial companies with reasonably forecastable operating cash flows.',
  },
  {
    name: 'Discounted Cash Flow (FCFE)',
    category: 'Cash flow',
    description:
      'Estimates equity value by discounting future cash flow available to shareholders.',
    suitability: 'Companies with reasonably predictable equity cash flows.',
  },
  {
    name: 'Forward P/E',
    category: 'Multiples',
    description:
      'Estimates share value using projected earnings per share and a justified earnings multiple.',
    suitability: 'Profitable companies.',
  },
  {
    name: 'EV/EBITDA',
    category: 'Multiples',
    description:
      'Estimates enterprise value using EBITDA and a justified enterprise value multiple.',
    suitability: 'Companies with positive and meaningful EBITDA.',
  },
  {
    name: 'EV/Revenue',
    category: 'Multiples',
    description:
      'Estimates enterprise value using revenue and a justified revenue multiple.',
    suitability:
      'Certain high-growth businesses where earnings are less representative.',
  },
  {
    name: 'PEG-Based Valuation',
    category: 'Multiples',
    description:
      'Uses earnings multiples adjusted for expected earnings growth.',
    suitability:
      'Profitable growth companies with reliable growth assumptions.',
  },
  {
    name: 'Graham Number',
    category: 'Equity & income',
    description:
      'A traditional value-investing formula based on earnings per share and book value per share.',
    suitability:
      'Certain mature companies with positive earnings and book value.',
  },
  {
    name: 'Dividend Discount Model',
    category: 'Equity & income',
    description: 'Values equity based on expected future dividend payments.',
    suitability: 'Stable dividend-paying companies.',
  },
  {
    name: 'Residual Income Model',
    category: 'Equity & income',
    description:
      'Estimates equity value using book equity and expected residual earnings.',
    suitability: 'Banks and other financial institutions.',
  },
  {
    name: 'Price-to-Book',
    category: 'Equity & income',
    description:
      'Estimates equity value using book value and an appropriate valuation multiple.',
    suitability: 'Banks and asset-heavy businesses.',
  },
  {
    name: 'REIT AFFO Valuation',
    category: 'Specialized',
    description:
      'Estimates REIT equity value using adjusted funds from operations and an appropriate multiple.',
    suitability: 'Real estate investment trusts.',
  },
  {
    name: 'Reverse DCF',
    category: 'Specialized',
    description:
      'Calculates the future growth or cash flow expectations implied by the current stock price.',
    suitability: 'Evaluating whether market expectations are reasonable.',
  },
]
