import test from "node:test";
import assert from "node:assert/strict";
import { formatObservationDate, formatResearchValue, financialTerminologyNote, researchMetricLabel } from "../../src/lib/researchPresentation.js";

test("financial display rounds units without mutating exact claim values", () => {
  const claim = { value: 619.5604742486083, unit: "USD/share", period: "FY2026" };
  const before = structuredClone(claim);
  assert.equal(formatResearchValue(claim), "$619.56 / share");
  assert.deepEqual(claim, before);
  assert.equal(formatResearchValue({ value: 539.44, unit: "USD/share" }), "$539.44 / share");
  assert.equal(formatResearchValue({ value: 125000000, unit: "USD" }), "$125.00M");
  assert.equal(formatResearchValue({ value: 29.40123247853427, unit: "multiple" }), "29.4×");
  assert.equal(formatResearchValue({ value: 1, unit: "models" }), "1 model");
  assert.equal(formatResearchValue({ value: 2, unit: "models" }), "2 models");
  assert.equal(formatResearchValue({ value: 0.1234567, unit: "fraction" }), "12.35%");
  assert.equal(formatResearchValue({ value: 12.34567, unit: "percent" }), "12.35%");
  assert.equal(formatResearchValue({ value: 0, unit: "USD/share" }), "$0.00 / share");
  assert.equal(formatResearchValue({ value: -195.555, unit: "USD/share" }), "-$195.56 / share");
});

test("small valid values stay nonzero and unavailable values are not fabricated", () => {
  assert.equal(formatResearchValue({ value: 0.000004567, unit: "USD/share" }), "$0.00000457 / share");
  for (const value of [null, undefined, NaN, Infinity, "123", true]) assert.equal(formatResearchValue({ value, unit: "USD" }), "Unavailable");
  assert.equal(formatResearchValue({ value: 7430000000, unit: "shares" }), "7.43B shares");
  assert.equal(formatResearchValue({ value: 0.12345, unit: "ratio" }), "0.12");
});

test("observation calendar date never uses retrieval time or local browser time", () => {
  assert.equal(formatObservationDate("2026-10-15T20:00:01+00:00"), "Oct 15, 2026");
  assert.equal(formatObservationDate("2026-10-15T23:30:00-07:00"), "Oct 15, 2026");
  assert.equal(formatObservationDate("2026-10-15"), "Oct 15, 2026");
  for (const value of [null, "unknown", "2026-02-30", "2026-13-01"]) assert.equal(formatObservationDate(value), null);
});

test("metric labels and source-backed clarification distinguish EBITDA margin", () => {
  assert.equal(researchMetricLabel("ebitda"), "EBITDA");
  assert.equal(researchMetricLabel("ebitda_margin"), "EBITDA margin");
  const finding = { explanation: "Missing EBITDA/EBITDA margin inputs.", evidence_ids: ["engine"] };
  const sources = [{ id: "engine", metric: "base_model_results", provider: "Fairworth Python valuation engine", category: "valuation_output",
    value: { models: [{ name: "EV/EBITDA", missing_inputs: ["ebitda_margin"] }] } }];
  assert.match(financialTerminologyNote(finding, sources), /EV\/EBITDA lists EBITDA margin as missing/);
  assert.equal(financialTerminologyNote({ ...finding, evidence_ids: [] }, sources), null);
  assert.equal(financialTerminologyNote(finding, []), null);
  for (const mutation of [{ provider: "unknown" }, { category: "unavailable" }, { category: "interpretation" }]) {
    assert.equal(financialTerminologyNote(finding, [{ ...sources[0], ...mutation }]), null);
  }
  sources[0].value.models[0].missing_inputs = ["ebitda"];
  assert.equal(financialTerminologyNote(finding, sources), null);
});
