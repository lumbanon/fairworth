import test from "node:test";
import assert from "node:assert/strict";
import { issuerCategoryLabel, listingSourceUrl, listingVerificationSummary, matchingSecurity, ordinaryWorkflowRestriction, securityFormLabel, securityFormRestriction, securityLabel, stockLocation } from "../../src/lib/securityIdentity.js";
import { isValidTicker } from "../../src/lib/format.js";
import { loadStock, searchStocks, calculateValuation, ApiError } from "../../src/services/api.js";
import { adaptProviderStock } from "../../src/lib/providerCompatibility.js";
import { adaptProviderValuation } from "../../src/lib/providerValuation.js";
import { validateResearchResponse, askResearchQuestion } from "../../src/services/aiResearch.js";
import { providerFixture } from "../helpers/providerFixture.js";
import { providerValuationFixture } from "../helpers/providerValuationFixture.js";
import { aiResearchFixture } from "../helpers/aiResearchFixture.js";

const identity = { ticker: "GOOGL", instrument_id: "fixture-instrument-a", issuer_id: "fixture-issuer", listing_id: "fixture-listing-a", cik: "0001652044", exchange: "NASDAQ", instrument_type: "common_stock", share_class: "A", listing_status: "active" };
function scopedFixture() {
  const fixture = providerFixture("GOOGL");
  fixture.profile.company = { ...fixture.profile.company, ...identity, name: "Synthetic UI fixture; financial values are fictional" };
  for (const key of ["annual", "quarterly", "metrics", "dataStatus"]) fixture[key].identity = identity;
  fixture.coverage = { identity, as_of: "2026-10-18", stages: { classification: { status: "available", reason: "Classification supplied by the test registry." }, valuation: { status: "missing_evidence", reason: "A supported security can still lack model evidence." } } };
  return fixture;
}
function fixtureFetcher(fixture, calls = [], errors = {}) {
  return async (url, options) => {
    calls.push({ url, options });
    const parsed = new URL(url);
    const key = parsed.pathname.endsWith("/financials") ? parsed.searchParams.get("period")
      : parsed.pathname.endsWith("/metrics") ? "metrics" : parsed.pathname.endsWith("/data-status") ? "dataStatus"
      : parsed.pathname.endsWith("/coverage") ? "coverage" : "profile";
    return new Response(JSON.stringify(errors[key] ? { error: { message: errors[key], code: "provider_restricted" } } : fixture[key]), { status: errors[key] ? 402 : 200 });
  };
}

test("registry symbols and explicit security routes preserve share class and stable instrument identity", () => {
  for (const symbol of ["GOOGL", "BRK.B", "BRK-B", "ABC123", "ABCD.WS"]) assert.equal(isValidTicker(symbol), true);
  for (const symbol of ["", "123", "TOOLONGSYMBOL", "A/B", "A?B"]) assert.equal(isValidTicker(symbol), false);
  assert.equal(isValidTicker("AAA123", false), false);
  assert.equal(stockLocation(identity), "/stocks/GOOGL?instrument_id=fixture-instrument-a&listing_id=fixture-listing-a");
  assert.equal(stockLocation({ ticker: "GOOGL", listing_id: "fixture-listing-a" }), "/stocks/GOOGL?listing_id=fixture-listing-a");
  assert.equal(stockLocation("MSFT"), "/stocks/MSFT");
});

test("stable identity rejects ticker reuse, sibling share classes and missing scoped identity", () => {
  assert.equal(matchingSecurity({ identity }, identity), true);
  assert.equal(matchingSecurity({ ...identity, ticker: "RENAMED" }, identity), false);
  assert.equal(matchingSecurity({ ...identity, ticker: "RENAMED", symbol_aliases: ["GOOGL"] }, identity), true);
  for (const changed of [{ instrument_id: "other" }, { issuer_id: "other" }, { listing_id: "other" }, { cik: "0000000001" }]) assert.equal(matchingSecurity({ ...identity, ...changed }, identity), false);
  assert.equal(matchingSecurity({ ticker: "GOOGL" }, identity), false);
  assert.equal(matchingSecurity({ ...identity, issuer_id: undefined }, identity), false);
  assert.equal(matchingSecurity(null, identity), false);
});

test("registry aliases must be explicit while older dot-hyphen contracts remain compatible", () => {
  const berkshire = { ticker: "BRK.B", instrument_id: "fixture-brkb", symbol_aliases: ["BRK-B"] };
  assert.equal(matchingSecurity(berkshire, "BRK-B"), true);
  assert.equal(matchingSecurity({ ...berkshire, symbol_aliases: [] }, "BRK-B"), false);
  assert.equal(matchingSecurity({ ticker: "BRK-B" }, "BRK.B"), true);
});

