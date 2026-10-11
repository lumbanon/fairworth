export function combineValuations(results, enabled, weights, marketPrice) {
  const selected = results.filter((result) => enabled[result.id])
  const invalidWeight = selected.some(
    (result) =>
      typeof weights[result.id] !== 'number' ||
      !Number.isFinite(weights[result.id]) ||
      weights[result.id] < 0,
  )
  if (invalidWeight)
    return {
      fairValue: null,
      upside: null,
      marginOfSafety: null,
      normalizedWeights: {},
      count: 0,
      warnings: ['Enabled model weights must be finite, non-negative numbers.'],
    }
  const valid = selected.filter(
    (result) => result.status === 'valid' && weights[result.id] > 0,
  )
  const total = valid.reduce((sum, result) => sum + weights[result.id], 0)
  if (!Number.isFinite(total) || total <= 0)
    return {
      fairValue: null,
      upside: null,
      marginOfSafety: null,
      normalizedWeights: {},
      count: 0,
      warnings: [
        selected.length
          ? 'No valid enabled models have a positive weight. Enable a valid model and give it a weight above zero.'
          : 'No valuation models are enabled. Enable at least one applicable model.',
      ],
    }
  const normalizedWeights = Object.fromEntries(
    valid.map((result) => [result.id, weights[result.id] / total]),
  )
  const fairValue = valid.reduce(
    (sum, result) => sum + result.fairValue * normalizedWeights[result.id],
    0,
  )
  const warnings = selected
    .filter((result) => result.status !== 'valid')
    .map((result) => `${result.name} is excluded until its inputs are valid.`)
  const hasPrice = Number.isFinite(marketPrice) && marketPrice > 0
  return {
    fairValue,
    upside: hasPrice ? (fairValue / marketPrice - 1) * 100 : null,
    marginOfSafety: hasPrice
      ? ((fairValue - marketPrice) / fairValue) * 100
      : null,
    normalizedWeights,
    count: valid.length,
    warnings,
  }
}
