import test from 'node:test'
import assert from 'node:assert/strict'
import { calculateFCFF, calculateFCFE } from '../../src/valuation/dcf.js'
import {
  calculatePE,
  calculateEVEBITDA,
  calculateEVRevenue,
  calculatePEG,
  calculateGraham,
  calculatePB,
  calculateAFFO,
} from '../../src/valuation/multiples.js'
import { calculateDividend } from '../../src/valuation/dividend.js'
import { calculateResidualIncome } from '../../src/valuation/residualIncome.js'
import { calculateReverseDCF } from '../../src/valuation/reverseDCF.js'
import { combineValuations } from '../../src/valuation/weighting.js'
import {
  createScenarioDefaults,
  scenarioNames,
} from '../../src/valuation/scenarios.js'
import {
  evaluateModels,
  modelEligibility,
  calculationInputs,
} from '../../src/valuation/modelSelector.js'
import { modelDefinitions } from '../../src/data/modelDefinitions.js'
import { mockFinancials } from '../../src/data/mockFinancials.js'

const close = (actual, expected, tolerance = 1e-8) =>
  assert.ok(
    Math.abs(actual - expected) < tolerance,
    `${actual} should equal ${expected}`,
  )
const dcf = {
  fcff: 100,
  fcfe: 100,
  cashFlowGrowth: 0,
  wacc: 0.1,
  costOfEquity: 0.1,
  terminalGrowth: 0,
  forecastYears: 2,
  shares: 10,
  debt: 100,
  cash: 20,
  otherClaims: 10,
}

test('FCFF constant-cash-flow perpetuity reconciles EV to equity, including other claims', () => {
  const result = calculateFCFF(dcf)
  // $100 perpetuity / 10% = $1,000 EV; $1,000 − 100 + 20 − 10 = $910 equity.
  close(result.details.enterpriseValue, 1000)
  close(result.fairValue, 91)
  close(result.details.projection[0].presentValue, 100 / 1.1)
})
test('FCFF explicit growth and terminal-year discounting are correct', () => {
  // Years 1/2 CF=110/121, each PV=100; terminal PV=1,000; equity=1,110.
  close(calculateFCFF({ ...dcf, cashFlowGrowth: 0.1 }).fairValue, 111)
})
test('FCFE discounts equity cash flow and never subtracts net debt again', () => {
  close(calculateFCFE(dcf).fairValue, 100)
  close(
    calculateFCFE({ ...dcf, debt: 999999, cashFlowGrowth: 0.1 }).fairValue,
    120,
  )
})
test('Forward P/E uses forecast EPS with consistent share units', () =>
  close(
    calculatePE({ netIncome: 100, shares: 20, epsGrowth: 0.1, targetPE: 15 })
      .fairValue,
    82.5,
  ))
test('EV/EBITDA forecasts revenue and margin before the equity bridge', () =>
  close(
    calculateEVEBITDA({
      revenue: 1000,
      revenueGrowth: 0.1,
      ebitdaMargin: 0.2,
      targetEVEBITDA: 10,
      debt: 200,
      cash: 50,
      otherClaims: 10,
      shares: 20,
    }).fairValue,
    102,
  ))
test('EV/Revenue adjusts debt, cash, and claims exactly once', () =>
  close(
    calculateEVRevenue({
      revenue: 1000,
      revenueGrowth: 0.1,
      targetEVRevenue: 2.5,
      debt: 200,
      cash: 50,
      otherClaims: 10,
      shares: 20,
    }).fairValue,
    129.5,
  ))
