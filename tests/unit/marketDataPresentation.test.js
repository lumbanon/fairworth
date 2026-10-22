import test from "node:test";
import assert from "node:assert/strict";
import { providerAccessLabel, providerQuoteCurrency, quoteCurrencyLabel, marketCapabilities } from "../../src/lib/marketDataPresentation.js";
import { providerCompatibilityLabel } from "../../src/lib/providerDiagnostics.js";
import { adaptProviderStock } from "../../src/lib/providerCompatibility.js";
import { providerFixture } from "../helpers/providerFixture.js";

test("market access states distinguish dated success, denial, rate limits, missing fields and untested endpoints", () => {
  assert.equal(providerAccessLabel("observed_access"), "Dated successful request");
  assert.equal(providerAccessLabel("requires_paid_subscription"), "Subscription restricted");
  assert.equal(providerAccessLabel("explicitly_denied"), "Access denied");
  assert.equal(providerAccessLabel("rate_limited"), "Rate limited");
  assert.equal(providerAccessLabel("temporarily_unavailable"), "Temporarily unavailable");
  assert.equal(providerAccessLabel("not_yet_tested"), "Not yet tested");
  assert.equal(providerAccessLabel("unsupported_source_field"), "Required field unsupported");
  assert.equal(providerAccessLabel("unknown"), "Access not assessed");
});

test("a ticker, exchange, reporting currency or an inconsistent resolution cannot supply quote currency", () => {
  const market = { ticker: "MSFT", exchange: "NASDAQ", reporting_currency: "USD", price: 100 };
  assert.equal(providerQuoteCurrency(market), null);
  assert.equal(providerQuoteCurrency({ ...market, currency_resolution: { status: "verified", currency: "USD" } }), null);
  for (const status of ["quote_currency_unverified", "conflict", "unrecognized"]) assert.equal(providerQuoteCurrency({ ...market, currency: "USD", currency_resolution: { status, currency: "USD" } }), null);
  assert.equal(providerQuoteCurrency({ currency: "USD", currency_resolution: { status: "verified", currency: "EUR" } }), null);
  assert.equal(providerQuoteCurrency({ currency: "USD", currency_resolution: { status: "verified", currency: "USD" } }), "USD");
});

test("legacy explicit currencies retain their unit while absence of verification stays unassessed", () => {
  assert.equal(providerQuoteCurrency({ currency: "EUR" }), "EUR");
  assert.equal(quoteCurrencyLabel(undefined), "Quote currency verification unassessed");
  assert.equal(quoteCurrencyLabel({ status: "quote_currency_unverified" }), "Quote currency unverified");
  assert.equal(quoteCurrencyLabel({ status: "conflict" }), "Currency evidence conflicts");
  assert.equal(providerCompatibilityLabel("quote_currency_unverified"), "Quote currency unverified");
});

test("profile and market capability records retain source scope without creating an entitlement", () => {
  const quote = { provider: "fmp", subscription: "free", scope: { ticker: "MSFT", listing_id: "synthetic-listing" }, endpoints: { quote: { access_status: "not_yet_tested", observed_at: null } }, display_license_status: "unresolved" };
  assert.equal(marketCapabilities({ providerCapabilities: quote }), quote);
  assert.equal(marketCapabilities({ providerCapabilities: {}, market: { provider_capabilities: quote } }), quote);
  assert.equal(marketCapabilities({}), null);
  const fixture = providerFixture();
  fixture.profile.provider_capabilities = quote;
  fixture.profile.market.currency_resolution = { status: "verified", currency: "USD", evidence: [{ source_record_hash: "a".repeat(64), original_record: { symbol: "MSFT", currency: "USD" } }] };
  const before = structuredClone(fixture);
  const company = adaptProviderStock(fixture);
  assert.deepEqual(company.providerCapabilities, quote);
  assert.deepEqual(company.market.currency_resolution, fixture.profile.market.currency_resolution);
  assert.deepEqual(fixture, before);
  assert.equal(company.price, 100);
});