test("all stock data requests carry instrument_id and retain exact validated profile identity", async () => {
  const fixture = scopedFixture();
  const calls = [];
  const loaded = await loadStock("GOOGL", { instrumentId: identity.instrument_id, listingId: identity.listing_id, fetcher: fixtureFetcher(fixture, calls) });
  assert.equal(calls.length, 6);
  assert.ok(calls.every(({ url }) => new URL(url).searchParams.get("instrument_id") === identity.instrument_id));
  assert.ok(calls.every(({ url }) => new URL(url).searchParams.get("listing_id") === identity.listing_id));
  assert.deepEqual(loaded.coverage, fixture.coverage);
  const company = adaptProviderStock(loaded);
  assert.equal(company.instrumentId, identity.instrument_id);
  assert.equal(company.listingId, identity.listing_id);
  assert.equal(company.shareClass, "A");
  assert.equal(company.latest.netIncome, 120);
});

test("sparse statements preserve profile, explicit provider restriction and unavailable financial values", async () => {
  const fixture = scopedFixture();
  const loaded = await loadStock("GOOGL", { instrumentId: identity.instrument_id, fetcher: fixtureFetcher(fixture, [], { annual: "Statements restricted by the mocked provider." }) });
  assert.equal(loaded.annual, null);
  assert.equal(loaded.requestWarnings[0].code, "provider_restricted");
  const company = adaptProviderStock(loaded);
  assert.equal(company.financials.length, 0);
  assert.equal(company.latest.netIncome, null);
  assert.equal(company.financialStatus, "unavailable");
  assert.equal(company.coverage.stages.valuation.status, "missing_evidence");
});

test("scoped financial response mismatch fails closed even on optional endpoints", async () => {
  for (const key of ["profile", "annual", "quarterly", "metrics", "dataStatus", "coverage"]) {
    const fixture = scopedFixture();
    if (key === "profile") fixture[key].company.instrument_id = "unrelated";
    else fixture[key].identity = { ...identity, instrument_id: "unrelated" };
    await assert.rejects(loadStock("GOOGL", { instrumentId: identity.instrument_id, fetcher: fixtureFetcher(fixture) }), (error) => error instanceof ApiError && error.code === "incompatible_response");
  }
});

test("search is bounded and paginated at the API boundary without downloading an entire registry", async () => {
  let requested;
  await searchStocks("alphabet", { limit: 10, offset: 20, fetcher: async (url) => { requested = new URL(url); return new Response(JSON.stringify({ results: [] })); } });
  assert.equal(requested.searchParams.get("q"), "alphabet");
  assert.equal(requested.searchParams.get("limit"), "10");
  assert.equal(requested.searchParams.get("offset"), "20");
});

test("backend applicability gates unsupported securities without blocking missing evidence", () => {
  assert.equal(ordinaryWorkflowRestriction({ stages: { valuation: { status: "missing_evidence" } } }), null);
  for (const status of ["financially_inapplicable", "not_supported", "identity_ambiguous"]) assert.equal(ordinaryWorkflowRestriction({ stages: { classification: { status, reason: "An authoritative backend restriction." } } }), "An authoritative backend restriction.");
  assert.equal(ordinaryWorkflowRestriction(null), null);
  assert.equal(securityLabel("etf"), "ETF");
  assert.equal(securityLabel("adr"), "ADR / ADS");
});

test("valuation requests and response checks retain instrument identity without changing financial inputs", async () => {
  const response = providerValuationFixture("GOOGL");
  response.company = { ...response.company, ...identity };
  assert.ok(adaptProviderValuation(response, identity));
  assert.throws(() => adaptProviderValuation({ ...response, company: { ...response.company, instrument_id: "other" } }, identity), /does not match/);
  const body = { assumptions: { target_pe: 25 } };
  await calculateValuation("GOOGL", body, { instrumentId: identity.instrument_id, listingId: identity.listing_id, fetcher: async (url, options) => {
    assert.equal(new URL(url).searchParams.get("instrument_id"), identity.instrument_id);
    assert.equal(new URL(url).searchParams.get("listing_id"), identity.listing_id);
    assert.deepEqual(JSON.parse(options.body), body);
    return new Response(JSON.stringify(response));
  } });
});