test('PEG interprets 12% growth as 12 percentage points, not 0.12', () => {
  const result = calculatePEG({
    netIncome: 100,
    shares: 20,
    epsGrowth: 0.12,
    targetPEG: 2,
  })
  close(result.details.justifiedPE, 24)
  close(result.fairValue, 134.4)
})
test('Graham Number requires positive earnings and book equity', () => {
  close(
    calculateGraham({ netIncome: 80, bookEquity: 180, shares: 20 }).fairValue,
    Math.sqrt(810),
  )
  assert.equal(
    calculateGraham({ netIncome: 80, bookEquity: -180, shares: 20 }).fairValue,
    null,
  )
})
test('Dividend discount values next-year dividend and validates the spread', () => {
  close(
    calculateDividend({
      dividends: 20,
      shares: 10,
      dividendGrowth: 0.04,
      costOfEquity: 0.08,
    }).fairValue,
    52,
  )
  assert.equal(
    calculateDividend({
      dividends: 20,
      shares: 10,
      dividendGrowth: 0.08,
      costOfEquity: 0.08,
    }).status,
    'invalid-input',
  )
})
test('Residual income reconciles book value plus a perpetual capital-charge surplus', () => {
  const inputs = {
    bookEquity: 1000,
    shares: 10,
    returnOnEquity: 0.12,
    payoutRatio: 1,
    costOfEquity: 0.1,
    terminalGrowth: 0,
    forecastYears: 2,
  }
  close(calculateResidualIncome(inputs).fairValue, 120)
  close(
    calculateResidualIncome({ ...inputs, returnOnEquity: 0.08 }).fairValue,
    80,
  )
  close(
    calculateResidualIncome({ ...inputs, payoutRatio: 0.5 }).fairValue,
    121.0909090909091,
  )
})
test('Price-to-book uses diluted book equity per share', () =>
  close(
    calculatePB({ bookEquity: 180, shares: 20, targetPB: 1.5 }).fairValue,
    13.5,
  ))
test('AFFO multiple uses a total AFFO amount divided by shares', () =>
  close(calculateAFFO({ affo: 90, shares: 20, targetPAFFO: 16 }).fairValue, 72))
