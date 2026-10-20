// Display formatting only. Never feed these strings into claims or validation.
const labels = {
  base_fair_value: "Base fair value", bear_fair_value: "Bear scenario fair value",
  bull_fair_value: "Bull scenario fair value", market_price: "Market price",
  base_contributing_model_count: "Contributing models", base_model_name: "Valuation method",
  base_model_results: "Model eligibility", valuation_methodology: "Valuation methodology",
  ebitda: "EBITDA", ebitda_margin: "EBITDA margin", target_pe: "Target P/E",
  forward_eps: "Forward EPS", wacc: "WACC", fcff: "FCFF", fcfe: "FCFE",
};

export function researchMetricLabel(metric) {
  return labels[metric] ?? String(metric ?? "Evidence").replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

export function formatResearchValue({ value, unit }) {
  if (!Number.isFinite(value)) return "Unavailable";
  const small = value !== 0 && Math.abs(value) < 0.01;
  const precision = small ? { maximumSignificantDigits: 3 } : { maximumFractionDigits: 2 };
  const format = (amount, options = {}) => new Intl.NumberFormat("en-US", { ...precision, ...options }).format(amount);
  const currency = /^([A-Z]{3})(\/shares?|\/year)?$/.exec(unit ?? "");
  if (currency) {
    const compact = !currency[2] && Math.abs(value) >= 1e6;
    return format(value, { style: "currency", currency: currency[1],
      ...(small ? {} : { minimumFractionDigits: 2 }), ...(compact ? { notation: "compact" } : {}) })
      + (currency[2]?.startsWith("/share") ? " / share" : currency[2] === "/year" ? " / year" : "");
  }
  if (unit === "fraction") return `${format(value * 100)}%`;
  if (unit === "percent") return `${format(value)}%`;
  if (unit === "multiple") return `${format(value)}×`;
  if (unit === "models" || unit === "count") return `${format(value)} ${unit === "models" ? Math.abs(value) === 1 ? "model" : "models" : ""}`.trim();
  if (unit === "shares") return `${format(value, Math.abs(value) >= 1e6 ? { notation: "compact" } : {})} shares`;
  if (unit === "years" || unit === "fiscal years") return `${format(value)} ${Math.abs(value) === 1 ? unit.slice(0, -1) : unit}`;
  return `${format(value)}${unit && !["number", "ratio"].includes(unit) ? ` ${unit}` : ""}`;
}

export function formatObservationDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}(?:T|$)/.test(value)) return null;
  // Keep the provider's observation calendar date; never substitute retrieval
  // time or the browser's local timezone for a dated financial observation.
  const calendar = value.slice(0, 10);
  const date = new Date(`${calendar}T00:00:00Z`);
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== calendar) return null;
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(date);
}

export function financialTerminologyNote(finding, evidence) {
  if (!/\bEBITDA\s*\/\s*EBITDA margin\b/i.test(finding.explanation)) return null;
  const summary = evidence.find((source) => finding.evidence_ids.includes(source.id) && source.metric === "base_model_results"
    && source.provider === "Fairworth Python valuation engine" && source.category === "valuation_output");
  const models = summary?.value?.models;
  if (!Array.isArray(models)) return null;
  const model = models.find((item) => typeof item.name === "string" && item.name.trim()
    && Array.isArray(item.missing_inputs) && item.missing_inputs.includes("ebitda_margin") && !item.missing_inputs.includes("ebitda"));
  return model ? `Engine input detail: ${model.name} lists EBITDA margin as missing. EBITDA margin and the EBITDA amount are distinct metrics.` : null;
}
