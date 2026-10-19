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

export function securityFormLabel(value) {
  const identity = securityIdentity(value);
  return securityLabel(identity.security_form ?? identity.instrument_type);
}

export function issuerCategoryLabel(value) {
  const identity = securityIdentity(value);
  const category = identity.issuer_business_category;
  const labels = { bank: "Bank", insurance: "Insurance company", reit: "REIT", operating_company: "Operating company", other: "Other issuer category", unknown: "Issuer category unverified" };
  return labels[category] ?? (category ? category.replaceAll("_", " ") : "Issuer category unverified");
}

export function securityFormRestriction(value) {
  const identity = securityIdentity(value);
  const form = identity.security_form ?? identity.instrument_type;
  if (["etf", "closed_end_fund"].includes(form)) return "Operating-company models inapplicable";
  if (["preferred", "preferred_stock", "warrant", "right", "rights", "unit"].includes(form)) return "Common-share valuation does not apply";
  return null;
}

// A declared status or a recent retrieval is insufficient to verify a listing.
// The registry supplies source-backed verification and its independent clocks.
export function listingVerificationSummary(value) {
  const identity = securityIdentity(value);
  const verification = identity.listing_verification ?? {};
  const conflicts = Array.isArray(verification.conflicts) ? verification.conflicts : [];
  const conflicting = verification.status === "conflicting" || verification.confidence === "conflicted" || conflicts.length > 0;
  const verified = !conflicting && verification.status === "verified" && verification.confidence === "source_backed";
  const freshness = [identity.registry_status, verification.freshness].filter((status) => status != null);
  const stale = freshness.includes("stale") || verification.stale === true;
  const observedOn = verification.observed_on;
  let validDate = false;
  if (typeof observedOn === "string" && /^\d{4}-\d{2}-\d{2}$/.test(observedOn)) {
    const observation = new Date(`${observedOn}T00:00:00.000Z`);
    validDate = Number.isFinite(observation.getTime()) && observation.toISOString().slice(0, 10) === observedOn && observedOn <= new Date().toISOString().slice(0, 10);
  }
  const current = verified && validDate && !stale && freshness.length > 0 && freshness.every((status) => status === "fresh");
  let label = "Reference only · listing unverified";
  if (conflicting) label = "Listing sources conflict";
  else if (verified && !validDate) label = "Listing observation date unverified";
  else if (verified && identity.listing_status === "active") label = current ? "Verified active listing" : stale ? "Dated active-listing observation" : "Dated listing observation";
  else if (verified && ["inactive", "delisted", "suspended"].includes(identity.listing_status)) label = current ? `Verified ${identity.listing_status} listing` : stale ? `Dated ${identity.listing_status}-listing observation` : "Dated listing observation";
  else if (verified) label = "Listing status unverified";
  return { ...verification, label, verified, current, stale, conflicting, observed_on: observedOn ?? null };
}

export function listingSourceUrl(value) {
  if (typeof value !== "string" || value.length > 1000 || /\s/.test(value)) return null;
  try {
    const url = new URL(value);
    const authorities = ["www.nasdaqtrader.com", "data.sec.gov", "www.sec.gov", "www.nyse.com"];
    const rawPath = value.match(/^https:\/\/[^/?#]+([^?#]*)/i)?.[1] ?? "";
    const decoded = decodeURIComponent(rawPath);
    const nasdaqPaths = ["/dynamic/SymDir/nasdaqlisted.txt", "/dynamic/SymDir/otherlisted.txt"];
    if (url.protocol !== "https:" || !authorities.includes(url.hostname) || url.username || url.password || url.search || url.hash
      || (url.port && url.port !== "443") || decoded.includes("\\") || decoded.split("/").some((part) => part === "." || part === "..")
      || (url.hostname === "www.nasdaqtrader.com" && !nasdaqPaths.includes(decoded))) return null;
    return url.href;
  } catch {
    return null;
  }
}

export function ordinaryWorkflowRestriction(coverage) {
  if (!coverage?.stages) return null;
  for (const key of ["symbol_resolution", "security_identity", "active_listing", "classification", "share_basis", "valuation"]) {
    const stage = coverage.stages[key];
    if (["financially_inapplicable", "not_supported", "identity_ambiguous"].includes(stage?.status))
      return stage.reason || "The ordinary-stock valuation workflow is unavailable for this security.";
  }
  return null;
}
