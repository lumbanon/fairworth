import {
  validate,
  valued,
  unavailable,
  positive,
  nonnegative,
  growth,
  discount,
  years,
} from './validation.js'

// Monetary totals and shares are both in millions; their quotient is USD/share.
// Annual end-of-year discounting and a Gordon terminal value; no midyear convention.
export function projectDCF(
  cashFlow,
  cashFlowGrowth,
  discountRate,
  terminalGrowth,
  forecastYears,
) {
  const projection = Array.from({ length: forecastYears }, (_, index) => {
    const year = index + 1
    const projectedCashFlow = cashFlow * (1 + cashFlowGrowth) ** year
    return {
      year,
      cashFlow: projectedCashFlow,
      presentValue: projectedCashFlow / (1 + discountRate) ** year,
    }
  })
  const terminalValue =
    (projection.at(-1).cashFlow * (1 + terminalGrowth)) /
    (discountRate - terminalGrowth)
  const terminalPresentValue =
    terminalValue / (1 + discountRate) ** forecastYears
  const value =
    projection.reduce((sum, item) => sum + item.presentValue, 0) +
    terminalPresentValue
  return { value, projection, terminalValue, terminalPresentValue }
}

export function validateDCF(
  cashFlow,
  cashFlowGrowth,
  discountRate,
  terminalGrowth,
  forecastYears,
  shares,
) {
  const error = validate(
    {
      cashFlow,
      cashFlowGrowth,
      discountRate,
      terminalGrowth,
      forecastYears,
      shares,
    },
    {
      cashFlow: positive,
      cashFlowGrowth: growth,
      discountRate: discount,
      terminalGrowth: (value) => value >= 0 && value <= 0.1,
      forecastYears: years,
      shares: positive,
    },
  )
  if (error) return error
  if (discountRate <= terminalGrowth)
    return unavailable(
      'invalid-input',
      'The discount rate must exceed terminal growth.',
    )
  return null
}

export function calculateFCFF({
  fcff,
  cashFlowGrowth,
  wacc,
  terminalGrowth,
  forecastYears,
  shares,
  debt,
  cash,
  otherClaims,
}) {
  const error =
    validateDCF(
      fcff,
      cashFlowGrowth,
      wacc,
      terminalGrowth,
      forecastYears,
      shares,
    ) ||
    validate(
      { debt, cash, otherClaims },
      { debt: nonnegative, cash: nonnegative, otherClaims: nonnegative },
    )
  if (error) return error
  const result = projectDCF(
    fcff,
    cashFlowGrowth,
    wacc,
    terminalGrowth,
    forecastYears,
  )
  const equityValue = result.value - debt + cash - otherClaims
  return valued(equityValue / shares, {
    ...result,
    enterpriseValue: result.value,
    equityValue,
    netDebt: debt - cash,
    otherClaims,
  })
}

export function calculateFCFE({
  fcfe,
  cashFlowGrowth,
  costOfEquity,
  terminalGrowth,
  forecastYears,
  shares,
}) {
  const error = validateDCF(
    fcfe,
    cashFlowGrowth,
    costOfEquity,
    terminalGrowth,
    forecastYears,
    shares,
  )
  if (error) return error
  const result = projectDCF(
    fcfe,
    cashFlowGrowth,
    costOfEquity,
    terminalGrowth,
    forecastYears,
  )
  // FCFE is already after financing cash flows. Never subtract debt a second time.
  return valued(result.value / shares, { ...result, equityValue: result.value })
}
