export const currency = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
})
export function formatCurrency(value) {
  return currency.format(value)
}
export function normalizeTicker(value) {
  return value.trim().toUpperCase()
}
export function isValidTicker(value, registry = true) {
  return registry ? /^[A-Z][A-Z0-9.-]{0,9}$/.test(value) : /^[A-Z]{1,5}(?:[.-][A-Z])?$/.test(value)
}