test('Reverse DCF recovers an independently known 10% growth solution', () => {
  const result = calculateReverseDCF(
    { ...dcf, debt: 0, cash: 0, otherClaims: 0 },
    120,
  )
  assert.equal(result.status, 'valid')
  close(result.impliedGrowth, 0.1)
  close(result.fairValue, 120)
})
test('Reverse DCF accepts a negative-equity lower endpoint and handles missing brackets', () => {
  const inputs = { ...dcf, debt: 500, cash: 0, otherClaims: 0 }
  close(calculateReverseDCF(inputs, 70).impliedGrowth, 0.1)
  assert.equal(calculateReverseDCF(inputs, 1000000).status, 'no-solution')
  assert.equal(
    calculateReverseDCF({ ...inputs, wacc: 0 }, 70).impliedGrowth,
    null,
  )
})
test('Normalized weighting and the two return conventions are distinct', () => {
  const result = combineValuations(
    [
      { id: 'a', name: 'A', status: 'valid', fairValue: 100 },
      { id: 'b', name: 'B', status: 'valid', fairValue: 200 },
    ],
    { a: true, b: true },
    { a: 1, b: 3 },
    100,
  )
  close(result.fairValue, 175)
  close(result.normalizedWeights.a, 0.25)
  close(result.upside, 75)
  close(result.marginOfSafety, 42.85714285714286)
})
test('Disabled and invalid models do not contribute; bad and zero weights warn', () => {
  const results = [
    { id: 'a', name: 'A', status: 'valid', fairValue: 100 },
    { id: 'b', name: 'B', status: 'invalid-input', fairValue: null },
  ]
  assert.equal(
    combineValuations(results, { a: false }, { a: 1 }, 100).fairValue,
    null,
  )
  assert.equal(
    combineValuations(results, { a: true }, { a: 0 }, 100).fairValue,
    null,
  )
  assert.equal(
    combineValuations(results, { a: true }, { a: -1 }, 100).fairValue,
    null,
  )
  const partial = combineValuations(
    results,
    { a: true, b: true },
    { a: 2, b: 2 },
    100,
  )
  close(partial.fairValue, 100)
  assert.equal(partial.warnings.length, 1)
})
test('Rules select bank, REIT, and loss-making company methods without missing-value zeros', () => {
  const eligible = (ticker) =>
    modelDefinitions
      .filter(
        (model) =>
          modelEligibility(model, mockFinancials[ticker]).status ===
          'applicable',
      )
      .map((model) => model.id)
  assert.deepEqual(eligible('JPM'), ['graham', 'dividend', 'residual', 'pb'])
  assert.deepEqual(eligible('O'), ['affo'])
  assert.deepEqual(eligible('TSLA'), ['evRevenue'])
  const missing = {
    ...mockFinancials.MSFT,
    latest: { ...mockFinancials.MSFT.latest, fcff: null },
  }
  assert.equal(
    modelEligibility(modelDefinitions[0], missing).status,
    'insufficient-data',
  )
})
test('Separate scenario calculations use their own assumptions and a constant market price', () => {
  const company = mockFinancials.MSFT
  const defaults = createScenarioDefaults(company)
  const summaries = scenarioNames.map((name) =>
    combineValuations(
      evaluateModels(company, defaults[name]),
      { pe: true },
      { pe: 1 },
      company.price,
    ),
  )
  const baseEPS = company.latest.netIncome / company.latest.shares
  close(summaries[1].fairValue, baseEPS * 1.12 * 32)
  close(summaries[0].fairValue, baseEPS * 1.06 * 25.6)
  close(summaries[2].fairValue, baseEPS * 1.156 * 38.4)
  assert.ok(
    summaries[0].fairValue < summaries[1].fairValue &&
      summaries[1].fairValue < summaries[2].fairValue,
  )
})
test('Every fictional statement balances and shares/earnings/cash-flow inputs reconcile', () => {
  assert.equal(Object.keys(mockFinancials).length, 10)
  assert.equal(
    new Set(
      Object.values(mockFinancials).map((company) => company.latest.revenue),
    ).size,
    10,
  )
  for (const company of Object.values(mockFinancials))
    for (const row of company.financials) {
      close(row.assets - row.liabilities, row.bookEquity)
      close(row.eps * row.shares, row.netIncome, 1e-6)
      close(row.operatingCashFlow - row.capex, row.fcfe)
      close(row.fcfe + row.interestExpense * 0.79, row.fcff)
      assert.ok(row.cash <= row.assets && row.debt <= row.liabilities)
    }
})
test('Invalid numeric inputs, shares, discount spreads, and negative metrics remain unavailable', () => {
  for (const shares of [0, -1, NaN, Infinity, ''])
    assert.equal(calculateFCFF({ ...dcf, shares }).fairValue, null)
  for (const cashFlowGrowth of [-1, NaN, Infinity, ''])
    assert.equal(calculateFCFF({ ...dcf, cashFlowGrowth }).fairValue, null)
  assert.equal(
    calculateFCFF({ ...dcf, wacc: 0.02, terminalGrowth: 0.03 }).status,
    'invalid-input',
  )
  assert.equal(
    calculateFCFE({ ...dcf, fcfe: null }).status,
    'insufficient-data',
  )
  assert.equal(
    calculatePE({ netIncome: -1, shares: 10, epsGrowth: 0.1, targetPE: 10 })
      .fairValue,
    null,
  )
  assert.equal(
    calculateEVEBITDA({
      revenue: 10,
      ebitdaMargin: -0.1,
      revenueGrowth: 0.1,
      targetEVEBITDA: 10,
      shares: 10,
      debt: 0,
      cash: 0,
      otherClaims: 0,
    }).fairValue,
    null,
  )
  assert.equal(
    calculatePEG({ netIncome: 10, shares: 10, epsGrowth: 0, targetPEG: 1 })
      .fairValue,
    null,
  )
})
test('Default datasets produce finite applicable estimates and diagnostic roots where supported', () => {
  for (const company of Object.values(mockFinancials)) {
    const defaults = createScenarioDefaults(company)
    for (const scenario of scenarioNames) {
      const results = evaluateModels(company, defaults[scenario])
      const enabled = Object.fromEntries(
        modelDefinitions.map((model) => [
          model.id,
          model.defaultEnabled &&
            modelEligibility(model, company).status === 'applicable',
        ]),
      )
      const weights = Object.fromEntries(
        modelDefinitions.map((model) => [model.id, model.defaultWeight]),
      )
      const summary = combineValuations(
        results,
        enabled,
        weights,
        company.price,
      )
      assert.ok(
        Number.isFinite(summary.fairValue) && summary.fairValue > 0,
        company.ticker + ' ' + scenario,
      )
    }
    if (!company.isBank && !company.isREIT && company.latest.fcff > 0)
      assert.equal(
        calculateReverseDCF(
          calculationInputs(company, defaults.base),
          company.price,
        ).status,
        'valid',
        company.ticker,
      )
  }
})
