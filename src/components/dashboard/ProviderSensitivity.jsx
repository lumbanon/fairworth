import { dollars, number, percent } from "@/lib/financialFormatting";

const labels = { pe: "Forward P/E", fcff: "FCFF DCF · WACC / terminal growth", fcffOperating: "FCFF DCF · growth / margin", fcfe: "FCFE DCF", evEbitda: "EV/EBITDA", evRevenue: "EV/Revenue" };
const ratioParameters = new Set(["wacc", "cost_of_equity", "terminal_growth", "revenue_growth", "operating_margin"]);
function axisValue(value, parameter, currency) {
  if (ratioParameters.has(parameter)) return percent(value * 100);
  if (["forward_eps", "forecast_ebitda", "forecast_revenue"].includes(parameter)) return dollars(value, currency);
  return `${number(value)}×`;
}

export default function ProviderSensitivity({ company, valuation }) {
  const data = valuation.sensitivity;
  const middleRow = data ? Math.floor(data.y_values.length / 2) : 0;
  const middleColumn = data ? Math.floor(data.x_values.length / 2) : 0;
  return (
    <section id="sensitivity" className="research-section" aria-labelledby="sensitivity-heading">
      <div className="research-section-heading"><div><h2 id="sensitivity-heading">Sensitivity analysis</h2><p>Each cell runs the Python model with edited base assumptions. Invalid combinations remain unavailable.</p></div></div>
      <div className="assumption-model-select"><label htmlFor="provider-sensitivity-model">Sensitivity model</label>
        <select id="provider-sensitivity-model" value={valuation.sensitivitySelection} onChange={(event) => valuation.setSensitivitySelection(event.target.value)}>
          {Object.entries(labels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
      </div>
      {!data?.rows?.length ? <p className="research-unavailable">Valid base-case model inputs are required for sensitivity. No client-side estimates are substituted.</p> : <>
        <p className="research-caption">Rows: {data.y_parameter.replaceAll("_", " ")} · Columns: {data.x_parameter.replaceAll("_", " ")} · {data.unit}</p>
        <div className="research-table-scroll" tabIndex={0} role="region" aria-label="Sensitivity matrix">
          <table className="research-table sensitivity-matrix"><thead><tr><th scope="col">Base assumptions</th>{data.x_values.map((value, index) => <th key={index} scope="col">{axisValue(value, data.x_parameter, company.currency)}</th>)}</tr></thead>
            <tbody>{data.rows.map((row, rowIndex) => <tr key={rowIndex}><th scope="row">{axisValue(row.y_value, data.y_parameter, company.currency)}</th>
              {row.cells.map((cell, columnIndex) => <td key={columnIndex}
                data-testid={rowIndex === middleRow && columnIndex === middleColumn ? "sensitivity-current" : undefined}
                className={`${rowIndex === middleRow && columnIndex === middleColumn ? "sensitivity-current" : ""} ${cell.status === "valid" ? "" : "sensitivity-invalid"}`}
                title={(cell.warnings ?? []).join(" ")}>{cell.status === "valid" ? dollars(cell.fair_value, company.currency) : "Unavailable"}</td>)}
            </tr>)}</tbody>
          </table>
        </div>
      </>}
      {data?.warnings?.map((warning, index) => <p className="research-caption" key={index}>{typeof warning === "string" ? warning : warning.message}</p>)}
    </section>
  );
}