test("AI chat shares the same scoped identity and rejects another security's otherwise valid citations", async () => {
  const result = aiResearchFixture("GOOGL", { kind: "chat" });
  result.identity = identity;
  result.evidence_references.forEach((source) => { source.identity = identity; });
  assert.ok(validateResearchResponse(result, "GOOGL", "chat", identity));
  assert.throws(() => validateResearchResponse({ ...result, identity: { ...identity, issuer_id: "another-issuer" } }, "GOOGL", "chat", identity), /does not match/);
  assert.throws(() => validateResearchResponse({ ...result, evidence_references: result.evidence_references.map((source) => ({ ...source, identity: { ...identity, instrument_id: "different-class" } })) }, "GOOGL", "chat", identity), /incomplete/);
  const answer = await askResearchQuestion("GOOGL", "Why is the valuation unavailable?", [], undefined, { session: "synthetic-session-token", instrumentId: identity.instrument_id, listingId: identity.listing_id, expectedIdentity: identity, fetcher: async (url, options) => {
    assert.equal(new URL(url).searchParams.get("instrument_id"), identity.instrument_id);
    assert.equal(new URL(url).searchParams.get("listing_id"), identity.listing_id);
    assert.deepEqual(JSON.parse(options.body), { question: "Why is the valuation unavailable?", history: [] });
    return new Response(JSON.stringify(result));
  } });
  assert.deepEqual(answer.identity, identity);
});

test("listing scope is independently mandatory when selected and cannot identify another venue", () => {
  const selected = { ticker: "GOOGL", listing_id: identity.listing_id };
  assert.equal(matchingSecurity({ identity }, selected), true);
  assert.equal(matchingSecurity({ ticker: "GOOGL" }, selected), false);
  assert.equal(matchingSecurity({ ...identity, listing_id: "other-venue" }, selected), false);
  assert.equal(matchingSecurity({ ...identity, listing_id: "other-venue" }, identity), false);
});

test("company search aliases never authorize a different canonical ticker on scoped financial records", () => {
  const incorrect = { ...identity, ticker: "OTHER", aliases: ["GOOGL", "Alphabet Inc."] };
  assert.equal(matchingSecurity(incorrect, identity), false);
  assert.equal(matchingSecurity({ ...incorrect, symbol_aliases: ["GOOGL"] }, identity), true);
});

test("temporary coverage failures are disclosed without fabricating coverage or hiding validated financial data", async () => {
  for (const status of [503, 429, 404]) {
    const fixture = scopedFixture();
    const fetcher = fixtureFetcher(fixture);
    const loaded = await loadStock("GOOGL", { instrumentId: identity.instrument_id, listingId: identity.listing_id, fetcher: (url, options) => new URL(url).pathname.endsWith("/coverage")
      ? new Response(JSON.stringify({ error: { code: status === 429 ? "provider_rate_limited" : "coverage_unavailable", message: "Coverage assessment could not be completed." } }), { status })
      : fetcher(url, options) });
    assert.equal(loaded.coverage, null);
    assert.equal(loaded.annual.periods.length, 1);
    const warnings = loaded.requestWarnings.filter((warning) => warning.field === "coverage");
    assert.equal(warnings.length, status === 404 ? 0 : 1);
    if (status !== 404) assert.match(warnings[0].message, /coverage diagnostics are unavailable/);
    assert.equal(adaptProviderStock(loaded).coverage, null);
  }
});

test("active status, verified identity, quotes and retrieval clocks cannot independently verify a listing", () => {
  for (const value of [identity, { ...identity, identity_status: "verified", registry_retrieved_at: "2026-10-19T12:00:00Z", market: { price: 100 } }, { ...identity, listing_verification: { status: "verified", confidence: "unverified" } }]) {
    const summary = listingVerificationSummary(value);
    assert.equal(summary.verified, false);
    assert.equal(summary.label, "Reference only · listing unverified");
  }
});

test("explicit source-backed listing verification retains independent clocks and exposes conflicts", () => {
  const listing = { ...identity, listing_verification: { status: "verified", confidence: "source_backed", freshness: "fresh", source: "synthetic_exchange_directory", observed_on: "2026-10-16", published_at: "1016202617:03", source_timezone: null, retrieved_at: "2026-10-19T12:00:00Z", conflicts: [] } };
  const summary = listingVerificationSummary(listing);
  assert.equal(summary.label, "Verified active listing");
  assert.equal(summary.observed_on, "2026-10-16");
  assert.equal(summary.published_at, "1016202617:03");
  assert.equal(summary.retrieved_at, "2026-10-19T12:00:00Z");
  for (const conflict of [{ status: "conflicting" }, { confidence: "conflicted" }, { conflicts: [{ field: "listing_status", values: ["active", "inactive"] }] }]) {
    const result = listingVerificationSummary({ ...listing, listing_verification: { ...listing.listing_verification, ...conflict } });
    assert.equal(result.verified, false);
    assert.equal(result.label, "Listing sources conflict");
  }
});

