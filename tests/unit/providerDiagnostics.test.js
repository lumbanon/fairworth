import test from "node:test";
import assert from "node:assert/strict";
import { adaptProviderValuation, emptyProviderValuation, providerRequiredInputPaths } from "../../src/lib/providerValuation.js";
import { completenessFieldLabel, completenessGroups, completenessValue, diagnosticLabel, diagnosticMessages, providerSourceLinks, providerModelBlockers, providerReportingPeriods, providerCompatibilityLabel } from "../../src/lib/providerDiagnostics.js";
import { providerValuationFixture } from "../helpers/providerValuationFixture.js";
import { providerDiagnosticsFixture } from "../helpers/providerDiagnosticsFixture.js";

test("Phase 6 adapter preserves Python diagnostics, exact financials and all scenario provenance unchanged", () => {
  const response = providerDiagnosticsFixture();
  const before = structuredClone(response);
  const view = adaptProviderValuation(response, "MSFT");
  assert.deepEqual(response, before);
  assert.deepEqual(view.financials, response.financials);
  assert.deepEqual(view.automaticEvidence, response.automatic_evidence);
  for (const name of ["bear", "base", "bull"]) {
    assert.deepEqual(view.scenarios[name].diagnostics, response.scenarios[name].diagnostics);
    assert.deepEqual(view.scenarios[name].dataCompleteness, response.scenarios[name].data_completeness);
    assert.equal(view.scenarios[name].summary.fairValue, response.scenarios[name].summary.fair_value);
  }
  assert.equal(view.scenarios.base.dataCompleteness.fields["reported.revenue"].value, 125000000.125);
});

test("diagnostics remain optional for legacy responses and errors never fabricate coverage", () => {
  const legacy = adaptProviderValuation(providerValuationFixture());
  assert.equal(legacy.diagnostics, null);
  assert.equal(legacy.dataCompleteness, null);
  assert.deepEqual(legacy.financials, {});
  assert.deepEqual(legacy.automaticEvidence, {});
  assert.equal(emptyProviderValuation().scenarios.base.diagnostics, null);
  const partial = providerDiagnosticsFixture();
  delete partial.scenarios.base.data_completeness;
  delete partial.scenarios.bear.data_completeness;
  const adapted = adaptProviderValuation(partial);
  assert.deepEqual(adapted.scenarios.base.dataCompleteness, partial.data_completeness);
  assert.equal(adapted.scenarios.bear.dataCompleteness, null);
});

test("related-model coverage and negative comparisons are presented exactly as supplied by Python", () => {
  const view = adaptProviderValuation(providerDiagnosticsFixture("NVDA", { mode: "correlated" }));
  assert.equal(view.scenarios.base.diagnostics.coverage.contributing_count, 2);
  assert.equal(view.scenarios.base.diagnostics.coverage.method_family_count, 1);
  assert.equal(view.scenarios.base.confidence.level, "low");
  assert.equal(view.scenarios.base.summary.upside, -12.34);
  assert.equal(view.scenarios.base.summary.fairValue, 701.183);
  assert.deepEqual(view.scenarios.base.diagnostics.aggregation.shared_assumptions, [{ key: "forward_eps", model_ids: ["pe", "peg"] }]);
});

test("data completeness formatting rounds only display strings and preserves unavailable values", () => {
  const field = providerDiagnosticsFixture().data_completeness.fields["reported.revenue"];
  const before = structuredClone(field);
  assert.equal(completenessValue(field), "$125.00M");
  assert.deepEqual(field, before);
  assert.equal(completenessValue({ value: 0, unit: "USD" }), "$0.00");
  assert.equal(completenessValue({ value: null, unit: "USD" }), "Unavailable");
  assert.equal(completenessValue({ value: 0.105678, unit: "fraction" }), "10.57%");
  assert.equal(completenessValue({ value: true }), "Confirmed");
  assert.equal(completenessValue({ value: [1, 2], unit: "USD" }), "$1.00, $2.00");
  assert.equal(completenessValue({ value: [1, null], unit: "USD" }), "See source record");
  assert.equal(completenessFieldLabel("assumptions.wacc"), "WACC");
  assert.equal(completenessFieldLabel("assumptions.wacc", { label: "Company discount rate" }), "Company discount rate");
  assert.equal(diagnosticLabel("user_defined"), "user defined");
  assert.equal(completenessGroups.length, 8);
});

