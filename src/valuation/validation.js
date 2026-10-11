export function unavailable(status, warnings) {
  return {
    status,
    fairValue: null,
    warnings: Array.isArray(warnings) ? warnings : [warnings],
    details: {},
  }
}

export function validate(values, rules) {
  const missing = Object.entries(values)
    .filter(([, value]) => value == null)
    .map(([key]) => key)
  if (missing.length)
    return unavailable(
      'insufficient-data',
      `Missing financial inputs: ${missing.join(', ')}.`,
    )
  const errors = []
  for (const [key, value] of Object.entries(values)) {
    if (typeof value !== 'number' || !Number.isFinite(value))
      errors.push(`${key} must be a finite number.`)
    else if (rules[key] && !rules[key](value))
      errors.push(`${key} is outside the supported range.`)
  }
  return errors.length ? unavailable('invalid-input', errors) : null
}

export function valued(fairValue, details = {}) {
  if (!Number.isFinite(fairValue) || fairValue <= 0)
    return unavailable(
      'invalid-input',
      'These assumptions do not produce a positive, finite equity value.',
    )
  return { status: 'valid', fairValue, warnings: [], details }
}

export const positive = (value) => value > 0
export const nonnegative = (value) => value >= 0
export const growth = (value) => value > -1 && value <= 2
export const discount = (value) => value > 0 && value <= 1
export const years = (value) =>
  Number.isInteger(value) && value >= 1 && value <= 30
export const fraction = (value) => value >= 0 && value <= 1
