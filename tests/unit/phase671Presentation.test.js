import test from "node:test";
import assert from "node:assert/strict";
import { issuerLinkageSummary, listingVerificationSummary } from "../../src/lib/securityIdentity.js";
import { adaptProviderValuation, providerPublicationLabel } from "../../src/lib/providerValuation.js";
import { adaptProviderStock } from "../../src/lib/providerCompatibility.js";
import { providerDiagnosticsFixture } from "../helpers/providerDiagnosticsFixture.js";
import { providerFixture } from "../helpers/providerFixture.js";

const listing = {
  ticker: "MSFT", listing_status: "active", registry_status: "fresh",
  listing_verification: { status: "verified", confidence: "source_backed", freshness: "fresh", source: "synthetic_listing_source", observed_on: "2026-10-19", retrieved_at: "2026-10-20T10:00:00Z" },
};
const expiredProof = { state: "verification_expired", source: "synthetic_listing_source", source_url: "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt", observed_on: "2026-10-19", published_at: "1019202607:00", retrieved_at: "2026-10-20T10:00:00Z", expires_at: "2026-10-20T00:00:00Z", ttl_seconds: 86400, reason: "The dated proof expired under the source policy." };

test("explicit expired listing proof cannot be promoted by fresh registry, financial or quote retrieval", () => {
  const identity = { ...listing, financial_retrieved_at: "2026-10-20T14:00:00Z", market: { price: 100, status: "fresh" }, proof_expiry: { listing: expiredProof } };
  const before = structuredClone(identity);
  const result = listingVerificationSummary(identity);
  assert.equal(result.label, "Listing verification expired");
  assert.equal(result.current, false);
  assert.equal(result.expired, true);
  assert.equal(result.observed_on, "2026-10-19");
  assert.equal(result.expires_at, "2026-10-20T00:00:00Z");
  assert.deepEqual(identity, before);
});

test("issuer proof expiry remains independent from a current verified exchange listing", () => {
  const identity = { ...listing, verification_state: "verification_expired", proof_expiry: { listing: { state: "verified" }, issuer_linkage: { ...expiredProof, source: "SEC issuer-symbol directory", source_url: "https://www.sec.gov/files/company_tickers_exchange.json" } } };
  assert.equal(listingVerificationSummary(identity).label, "Verified active listing");
  const linkage = issuerLinkageSummary(identity);
  assert.equal(linkage.label, "Issuer linkage verification expired");
  assert.equal(linkage.current, false);
  assert.equal(linkage.source, "SEC issuer-symbol directory");
  assert.equal(linkage.observed_on, "2026-10-19");
  assert.equal(linkage.retrieved_at, "2026-10-20T10:00:00Z");
});

test("unverified and conflicting source proofs cannot be displayed as current", () => {
  assert.equal(listingVerificationSummary({ ...listing, proof_expiry: { listing: { state: "unverified" } } }).current, false);
  assert.equal(listingVerificationSummary({ ...listing, proof_expiry: { listing: { state: "conflicting" } } }).label, "Listing sources conflict");
  assert.equal(issuerLinkageSummary({ issuer_linkage: { source: "SEC", observed_on: "2026-10-19", retrieved_at: "2026-10-20T10:00:00Z" } }).label, "Issuer linkage freshness unassessed");
  assert.equal(issuerLinkageSummary({}).current, false);
});

