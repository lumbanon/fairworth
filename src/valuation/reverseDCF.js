import { projectDCF, validateDCF } from './dcf.js'
import { unavailable, validate, positive, nonnegative } from './validation.js'

export function calculateReverseDCF(inputs, marketPrice, bounds = [-0.5, 1]) {
  const error =
    validate(
      {
        marketPrice,
        debt: inputs.debt,
        cash: inputs.cash,
        otherClaims: inputs.otherClaims,
      },
      {
        marketPrice: positive,
        debt: nonnegative,
        cash: nonnegative,
        otherClaims: nonnegative,
      },
    ) ||
    validateDCF(
      inputs.fcff,
      0,
      inputs.wacc,
      inputs.terminalGrowth,
      inputs.forecastYears,
      inputs.shares,
    )
  if (error) return { ...error, impliedGrowth: null }
  // Signed equity values at bracket endpoints are valid solver observations even
  // when they are too low to be displayed as a positive fair-value estimate.
  const atGrowth = (rate) => {
    const result = projectDCF(
      inputs.fcff,
      rate,
      inputs.wacc,
      inputs.terminalGrowth,
      inputs.forecastYears,
    )
    return {
      status: 'valid',
      fairValue:
        (result.value - inputs.debt + inputs.cash - inputs.otherClaims) /
        inputs.shares,
      warnings: [],
      details: result,
    }
  }
  let [low, high] = bounds
  const lower = atGrowth(low),
    upper = atGrowth(high)
  if (
    !Number.isFinite(lower.fairValue) ||
    !Number.isFinite(upper.fairValue) ||
    lower.fairValue > marketPrice ||
    upper.fairValue < marketPrice
  ) {
    return {
      ...unavailable(
        'no-solution',
        'No positive-equity solution is bracketed within the supported −50% to +100% cash-flow growth range.',
      ),
      impliedGrowth: null,
    }
  }
  for (let index = 0; index < 100; index++) {
    const middle = (low + high) / 2
    const result = atGrowth(middle)
    if (result.status !== 'valid')
      return {
        ...unavailable(
          'no-solution',
          'No valid DCF solution exists inside the search interval.',
        ),
        impliedGrowth: null,
      }
    if (Math.abs(result.fairValue - marketPrice) < 1e-8)
      return { ...result, impliedGrowth: middle }
    if (result.fairValue < marketPrice) low = middle
    else high = middle
  }
  const impliedGrowth = (low + high) / 2
  return { ...atGrowth(impliedGrowth), impliedGrowth }
}
