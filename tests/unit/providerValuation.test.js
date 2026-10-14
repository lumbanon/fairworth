import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { adaptProviderValuation, providerInputErrors } from "../../src/lib/providerValuation.js";
import { calculateValuation, loadValuationDefaults, loadValuationSensitivity } from "../../src/services/api.js";
import { providerValuationFixture } from "../helpers/providerValuationFixture.js";

test("Provider presentation preserves authoritative Python values, distinct comparisons and currencies", () => {
  const fixture = providerValuationFixture("ORCL", { forceActive: true, price: null, fairValue: 777.77, currency: "EUR" });
  fixture.scenarios.base.summary.upside = 12.34;
  fixture.scenarios.base.summary.margin_of_safety = 8.76;
  fixture.scenarios.base.models.find((model) => model.id === "pe").upside = 92.5;
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
});

test("Provider hook and editor do not import Demo valuation calculations", async () => {
  for (const filename of ["src/hooks/useProviderValuation.js", "src/components/dashboard/ProviderAssumptionEditor.jsx", "src/components/dashboard/ProviderSensitivity.jsx", "src/lib/providerValuation.js"]) {
    const content = await readFile(new URL(`../../${filename}`, import.meta.url), "utf8");
    assert.doesNotMatch(content, /from\s+["'][^"']*(?:valuation\/(?:dcf|multiples|modelSelector|weighting|scenarios|reverseDCF)|hooks\/useValuation)/);
  }
});
