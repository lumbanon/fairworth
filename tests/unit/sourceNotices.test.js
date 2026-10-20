import test from "node:test";
import assert from "node:assert/strict";
import { companyDescriptionPreview, groupSourceNotices, isHistoricalNotice, noticePeriodSummary } from "../../src/lib/sourceNotices.js";

test("historical notices group by issue type without losing original messages, periods or provenance", () => {
  const notices = [
    { code: "restated_fact", field: "revenue", message: "FY2025 FY (2025-06-30): a later filing revised this exact reporting period.", source_id: "fixture:filing:2025" },
    { code: "restated_fact", field: "net_income", message: "FY2024 Q2 (2023-12-31): a later filing revised this exact reporting period.", source_id: "fixture:filing:2024" },
    { code: "restated_fact", field: "revenue", message: "FY2025 FY (2025-06-30): a later filing revised this exact reporting period.", source_id: "fixture:filing:2025" },
    { code: "incomplete_debt_components", field: "total_debt", message: "FY2025 FY (2025-06-30): current maturities of long-term debt are unavailable." },
  ];
  const groups = groupSourceNotices(notices);
  assert.equal(groups.length, 2);
  assert.deepEqual(groups[0].notices, notices.slice(0, 3));
  assert.equal(groups[0].notices[0], notices[0]);
  assert.equal(groups[0].notices[0].source_id, "fixture:filing:2025");
  assert.deepEqual(groups[0].fields, ["revenue", "net_income"]);
  assert.deepEqual(groups[0].periods.map((period) => period.label), ["FY2024 Q2 (2023-12-31)", "FY2025 FY (2025-06-30)"]);
  assert.equal(noticePeriodSummary(groups[0].periods), "FY 2024–2025 · 2 reporting periods");
  assert.equal(groups[0].message, "a later filing revised this exact reporting period.");
});

test("current and material valuation warnings are kept distinct from historical financial notices", () => {
  const current = [
    { code: "missing_share_count", message: "The market provider did not supply a usable current share count." },
    "Single-model estimate: there is no independent model confirmation.",
    "A dated comparison price is unavailable.",
    "The model denominator is an annual historical diluted share count.",
  ];
  assert.ok(current.every((notice) => !isHistoricalNotice(notice)));
  const legacy = "FY2026 Q1 (2025-09-30): complete debt components are unavailable.";
  assert.equal(isHistoricalNotice(legacy), true);
  assert.equal(groupSourceNotices([legacy, "FY2025 Q1 (2024-09-30): complete debt components are unavailable."]).length, 1);
  assert.equal(noticePeriodSummary([{ year: 2021 }, { year: 2023 }, { year: 2024 }]), "FY 2021, 2023–2024 · 3 reporting periods");
  assert.equal(noticePeriodSummary([]), "No reporting period specified");
});

test("overview preview stays concise and retains the exact complete provider description for expansion", () => {
  const full = "A provider description with business segments and financial context. ".repeat(20);
  const description = companyDescriptionPreview(full);
  assert.equal(description.expandable, true);
  assert.ok(description.preview.length <= 280);
  assert.ok(description.preview.length >= 250);
  assert.ok(description.preview.endsWith("…"));
  assert.equal(description.full, full.trim());
  assert.equal(companyDescriptionPreview("Short company overview.").preview, "Short company overview.");
  assert.equal(companyDescriptionPreview("Short company overview.").expandable, false);
  assert.equal(companyDescriptionPreview(null).full, "");
});
