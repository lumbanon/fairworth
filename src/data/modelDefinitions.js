import { calculateFCFF, calculateFCFE } from '../valuation/dcf.js'
import {
  calculatePE,
  calculateEVEBITDA,
  calculateEVRevenue,
  calculatePEG,
  calculateGraham,
  calculatePB,
  calculateAFFO,
} from '../valuation/multiples.js'
import { calculateDividend } from '../valuation/dividend.js'
import { calculateResidualIncome } from '../valuation/residualIncome.js'

export const modelDefinitions = [
  {
    id: 'fcff',
    name: 'Discounted Cash Flow (FCFF)',
    shortName: 'FCFF DCF',
    description:
      'Discount future firm cash flow at WACC; subtract net debt and other claims to get equity value.',
    formula:
      'PV(FCFF) + PV(terminal value) − debt + cash − other claims, divided by shares.',
    requiredInputs: ['fcff', 'debt', 'cash', 'otherClaims', 'shares'],
    condition: 'Non-financial, non-REIT companies with positive starting FCFF.',
    assumptions: [
      'cashFlowGrowth',
      'wacc',
      'terminalGrowth',
      'forecastYears',
      'shares',
    ],
    defaultWeight: 35,
    defaultEnabled: true,
    calculate: calculateFCFF,
  },
  {
    id: 'fcfe',
    name: 'Discounted Cash Flow (FCFE)',
    shortName: 'FCFE DCF',
    description:
      'Discount cash available to equity holders at cost of equity. Net debt is not subtracted again.',
    formula: 'PV(FCFE) + PV(terminal value), divided by shares.',
    requiredInputs: ['fcfe', 'shares'],
    condition: 'Non-financial, non-REIT companies with positive starting FCFE.',
    assumptions: [
      'cashFlowGrowth',
      'costOfEquity',
      'terminalGrowth',
      'forecastYears',
      'shares',
    ],
    defaultWeight: 15,
    defaultEnabled: false,
    calculate: calculateFCFE,
  },
  {
    id: 'pe',
    name: 'Forward P/E',
    shortName: 'Forward P/E',
    description:
      'Apply a justified earnings multiple to one-year forecast diluted EPS.',
    formula: '(Net income / shares) × (1 + EPS growth) × target P/E.',
    requiredInputs: ['netIncome', 'shares'],
    condition: 'Profitable non-bank, non-REIT companies.',
    assumptions: ['epsGrowth', 'targetPE', 'shares'],
    defaultWeight: 25,
    defaultEnabled: true,
    calculate: calculatePE,
  },
  {
    id: 'evEbitda',
    name: 'EV/EBITDA',
    shortName: 'EV/EBITDA',
    description:
      'Apply an enterprise multiple to forecast EBITDA, then adjust for net debt and other claims.',
    formula:
      'Forecast revenue × EBITDA margin × multiple − net debt − other claims, divided by shares.',
    requiredInputs: [
      'revenue',
      'ebitda',
      'debt',
      'cash',
      'otherClaims',
      'shares',
    ],
    condition: 'Non-financial, non-REIT companies with positive EBITDA.',
    assumptions: ['revenueGrowth', 'ebitdaMargin', 'targetEVEBITDA', 'shares'],
    defaultWeight: 20,
    defaultEnabled: true,
    calculate: calculateEVEBITDA,
  },
  {
    id: 'evRevenue',
    name: 'EV/Revenue',
    shortName: 'EV/Revenue',
    description:
      'Use forecast revenue to estimate enterprise value; margins and reinvestment are not explicitly modeled.',
    formula:
      'Revenue × (1 + growth) × multiple − net debt − other claims, divided by shares.',
    requiredInputs: ['revenue', 'debt', 'cash', 'otherClaims', 'shares'],
    condition: 'Non-financial, non-REIT companies with positive revenue.',
    assumptions: ['revenueGrowth', 'targetEVRevenue', 'shares'],
    defaultWeight: 20,
    defaultEnabled: true,
    calculate: calculateEVRevenue,
  },
  {
    id: 'peg',
    name: 'PEG-Based Valuation',
    shortName: 'PEG',
    description:
      'Use annual EPS growth in percentage points to derive a justified P/E. Highly sensitive to growth estimates.',
    formula:
      'Forward EPS × target PEG × EPS growth × 100 (growth stored as a decimal).',
    requiredInputs: ['netIncome', 'shares'],
    condition: 'Profitable non-financial, non-REIT growth companies.',
    assumptions: ['epsGrowth', 'targetPEG', 'shares'],
    defaultWeight: 10,
    defaultEnabled: false,
    calculate: calculatePEG,
  },
  {
    id: 'graham',
    name: 'Graham Number',
    shortName: 'Graham',
    description:
      'A historical heuristic for selected mature, book-value-relevant companies; not a comprehensive valuation.',
    formula: '√(22.5 × current EPS × book value per share).',
    requiredInputs: ['netIncome', 'bookEquity', 'shares'],
    condition:
      'Selected mature companies with positive earnings and book equity.',
    assumptions: ['shares'],
    defaultWeight: 10,
    defaultEnabled: false,
    calculate: calculateGraham,
  },
  {
    id: 'dividend',
    name: 'Dividend Discount Model',
    shortName: 'Dividend discount',
    description:
      'Discount a stable, perpetually growing dividend stream at cost of equity.',
    formula:
      'Next-year dividend per share / (cost of equity − dividend growth).',
    requiredInputs: ['dividends', 'shares'],
    condition:
      'Stable dividend-paying companies; AFFO is preferred for this REIT example.',
    assumptions: ['dividendGrowth', 'costOfEquity', 'shares'],
    defaultWeight: 20,
    defaultEnabled: true,
    calculate: calculateDividend,
  },
  {
    id: 'residual',
    name: 'Residual Income Model',
    shortName: 'Residual income',
    description:
      'Add discounted earnings above the equity capital charge to current book value. Uses a simplified clean-surplus roll-forward.',
    formula:
      'Book value/share + PV((ROE − cost of equity) × beginning book value) + PV(terminal residual income).',
    requiredInputs: ['bookEquity', 'shares'],
    condition: 'Banking businesses with meaningful positive book equity.',
    assumptions: [
      'returnOnEquity',
      'payoutRatio',
      'costOfEquity',
      'terminalGrowth',
      'forecastYears',
      'shares',
    ],
    defaultWeight: 45,
    defaultEnabled: true,
    calculate: calculateResidualIncome,
  },
  {
    id: 'pb',
    name: 'Price-to-Book',
    shortName: 'Price-to-book',
    description:
      'Apply a justified book-equity multiple to an equity-focused business.',
    formula: 'Book equity / shares × target P/B.',
    requiredInputs: ['bookEquity', 'shares'],
    condition: 'Banking businesses with positive book equity.',
    assumptions: ['targetPB', 'shares'],
    defaultWeight: 35,
    defaultEnabled: true,
    calculate: calculatePB,
  },
  {
    id: 'affo',
    name: 'REIT AFFO Valuation',
    shortName: 'REIT AFFO',
    description:
      'Apply a cash-earnings multiple to the provided adjusted funds from operations.',
    formula: 'AFFO / shares × target P/AFFO.',
    requiredInputs: ['affo', 'shares'],
    condition: 'REITs with positive, available AFFO data.',
    assumptions: ['targetPAFFO', 'shares'],
    defaultWeight: 100,
    defaultEnabled: true,
    calculate: calculateAFFO,
  },
]
