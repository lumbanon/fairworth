// Presentation only. Financial validity, status groups and counts come from Python.
import { formatResearchValue, researchMetricLabel } from "./researchPresentation.js";
import { safeEvidenceUrl } from "../services/aiResearch.js";

export const completenessGroups = [
  ["available", "Available inputs"], ["missing", "Missing inputs"],
  ["stale", "Stale observations"], ["incompatible", "Incompatible inputs"],
  ["restricted", "Provider restrictions"], ["derived", "Derived inputs"],
  ["policy", "Research policy"], ["user", "User overrides"],
];

export function diagnosticLabel(value) {
  return String(value ?? "Unavailable").replaceAll("_", " ");
}

export function diagnosticMessages(values = []) {
  const records = Array.isArray(values) ? values : values && typeof values === "object" ? Object.values(values) : [];
  return records.map((value) => typeof value === "string" ? value : value?.explanation || value?.message || value?.description).filter(Boolean);
}

// Present only explicit server assessments. A missing record is never an
// eligible model or a verified share/currency basis.
export function providerModelBlockers(eligibility = {}) {
  if (!Array.isArray(eligibility?.blockers)) return [];
  return eligibility.blockers.filter((blocker) => blocker && typeof blocker === "object" &&
    typeof blocker.code === "string" && typeof blocker.message === "string" && blocker.message.trim())
    .map((blocker) => ({ ...blocker, fields: Array.isArray(blocker.fields) ? blocker.fields.filter((field) => typeof field === "string") : [] }));
}

export function providerCompatibilityLabel(status) {
  return ({ available: "Available", unavailable: "Unavailable", incompatible: "Incompatible", stale: "Stale observation", unverified: "Unverified" })[status] || "Not assessed";
}

export function providerReportingPeriods(completeness = {}) {
  if (!Array.isArray(completeness?.reporting_periods)) return [];
  return completeness.reporting_periods.filter((period) => period && typeof period === "object")
    .map((period) => ({ ...period,
      available_metrics: Array.isArray(period.available_metrics) ? period.available_metrics.filter((metric) => typeof metric === "string") : null,
      missing_metrics: Array.isArray(period.missing_metrics) ? period.missing_metrics.filter((metric) => typeof metric === "string") : null,
      source_identifiers: Array.isArray(period.source_identifiers) ? period.source_identifiers.filter((source) => typeof source === "string") : [],
      warnings: diagnosticMessages(period.warnings),
    }));
}

export function completenessFieldLabel(key, field = {}) {
  return field.label || researchMetricLabel(String(key).split(".").at(-1));
}

export function completenessValue(field = {}) {
  if (typeof field.value === "boolean") return field.value ? "Confirmed" : "Not confirmed";
  if (Array.isArray(field.value)) {
    return field.value.every(Number.isFinite) ? field.value.map((value) => formatResearchValue({ value, unit: field.unit })).join(", ") : "See source record";
  }
  return formatResearchValue(field);
}

export function providerSourceLinks(field = {}) {
  const records = Array.isArray(field.provenance) ? field.provenance : [];
  const urls = [field.url, field.source_url, ...(records.flatMap((record) => [record?.url, record?.filing_url, record?.source_url, record?.source]))];
  return [...new Set(urls.map(safeEvidenceUrl).filter(Boolean))];
}
