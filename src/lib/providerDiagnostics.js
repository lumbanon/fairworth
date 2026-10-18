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
