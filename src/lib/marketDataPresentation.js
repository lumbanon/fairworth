// Presentation of server-owned market evidence. No currency, entitlement or
// financial compatibility is inferred from a ticker, venue or reporting unit.
export const providerAccessLabels = {
  not_yet_tested: "Not yet tested", observed_access: "Dated successful request",
  requires_paid_subscription: "Subscription restricted", explicitly_denied: "Access denied",
  temporarily_unavailable: "Temporarily unavailable", rate_limited: "Rate limited",
  unsupported_source_field: "Required field unsupported",
};

export function providerAccessLabel(status) {
  return providerAccessLabels[status] ?? "Access not assessed";
}

export function quoteCurrencyLabel(resolution) {
  return ({ verified: "Source-backed quote currency", quote_currency_unverified: "Quote currency unverified", conflict: "Currency evidence conflicts" })[resolution?.status] ?? "Quote currency verification unassessed";
}

export function providerQuoteCurrency(market) {
  if (!/^[A-Z]{3}$/.test(market?.currency ?? "")) return null;
  const resolution = market.currency_resolution;
  if (resolution && (resolution.status !== "verified" || resolution.currency !== market.currency)) return null;
  // Older responses may explicitly declare the quote's currency without the
  // new evidence envelope. Their verification remains labeled unassessed.
  return market.currency;
}

export function marketCapabilities(company = {}) {
  return [company.providerCapabilities, company.market?.provider_capabilities]
    .find((value) => value && typeof value === "object" && Object.keys(value).length > 0) ?? null;
}
