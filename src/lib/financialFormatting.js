const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});
const compact = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 2,
});
const numbers = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
export function dollars(value, currency = "USD") {
  if (!Number.isFinite(value)) return "—";
  if (currency === "USD") return money.format(value);
  return /^[A-Z]{3}$/.test(currency ?? "")
    ? new Intl.NumberFormat("en-US", {
        style: "currency",
        currency,
        maximumFractionDigits: 2,
      }).format(value)
    : `${numbers.format(value)} (currency unavailable)`;
}
export function totalDollars(millions, currency = "USD") {
  if (!Number.isFinite(millions)) return "—";
  if (currency === "USD") return compact.format(millions * 1e6);
  return /^[A-Z]{3}$/.test(currency ?? "")
    ? new Intl.NumberFormat("en-US", {
        style: "currency",
        currency,
        notation: "compact",
        maximumFractionDigits: 2,
      }).format(millions * 1e6)
    : `${numbers.format(millions)} million (currency unavailable)`;
}
export function percent(value, signed = false) {
  return Number.isFinite(value)
    ? `${signed && value > 0 ? "+" : ""}${value.toFixed(1)}%`
    : "—";
}
export function number(value) {
  return Number.isFinite(value) ? numbers.format(value) : "—";
}
export function direction(value) {
  return Number.isFinite(value)
    ? value < 0
      ? "negative"
      : value > 0
        ? "positive"
        : ""
    : "";
}
