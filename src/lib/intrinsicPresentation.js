// Presentation only: the backend determines calculation and comparison eligibility.
export function intrinsicEstimateLabel(intrinsic) {
  if (intrinsic?.status !== "available" || !Number.isFinite(intrinsic.value)) return "Intrinsic estimate unavailable";
  return intrinsic.classification === "user_defined"
    ? "User-assisted intrinsic estimate"
    : "Financial-evidence intrinsic estimate";
}

export function intrinsicHorizonLabel(horizon) {
  if (typeof horizon === "string") return horizon;
  if (!horizon || typeof horizon !== "object") return "Not supplied";
  if (horizon.description) return horizon.description;
  if (horizon.label) return [horizon.label, [horizon.first_forecast_start, horizon.first_forecast_end].filter(Boolean).join(" to ")].filter(Boolean).join(" · ");
  return [horizon.start_date, horizon.end_date, horizon.years != null && `${horizon.years} ${horizon.years === 1 ? "year" : "years"}`]
    .filter(Boolean).join(" · ") || "Not supplied";
}

export function comparisonStatusLabel(comparison) {
  return ({ available: "Compatible market comparison", user_provided: "User-provided comparison scenario", user_scenario: "User-provided comparison scenario",
    unavailable: "Market comparison unavailable", stale: "Dated market comparison unavailable", historical: "Historical market comparison" })[comparison?.status]
    ?? "Market comparison not assessed";
}

export function intrinsicAssumptionEntries(assumptions) {
  if (!assumptions || typeof assumptions !== "object" || Array.isArray(assumptions)) return [];
  return Object.entries(assumptions).map(([key, value]) => [key,
    value && typeof value === "object" ? value : { value }]);
}