test("valuation publication remains scenario-scoped and preserves exact server values and clocks", () => {
  const response = providerDiagnosticsFixture();
  response.scenarios.base.publication = { result_type: "historical_illustration", blockers: [{ code: "verification_expired", message: "Issuer proof expired." }], clocks: { calculated_at: response.calculated_at, issuer_linkage: expiredProof } };
  response.scenarios.bear.publication = { result_type: "unavailable", blockers: [{ code: "missing_financial_input", message: "Required forecast inputs are unavailable." }], clocks: {} };
  response.scenarios.bull.publication = { result_type: "current_eligible", blockers: [], clocks: {} };
  response.financial_coverage = { publication: response.scenarios.base.publication };
  const before = structuredClone(response);
  const adapted = adaptProviderValuation(response);
  for (const scenario of ["base", "bear", "bull"]) {
    assert.deepEqual(adapted.scenarios[scenario].publication, response.scenarios[scenario].publication);
    assert.equal(adapted.scenarios[scenario].summary.fairValue, response.scenarios[scenario].summary.fair_value);
  }
  assert.deepEqual(adapted.financialCoverage, response.financial_coverage);
  assert.equal(providerPublicationLabel(adapted.scenarios.base.publication), "Historical illustration");
  assert.equal(providerPublicationLabel(adapted.scenarios.bear.publication), "Unavailable");
  assert.equal(providerPublicationLabel(adapted.scenarios.bull.publication), "Current eligible valuation");
  assert.deepEqual(response, before);
});

test("legacy or unrecognized publication metadata never implies a current valuation", () => {
  const response = providerDiagnosticsFixture();
  const legacy = adaptProviderValuation(response);
  assert.equal(legacy.scenarios.base.publication, null);
  assert.equal(providerPublicationLabel(legacy.scenarios.base.publication), "Current / historical status unassessed");
  assert.equal(providerPublicationLabel({ result_type: "active" }), "Current / historical status unassessed");
  response.financial_coverage = { publication: { result_type: "historical_illustration" } };
  const scoped = adaptProviderValuation(response);
  assert.deepEqual(scoped.scenarios.base.publication, response.financial_coverage.publication);
  assert.equal(scoped.scenarios.bear.publication, null);
  assert.equal(scoped.scenarios.bull.publication, null);
});

test("company adaptation preserves both proof clocks and identity without changing statement or market facts", () => {
  const response = providerFixture();
  const original = adaptProviderStock(response);
  response.profile.company.proof_expiry = { listing: expiredProof, issuer_linkage: { ...expiredProof, source: "SEC" } };
  response.profile.company.verification_state = "verification_expired";
  const adapted = adaptProviderStock(response);
  assert.deepEqual(adapted.identity.proof_expiry, response.profile.company.proof_expiry);
  assert.equal(adapted.identity.verification_state, "verification_expired");
  assert.deepEqual(adapted.financials, original.financials);
  assert.equal(adapted.price, original.price);
});

test("independence disclosures and conflicting debt candidates are passed through without arithmetic or family inference", () => {
  const response = providerDiagnosticsFixture();
  const independence = { contributing_models: ["pe", "peg"], contributing_model_count: 2, method_families: ["earnings"], method_family_count: 1, pairs: [{ models: ["pe", "peg"], shared_assumptions: ["forward_eps"], shared_observed_inputs: ["diluted_eps"], shared_source_records: [{ concept: "EarningsPerShareDiluted", accn: "synthetic-filing", unit: "USD/share", start: "2025-01-01", end: "2025-12-31" }], status: "not_established" }], corroboration: { status: "unverified", reason: "Distinct methods share financial evidence." } };
  response.scenarios.base.independence = independence;
  const debt = { status: "conflict", effective_total_debt: null, unit: "USD", candidates: [{ id: "reported_total_debt", value: 15000000.125 }, { id: "short_term_plus_long_term", value: 16000000.25 }], comparisons: [{ left_candidate: "reported_total_debt", right_candidate: "short_term_plus_long_term", difference: -1000000.125, status: "conflict" }] };
  response.scenarios.base.data_completeness.financial_reconciliations = { debt };
  const before = structuredClone(response);
  const result = adaptProviderValuation(response);
  assert.deepEqual(result.scenarios.base.independence, independence);
  assert.equal(result.scenarios.bear.independence, null);
  assert.equal(result.scenarios.base.dataCompleteness.financial_reconciliations.debt.comparisons[0].difference, -1000000.125);
  assert.deepEqual(response, before);
});