test("dated and suspended source observations are not presented as current active listings", () => {
  const listing = { ...identity, listing_verification: { status: "verified", confidence: "source_backed", freshness: "fresh", observed_on: "2026-09-01" } };
  assert.equal(listingVerificationSummary({ ...listing, registry_status: "stale" }).label, "Dated active-listing observation");
  assert.equal(listingVerificationSummary({ ...listing, listing_status: "suspended" }).label, "Verified suspended listing");
  assert.equal(listingVerificationSummary({ ...listing, listing_status: "suspended", registry_status: "stale" }).label, "Dated suspended-listing observation");
  assert.equal(listingVerificationSummary({ ...listing, listing_status: "unknown" }).label, "Listing status unverified");
});

test("security form and issuer business category are presented independently", () => {
  const bank = { ...identity, security_form: "common_stock", issuer_business_category: "bank", instrument_type: "financial_institution" };
  assert.equal(securityFormLabel(bank), "Common stock");
  assert.equal(issuerCategoryLabel(bank), "Bank");
  assert.equal(securityFormLabel({ security_form: "adr", issuer_business_category: "operating_company" }), "ADR / ADS");
  assert.equal(issuerCategoryLabel({}), "Issuer category unverified");
  assert.equal(securityFormLabel({ security_form: "unknown", instrument_type: "common_stock" }), "Classification unverified");
  assert.equal(securityFormRestriction(bank), null);
  assert.equal(securityFormRestriction({ security_form: "adr" }), null);
  assert.equal(securityFormRestriction({ security_form: "etf" }), "Operating-company models inapplicable");
  assert.equal(securityFormRestriction({ security_form: "warrant" }), "Common-share valuation does not apply");
});

test("provider adaptation preserves exact verification provenance without changing financial values", () => {
  const fixture = scopedFixture();
  const original = adaptProviderStock(fixture);
  const verification = { status: "verified", confidence: "source_backed", observed_on: "2026-10-16", published_at: "1016202617:03", source_timezone: null, retrieved_at: "2026-10-19T12:00:00Z", record_hash: "synthetic-record-hash" };
  fixture.coverage.identity = { ...identity, display_symbol: "SYNTH.A", security_form: "common_stock", issuer_business_category: "bank", listing_verification: verification };
  const result = adaptProviderStock(fixture);
  assert.equal(result.securityForm, "common_stock");
  assert.equal(result.issuerBusinessCategory, "bank");
  assert.deepEqual(result.listingVerification, verification);
  assert.equal(result.displaySymbol, "SYNTH.A");
  assert.equal(result.ticker, "GOOGL");
  assert.deepEqual(result.financials, original.financials);
  assert.equal(result.price, original.price);
});

test("listing provenance links permit only public HTTPS URLs without embedded credentials", () => {
  assert.equal(listingSourceUrl("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"), "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt");
  for (const value of ["https://data.sec.gov/submissions/CIK0000000001.json", "https://www.sec.gov/files/company_tickers_exchange.json", "https://www.nyse.com/market-data/reference"]) assert.equal(listingSourceUrl(value), value);
  for (const value of [undefined, "javascript:alert(1)", "http://example.com/", "https://private:secret@example.com/", "/relative", "https://www.nyse.com/market-data/reference?secret=synthetic-private-value", "https://www.nyse.com/market-data/reference#private", "https://www.sec.gov:444/files/company_tickers_exchange.json", "https://untrusted.test/public", "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt.backup", "https://www.sec.gov/files/%2e%2e/private", "https://www.sec.gov/files/%5cprivate"]) assert.equal(listingSourceUrl(value), null);
});

test("current listing labels require a valid nonfuture observation date and explicit fresh status", () => {
  const listing = { ...identity, listing_verification: { status: "verified", confidence: "source_backed", observed_on: "2026-10-16" } };
  assert.equal(listingVerificationSummary(listing).label, "Dated listing observation");
  assert.equal(listingVerificationSummary(listing).current, false);
  assert.equal(listingVerificationSummary({ ...listing, registry_status: "fresh" }).label, "Verified active listing");
  for (const observed_on of [null, "not-a-date", "2026-02-30", "9999-01-01"]) {
    const summary = listingVerificationSummary({ ...listing, registry_status: "fresh", listing_verification: { ...listing.listing_verification, observed_on } });
    assert.equal(summary.current, false);
    assert.equal(summary.label, "Listing observation date unverified");
  }
  assert.equal(listingVerificationSummary({ ...listing, registry_status: "partial", listing_verification: { ...listing.listing_verification, freshness: "fresh" } }).current, false);
});
