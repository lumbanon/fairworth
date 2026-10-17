import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { adaptProviderValuation, providerInputErrors, providerAssumptionEvidence, providerClassificationLabel, providerPeriodLabel } from "../../src/lib/providerValuation.js";
import { calculateValuation, loadValuationDefaults, loadValuationSensitivity } from "../../src/services/api.js";
import { providerValuationFixture, automaticProviderValuationFixture } from "../helpers/providerValuationFixture.js";

test("Provider presentation preserves authoritative Python values, distinct comparisons and currencies", () => {
  const fixture = providerValuationFixture("ORCL", { forceActive: true, price: null, fairValue: 777.77, currency: "EUR" });
  fixture.scenarios.base.summary.upside = 12.34;
  fixture.scenarios.base.summary.margin_of_safety = 8.76;
  fixture.scenarios.base.models.find((model) => model.id === "pe").upside = 92.5;
  fixture.warnings = [{ code: "restated_fact", field: "revenue", message: "FY2025 FY (2025-12-31): a filing revised this exact period.", source_id: "fixture:source:2025" }];
  const view = adaptProviderValuation(fixture, "ORCL");
  assert.equal(view.scenarios.base.results.find((model) => model.id === "pe").fairValue, 777.77);
  assert.equal(view.scenarios.base.results.find((model) => model.id === "pe").upside, 92.5);
  assert.equal(view.scenarios.base.summary.fairValue, 777.77);
  assert.equal(view.scenarios.base.summary.upside, 12.34);
  assert.equal(view.scenarios.base.summary.marginOfSafety, 8.76);
  assert.equal(view.comparisonPrice, null);
  assert.equal(view.currency, "EUR");
  assert.equal(view.defaults.base.values.shares, 12000000);
  assert.equal(view.scenarios.bear.summary.fairValue, 145);
  assert.equal(view.scenarios.bull.summary.fairValue, 195);
  assert.deepEqual(view.sourceNotices, fixture.warnings);
  assert.deepEqual(view.warnings, fixture.warnings.map((warning) => warning.message));
});

test("Provider adapter rejects missing scenarios, nonfinite results and another company without fallback", () => {
  assert.throws(() => adaptProviderValuation({}), /incomplete/);
  const fixture = providerValuationFixture();
  assert.throws(() => adaptProviderValuation(fixture, "AAPL"), /does not match/);
  delete fixture.scenarios.bull;
  assert.throws(() => adaptProviderValuation(fixture), /bull/);
  const invalid = providerValuationFixture("BRK-B");
  invalid.scenarios.base.models[0].fair_value = Infinity;
  assert.throws(() => adaptProviderValuation(invalid, "BRK.B"), /nonfinite/);
});

test("Valuation transport sends explicit assumptions and overrides as POST JSON in absolute units", async () => {
  const request = { assumptions: { earnings_growth: 0.1, shares: 12000000 }, scenario_overrides: { bear: { target_pe: 10 } }, weights: { pe: 70 }, enabled_models: ["pe"], manual_market_price: { value: 200, currency: "USD" } };
  const calls = [];
  const fetcher = async (url, options) => {
    calls.push({ url, ...options });
    return new Response(JSON.stringify(providerValuationFixture("ORCL", { request })));
  };
  await loadValuationDefaults("ORCL", { fetcher });
  await calculateValuation("ORCL", request, { fetcher });
  await loadValuationSensitivity("ORCL", { ...request, sensitivity: { model_id: "pe", x_parameter: "target_pe", y_parameter: "forward_eps" } }, { fetcher });
  assert.equal(calls[0].method, "GET");
  assert.equal(calls[1].method, "POST");
  assert.equal(calls[1].headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[1].body), request);
  assert.ok(calls[2].url.endsWith("/ORCL/valuation/sensitivity"));
  assert.equal(JSON.parse(calls[2].body).assumptions.shares, 12000000);
});

