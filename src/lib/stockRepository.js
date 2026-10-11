import { mockFinancials } from '../data/mockFinancials.js'
import { normalizeTicker } from './format.js'

// Data boundary: replace this adapter with a service without changing presentation.
export function getStockData(ticker) {
  return mockFinancials[normalizeTicker(ticker)] ?? null
}
