import {
  validate,
  valued,
  unavailable,
  positive,
  growth,
  discount,
} from './validation.js'

export function calculateDividend({
  dividends,
  shares,
  dividendGrowth,
  costOfEquity,
}) {
  const error = validate(
    { dividends, shares, dividendGrowth, costOfEquity },
    {
      dividends: positive,
      shares: positive,
      dividendGrowth: growth,
      costOfEquity: discount,
    },
  )
  if (error) return error
  if (costOfEquity <= dividendGrowth)
    return unavailable(
      'invalid-input',
      'Cost of equity must exceed dividend growth.',
    )
  const nextDividend = (dividends / shares) * (1 + dividendGrowth)
  return valued(nextDividend / (costOfEquity - dividendGrowth), {
    nextDividend,
  })
}
