import {
  validate,
  valued,
  positive,
  nonnegative,
  growth,
  fraction,
} from './validation.js'

export function calculatePE({ netIncome, shares, epsGrowth, targetPE }) {
  const error = validate(
    { netIncome, shares, epsGrowth, targetPE },
    {
      netIncome: positive,
      shares: positive,
      epsGrowth: growth,
      targetPE: positive,
    },
  )
  if (error) return error
  const forwardEPS = (netIncome / shares) * (1 + epsGrowth)
  return valued(forwardEPS * targetPE, { forwardEPS, multiple: targetPE })
}

function enterpriseMultiple({
  revenue,
  revenueGrowth,
  multiple,
  debt,
  cash,
  otherClaims,
  shares,
  ebitdaMargin,
}) {
  const values = {
    revenue,
    revenueGrowth,
    multiple,
    debt,
    cash,
    otherClaims,
    shares,
  }
  if (ebitdaMargin !== undefined) values.ebitdaMargin = ebitdaMargin
  const error = validate(values, {
    revenue: positive,
    revenueGrowth: growth,
    multiple: positive,
    debt: nonnegative,
    cash: nonnegative,
    otherClaims: nonnegative,
    shares: positive,
    ebitdaMargin: (value) => fraction(value) && value > 0,
  })
  if (error) return error
  const forecastRevenue = revenue * (1 + revenueGrowth)
  const metric =
    forecastRevenue * (ebitdaMargin === undefined ? 1 : ebitdaMargin)
  const enterpriseValue = metric * multiple
  const equityValue = enterpriseValue - debt + cash - otherClaims
  return valued(equityValue / shares, {
    forecastRevenue,
    forecastMetric: metric,
    multiple,
    enterpriseValue,
    equityValue,
  })
}

export function calculateEVEBITDA(inputs) {
  // Forecast revenue × an explicit EBITDA margin, instead of arbitrary slider offsets.
  const error = validate(
    { ebitdaMargin: inputs.ebitdaMargin },
    { ebitdaMargin: (value) => value > 0 && value <= 1 },
  )
  return (
    error || enterpriseMultiple({ ...inputs, multiple: inputs.targetEVEBITDA })
  )
}
export function calculateEVRevenue(inputs) {
  return enterpriseMultiple({
    ...inputs,
    ebitdaMargin: undefined,
    multiple: inputs.targetEVRevenue,
  })
}

export function calculatePEG({ netIncome, shares, epsGrowth, targetPEG }) {
  const error = validate(
    { netIncome, shares, epsGrowth, targetPEG },
    {
      netIncome: positive,
      shares: positive,
      epsGrowth: (value) => value > 0 && value <= 2,
      targetPEG: positive,
    },
  )
  if (error) return error
  // PEG = P/E divided by annual EPS growth in percentage points (12, not 0.12).
  const justifiedPE = targetPEG * epsGrowth * 100
  const forwardEPS = (netIncome / shares) * (1 + epsGrowth)
  return valued(forwardEPS * justifiedPE, {
    forwardEPS,
    justifiedPE,
    growthPercent: epsGrowth * 100,
  })
}

export function calculateGraham({ netIncome, bookEquity, shares }) {
  const error = validate(
    { netIncome, bookEquity, shares },
    { netIncome: positive, bookEquity: positive, shares: positive },
  )
  return (
    error ||
    valued(Math.sqrt((((22.5 * netIncome) / shares) * bookEquity) / shares), {
      formula: '√(22.5 × current EPS × book value/share)',
    })
  )
}
export function calculatePB({ bookEquity, shares, targetPB }) {
  const error = validate(
    { bookEquity, shares, targetPB },
    { bookEquity: positive, shares: positive, targetPB: positive },
  )
  return (
    error ||
    valued((bookEquity / shares) * targetPB, {
      bookValuePerShare: bookEquity / shares,
      multiple: targetPB,
    })
  )
}
export function calculateAFFO({ affo, shares, targetPAFFO }) {
  const error = validate(
    { affo, shares, targetPAFFO },
    { affo: positive, shares: positive, targetPAFFO: positive },
  )
  return (
    error ||
    valued((affo / shares) * targetPAFFO, {
      affoPerShare: affo / shares,
      multiple: targetPAFFO,
    })
  )
}
