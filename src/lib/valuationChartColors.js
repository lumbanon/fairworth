// Each threshold includes its upper bound: exactly 5% is red, 30% is lime.
export const marketDistanceScale = [
  { maxDistance: 5, color: "#EF4444", label: "0–5%" },
  { maxDistance: 10, color: "#F97316", label: ">5–10%" },
  { maxDistance: 20, color: "#F59E0B", label: ">10–20%" },
  { maxDistance: 30, color: "#84CC16", label: ">20–30%" },
  { maxDistance: Infinity, color: "#16A34A", label: ">30%" },
];

export function marketPriceDistance(fairValue, marketPrice) {
  if (
    !Number.isFinite(fairValue) ||
    !Number.isFinite(marketPrice) ||
    marketPrice <= 0
  )
    return null;
  const distance = Math.abs((fairValue - marketPrice) / marketPrice) * 100;
  return Number.isFinite(distance) ? distance : null;
}

export function marketDistanceColor(distance) {
  if (!Number.isFinite(distance) || distance < 0) return "#525252";
  return marketDistanceScale.find((band) => distance <= band.maxDistance).color;
}
