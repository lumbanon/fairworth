import test from "node:test";
import assert from "node:assert/strict";
import { adaptProviderValuation, emptyProviderValuation } from "../../src/lib/providerValuation.js";
import { adaptProviderStock } from "../../src/lib/providerCompatibility.js";
import { intrinsicEstimateLabel, intrinsicHorizonLabel, comparisonStatusLabel, intrinsicAssumptionEntries } from "../../src/lib/intrinsicPresentation.js";
import { providerValuationFixture } from "../helpers/providerValuationFixture.js";
import { providerFixture } from "../helpers/providerFixture.js";

test("intrinsic estimates require an explicit backend assessment and never become automatic defaults through presentation", () => {
  assert.equal(intrinsicEstimateLabel({ value: 20 }), "Intrinsic estimate unavailable");
  assert.equal(intrinsicEstimateLabel({ status: "available", value: Infinity }), "Intrinsic estimate unavailable");
  assert.equal(intrinsicEstimateLabel({ status: "available", value: 20, classification: "user_defined" }), "User-assisted intrinsic estimate");
  assert.equal(intrinsicEstimateLabel({ status: "available", value: 20, classification: "policy_based" }), "Financial-evidence intrinsic estimate");
});

test("intrinsic dates, forecasts and market-comparison classifications remain separate", () => {
  assert.equal(intrinsicHorizonLabel({ start_date: "2025-07-01", end_date: "2026-06-30", years: 1 }), "2025-07-01 · 2026-06-30 · 1 year");
  assert.equal(intrinsicHorizonLabel({ description: "Explicit dated dividend scenario" }), "Explicit dated dividend scenario");
  assert.equal(intrinsicHorizonLabel({ label: "Explicit annual scenario", first_forecast_start: "2026-07-01", first_forecast_end: "2027-06-30" }), "Explicit annual scenario · 2026-07-01 to 2027-06-30");
  assert.equal(intrinsicHorizonLabel(null), "Not supplied");
  assert.equal(comparisonStatusLabel({ status: "unavailable", price: 200 }), "Market comparison unavailable");
  assert.equal(comparisonStatusLabel({ status: "user_provided" }), "User-provided comparison scenario");
  assert.equal(comparisonStatusLabel(null), "Market comparison not assessed");
});

test("adapter preserves scenario-specific intrinsic provenance without inferring a missing market comparison", () => {
  const response = providerValuationFixture("MSFT", { price: null });
  const original = { status: "available", value: 20.123456789, currency: "USD", classification: "user_defined", financial_observation_date: "2025-06-30", source_identifiers: ["sec:original-filing"], assumptions: { dividend_growth: { value: 0.03, evidence_type: "user" } } };
  response.financial_coverage = { intrinsic: original, market_comparison: { status: "unavailable", price: null } };
  response.scenarios.bear.intrinsic = { ...original, value: 18 };
  const frozen = structuredClone(response);
  const adapted = adaptProviderValuation(response);
  assert.deepEqual(adapted.scenarios.base.intrinsic, original);
  assert.equal(adapted.scenarios.bear.intrinsic.value, 18);
  assert.equal(adapted.scenarios.bull.intrinsic, null);
  assert.equal(adapted.scenarios.base.marketComparison.status, "unavailable");
  assert.equal(adapted.comparisonPrice, null);
  assert.deepEqual(response, frozen);
  assert.equal(emptyProviderValuation().scenarios.base.intrinsic, null);
  assert.deepEqual(intrinsicAssumptionEntries(original.assumptions), Object.entries(original.assumptions));
});

test("financial import clocks remain distinct from reported financial observations", () => {
  const fixture = providerFixture();
  fixture.annual.financial_import = { import_batch_id: "synthetic-batch", imported_at: "2026-10-22T00:00:00Z", original_retrieved_at: "2026-10-20T12:00:00Z", cik: "0000000001" };
  const company = adaptProviderStock(fixture);
  assert.deepEqual(company.financialImport, fixture.annual.financial_import);
  assert.notEqual(company.latest.periodEnd, company.financialImport.imported_at);
});