test("Provider editor guards empty and nonfinite values, negative weights and invalid comparison prices", () => {
  assert.deepEqual(providerInputErrors({ earnings_growth: -0.1, share_basis_confirmed: true, projected_fcff: [-20, 10] }, { bear: {} }, { pe: 0 }, null), []);
  assert.equal(providerInputErrors({ earnings_growth: "", wacc: NaN }, { bear: { target_pe: Infinity } }, { pe: -1 }, 0).length, 5);
  assert.match(providerInputErrors({ projected_fcff: [10, Infinity] }, {}, {}, null).join(" "), /finite annual values/);
  assert.deepEqual(providerInputErrors({ projected_revenue: [100, 110, 120] }, {}, {}, null), []);
  assert.match(providerInputErrors({ projected_revenue: [100, 0, -20] }, {}, {}, null).join(" "), /positive annual amounts/);
});

test("Provider hook and editor do not import Demo valuation calculations", async () => {
  for (const filename of ["src/hooks/useProviderValuation.js", "src/components/dashboard/ProviderAssumptionEditor.jsx", "src/components/dashboard/ProviderSensitivity.jsx", "src/lib/providerValuation.js"]) {
    const content = await readFile(new URL(`../../${filename}`, import.meta.url), "utf8");
    assert.doesNotMatch(content, /from\s+["'][^"']*(?:valuation\/(?:dcf|multiples|modelSelector|weighting|scenarios|reverseDCF)|hooks\/useValuation)/);
  }
});

test("Automatic assumption provenance, classifications and weighted composition preserve server evidence", () => {
  const fixture = automaticProviderValuationFixture();
  fixture.scenarios.base.summary.composition = [{ classification: "evidence_supported", weight: 0.6, model_ids: ["pe"] }, { classification: "policy_based", weight: 0.4, model_ids: ["fcff"] }];
  const view = adaptProviderValuation(fixture);
  assert.equal(view.scenarios.base.summary.classification, "evidence_supported");
  assert.deepEqual(view.scenarios.base.summary.composition, fixture.scenarios.base.summary.composition);
  assert.deepEqual(view.scenarios.base.metadata.target_pe, fixture.scenarios.base.assumptions.metadata.target_pe);
  assert.equal(view.scenarios.base.results.find((model) => model.id === "pe").sourceQuality.level, "medium");
  assert.equal(view.scenarios.base.results.find((model) => model.id === "pe").classification, "evidence_supported");
  assert.equal(view.assumptionMethodologyVersion, fixture.assumption_methodology_version);
  assert.deepEqual(view.snapshotDates, fixture.snapshot_dates);
  assert.deepEqual(view.sourceIdentifiers, fixture.source_identifiers);
  assert.match(view.scenarios.base.summary.sourceWarnings[0], /relevance review/);
});

test("Source presentation distinguishes verified facts, estimates, policies, user inputs and unknown dates", () => {
  assert.equal(providerAssumptionEvidence({ evidence_type: "fact", input_status: "verified_zero" }), "Reported or observed fact");
  assert.equal(providerAssumptionEvidence({ evidence_type: "estimate" }), "Derived or sourced estimate");
  assert.equal(providerAssumptionEvidence({ source_type: "benchmark_assumption" }), "Modeling policy");
  assert.equal(providerAssumptionEvidence({ evidence_type: "user" }), "User override");
  assert.equal(providerAssumptionEvidence({ source_type: "unavailable" }), "Unavailable");
  assert.equal(providerClassificationLabel("policy_based"), "Policy-based illustrative estimate");
  assert.equal(providerClassificationLabel("unknown"), null);
  assert.equal(providerPeriodLabel({ start: "2021-12-31", end: "2025-12-31" }), "2021-12-31 to 2025-12-31");
  assert.equal(providerPeriodLabel({ fiscal_year: 2025, fiscal_period: "FY" }), "FY 2025");
  assert.equal(providerPeriodLabel({ fiscal_years: [2021, 2022, 2023, 2024, 2025] }), "FY 2021–2025");
  assert.equal(providerPeriodLabel({ fiscal_years: [2021, 2023] }), "FY 2021, 2023");
  assert.equal(providerPeriodLabel(null), null);
});

test("Provider adapter remains compatible with responses that do not include Phase 4.5 classifications", () => {
  const view = adaptProviderValuation(providerValuationFixture());
  assert.equal(view.scenarios.base.summary.classification, null);
  assert.deepEqual(view.scenarios.base.summary.composition, []);
  assert.equal(view.scenarios.base.results[0].classification, null);
  assert.deepEqual(view.sourceIdentifiers, []);
});
