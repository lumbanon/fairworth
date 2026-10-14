import { dollars, number, percent } from "@/lib/financialFormatting";

const fractionFields = new Set(["discount_rate", "terminal_growth", "terminal_value_contribution", "earnings_growth", "terminal_roe", "terminal_payout_ratio", "tax_rate"]);
const scalarFields = new Set(["shares", "forecast_years", "multiple", "target_pe", "target_peg", "justified_pe", "growth_percentage_points"]);
function formatValue(key, value, currency) {
  if (!Number.isFinite(value)) return typeof value === "boolean" ? String(value) : String(value ?? "Unavailable");
  if (fractionFields.has(key)) return percent(value * 100);
  return scalarFields.has(key) ? number(value) : dollars(value, currency);
}

export default function ProviderCalculationDetails({ details, currency }) {
  const entries = Object.entries(details).filter(([, value]) => value == null || ["number", "string", "boolean"].includes(typeof value));
  const projection = details.projection;
  const columns = ["year", "revenue", "cash_flow", "net_income", "residual_income", "present_value"].filter((key) => projection?.some((row) => Object.hasOwn(row, key)));
  return (
    <details className="provider-calculation-details"><summary>Calculation breakdown and financial basis</summary>
      <p className="research-caption">These amounts are returned by Python in {currency}; share counts use actual shares. Enterprise value and equity value are shown separately.</p>
      {entries.map(([key, value]) => <p className="research-caption" key={key}><strong>{key.replaceAll("_", " ")}: </strong>{formatValue(key, value, currency)}</p>)}
      {projection?.length > 0 && <div className="research-table-scroll" role="region" tabIndex={0} aria-label="Python cash flow projection"><table className="research-table"><thead><tr>{columns.map((key) => <th key={key} scope="col">{key.replaceAll("_", " ")}</th>)}</tr></thead>
        <tbody>{projection.map((row, index) => <tr key={index}>{columns.map((key) => <td key={key}>{key === "year" ? number(row[key]) : dollars(row[key], currency)}</td>)}</tr>)}</tbody>
      </table></div>}
    </details>
  );
}
