// Stable security identity is authoritative when supplied by the registry.
// Ticker comparison remains a compatibility path for older API responses.
export function securityIdentity(value = {}) {
  value ??= {};
  return value.identity ?? value.company ?? value;
}

export function matchingSecurity(actual, expected = {}) {
  const received = securityIdentity(actual);
  const requested = typeof expected === "string" ? { ticker: expected } : securityIdentity(expected);
  if (requested.instrument_id && !received.instrument_id) return false;
  if (requested.listing_id && !received.listing_id) return false;
  for (const field of ["instrument_id", "issuer_id", "listing_id", "cik"]) {
    if (requested[field] != null && (received[field] != null || requested.instrument_id || requested.listing_id) && String(requested[field]) !== String(received[field])) return false;
  }
  const ticker = (value) => String(value ?? "").toUpperCase();
  if (!requested.ticker && (requested.instrument_id || requested.listing_id)) return true;
  if (ticker(received.ticker) === ticker(requested.ticker)) return true;
  const scoped = requested.instrument_id || received.instrument_id || requested.listing_id || received.listing_id;
  const aliasField = scoped ? "symbol_aliases" : "aliases";
  const verifiedAliases = [...(Array.isArray(received[aliasField]) ? received[aliasField] : []), ...(Array.isArray(requested[aliasField]) ? requested[aliasField] : [])]
    .map((alias) => ticker(typeof alias === "string" ? alias : alias.symbol ?? alias.ticker));
  if (verifiedAliases.includes(ticker(requested.ticker)) || verifiedAliases.includes(ticker(received.ticker))) return true;
  // Legacy contracts predate the registry and explicitly supported this spelling.
  return !requested.instrument_id && !received.instrument_id
    && ticker(received.ticker).replaceAll(".", "-") === ticker(requested.ticker).replaceAll(".", "-");
}

export function stockLocation(stock) {
  const security = typeof stock === "string" ? { ticker: stock } : stock;
  const parameters = new URLSearchParams();
  if (security.instrument_id) parameters.set("instrument_id", security.instrument_id);
  if (security.listing_id) parameters.set("listing_id", security.listing_id);
  return `/stocks/${encodeURIComponent(security.ticker)}${parameters.size ? `?${parameters}` : ""}`;
}

export function securityLabel(value) {
  const labels = { common_stock: "Common stock", domestic_common_stock: "US common stock", foreign_ordinary: "Foreign ordinary share", foreign_ordinary_share: "Foreign ordinary share", adr: "ADR / ADS", ads: "ADR / ADS", reit: "REIT", financial_institution: "Financial institution", etf: "ETF", closed_end_fund: "Closed-end fund", preferred: "Preferred stock", preferred_stock: "Preferred stock", warrant: "Warrant", right: "Rights", rights: "Rights", unit: "Unit", other: "Other security", unknown: "Classification unverified" };
  return labels[value] ?? (value ? value.replaceAll("_", " ") : "Classification unverified");
}

export function ordinaryWorkflowRestriction(coverage) {
  if (!coverage?.stages) return null;
  for (const key of ["symbol_resolution", "classification", "valuation"]) {
    const stage = coverage.stages[key];
    if (["financially_inapplicable", "not_supported", "identity_ambiguous"].includes(stage?.status))
      return stage.reason || "The ordinary-stock valuation workflow is unavailable for this security.";
  }
  return null;
}