test("provenance links reject credentials and unsafe protocols without inventing filing URLs", () => {
  assert.deepEqual(providerSourceLinks({ provenance: [{ source: "SEC EDGAR", filing_url: "https://www.sec.gov/Archives/edgar/data/1/fixture.htm" }, { source: "https://www.sec.gov/Archives/edgar/data/1/fixture.htm" }, { url: "javascript:alert(1)" }, { url: "https://person:password@example.com/" }, { url: "http://example.com" }, { url: "https://financialmodelingprep.com/stable/quote?apikey=private" }] }), ["https://www.sec.gov/Archives/edgar/data/1/fixture.htm"]);
  assert.deepEqual(providerSourceLinks({ source_identifiers: ["fixture:accn:1"] }), []);
  assert.deepEqual(diagnosticMessages([{ explanation: "Verified source" }, { message: "Missing input" }, "Policy" ]), ["Verified source", "Missing input", "Policy"]);
  assert.deepEqual(diagnosticMessages({ first: { description: "Dated quote" } }), ["Dated quote"]);
});

test("model input alternatives retain their grouping and expose individual assumption keys for sources", () => {
  const paths = [["projected_fcff", "wacc"], ["ebit", "tax_rate", "wacc"]];
  const response = providerDiagnosticsFixture();
  response.scenarios.base.models[0].eligibility.required_inputs = paths;
  const view = adaptProviderValuation(response);
  assert.deepEqual(view.scenarios.base.results[0].definition.requiredInputPaths, paths);
  assert.deepEqual(view.scenarios.base.results[0].definition.requiredInputs, ["projected_fcff", "wacc", "ebit", "tax_rate"]);
  assert.deepEqual(providerRequiredInputPaths(["forward_eps", "target_pe"]), [["forward_eps", "target_pe"]]);
  assert.deepEqual(providerRequiredInputPaths(null), []);
  assert.deepEqual(providerRequiredInputPaths([{}, null, ["wacc", null]]), [["wacc"]]);
});

test("Phase 6.7 keeps each independent model blocker and reporting period without altering server eligibility", () => {
  const response = providerDiagnosticsFixture("ORCL", { mode: "none", price: null });
  const before = structuredClone(response);
  const view = adaptProviderValuation(response);
  const model = view.scenarios.base.results.find((result) => result.id === "fcfe");
  assert.deepEqual(providerModelBlockers(model.eligibility), response.scenarios.base.models.find((result) => result.id === "fcfe").eligibility.blockers);
  assert.deepEqual(providerModelBlockers(model.eligibility).map((blocker) => blocker.code), ["required_metric_missing", "share_basis_unverified"]);
  const periods = providerReportingPeriods(view.scenarios.base.dataCompleteness);
  assert.deepEqual(periods.map((period) => period.end_date), ["2025-12-31", "2024-12-31"]);
  assert.deepEqual(periods[0].available_metrics, ["revenue", "net_income", "total_debt"]);
  assert.deepEqual(periods[1].source_identifiers, ["fixture:revenue:2024"]);
  assert.equal(view.scenarios.base.summary.fairValue, null);
  assert.equal(model.fairValue, null);
  assert.deepEqual(response, before);
});

test("partial coverage remains unassessed and no client default creates compatibility or missing-input proof", () => {
  assert.equal(providerCompatibilityLabel(undefined), "Not assessed");
  assert.equal(providerCompatibilityLabel("invented"), "Not assessed");
  assert.equal(providerCompatibilityLabel("unverified"), "Unverified");
  assert.equal(providerCompatibilityLabel("stale"), "Stale observation");
  assert.deepEqual(providerModelBlockers(null), []);
  assert.deepEqual(providerModelBlockers({ reason: "Unavailable", missing_inputs: ["debt"] }), []);
  assert.deepEqual(providerModelBlockers({ blockers: [null, {}, { code: "required_metric_missing", message: "", fields: ["debt"] }] }), []);
  assert.deepEqual(providerReportingPeriods(), []);
  const partial = providerReportingPeriods({ reporting_periods: [null, { fiscal_year: 2025, available_metrics: [null, "revenue"], warnings: [{ message: "Period remains incomplete." }] }] });
  assert.deepEqual(partial[0].available_metrics, ["revenue"]);
  assert.equal(partial[0].missing_metrics, null);
  assert.deepEqual(partial[0].warnings, ["Period remains incomplete."]);
});
