import {
  validate,
  valued,
  unavailable,
  positive,
  discount,
  years,
  fraction,
} from './validation.js'

export function calculateResidualIncome({
  bookEquity,
  shares,
  returnOnEquity,
  payoutRatio,
  costOfEquity,
  terminalGrowth,
  forecastYears,
}) {
  const error = validate(
    {
      bookEquity,
      shares,
      returnOnEquity,
      payoutRatio,
      costOfEquity,
      terminalGrowth,
      forecastYears,
    },
    {
      bookEquity: positive,
      shares: positive,
      returnOnEquity: fraction,
      payoutRatio: fraction,
      costOfEquity: discount,
      terminalGrowth: (value) => value >= 0 && value <= 0.1,
      forecastYears: years,
    },
  )
  if (error) return error
  if (costOfEquity <= terminalGrowth)
    return unavailable(
      'invalid-input',
      'Cost of equity must exceed residual-income terminal growth.',
    )
  let bookValue = bookEquity / shares
  let equityPerShare = bookValue
  const projection = []
  for (let year = 1; year <= forecastYears; year++) {
    const earnings = bookValue * returnOnEquity
    const residualIncome = earnings - bookValue * costOfEquity
    const presentValue = residualIncome / (1 + costOfEquity) ** year
    projection.push({
      year,
      beginningBookValue: bookValue,
      earnings,
      residualIncome,
      presentValue,
    })
    equityPerShare += presentValue
    // Clean-surplus assumption: retained earnings add to book equity; no OCI/buybacks.
    bookValue += earnings * (1 - payoutRatio)
  }
  const terminalValue =
    (projection.at(-1).residualIncome * (1 + terminalGrowth)) /
    (costOfEquity - terminalGrowth)
  equityPerShare += terminalValue / (1 + costOfEquity) ** forecastYears
  return valued(equityPerShare, {
    projection,
    terminalValue,
    initialBookValue: bookEquity / shares,
  })
}
