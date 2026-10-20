import { useMemo, useState } from "react";
import { calculateFCFF } from "@/valuation/dcf";
import { calculatePE } from "@/valuation/multiples";
import {
  calculationInputs,
  validateModelAssumptions,
} from "@/valuation/modelSelector";
import { dollars, percent, number } from "@/lib/financialFormatting";
import ProviderSensitivity from "./ProviderSensitivity";

function DemoSensitivityTable({ company, valuation }) {
  const availableDCF = valuation.scenarios.base.results.find(
    (result) => result.id === "fcff",
  ).applicable;
  const availablePE = valuation.scenarios.base.results.find(
    (result) => result.id === "pe",
  ).applicable;
  const [selection, setSelection] = useState(availableDCF ? "dcf" : "pe");
  const kind = selection === "dcf" && !availableDCF ? "pe" : selection;
  const data = useMemo(() => {
    if (
      validateModelAssumptions(
        kind === "dcf" ? "fcff" : "pe",
        valuation.assumptions.base,
      )
    )
      return null;
    const base = calculationInputs(company, valuation.assumptions.base);
    if (kind === "dcf") {
      if (
        ![base.wacc, base.terminalGrowth].every(
          (value) => typeof value === "number" && Number.isFinite(value),
        )
      )
        return null;
      const rows = [-0.01, -0.005, 0, 0.005, 0.01].map(
        (offset) => base.wacc + offset,
      );
      const columns = [-0.01, -0.005, 0, 0.005, 0.01].map(
        (offset) => base.terminalGrowth + offset,
      );
      return {
        rows,
        columns,
        values: rows.map((wacc) =>
          columns.map((terminalGrowth) =>
            calculateFCFF({ ...base, wacc, terminalGrowth }),
          ),
        ),
      };
    }
    if (
      ![base.netIncome, base.shares, base.epsGrowth, base.targetPE].every(
        (value) => typeof value === "number" && Number.isFinite(value),
      ) ||
      base.shares <= 0
    )
      return null;
    const forwardEPS = (base.netIncome / base.shares) * (1 + base.epsGrowth);
    const rows = [0.8, 0.9, 1, 1.1, 1.2].map((factor) => forwardEPS * factor);
    const columns = [-4, -2, 0, 2, 4].map((offset) => base.targetPE + offset);
    return {
      rows,
      columns,
      values: rows.map((eps) =>
        columns.map((targetPE) =>
          calculatePE({
            netIncome: eps * base.shares,
            shares: base.shares,
            epsGrowth: 0,
            targetPE,
          }),
        ),
      ),
    };
  }, [company, valuation.assumptions.base, kind]);
  return (
    <section
      id="sensitivity"
      className="research-section"
      aria-labelledby="sensitivity-heading"
    >
      <div className="research-section-heading">
        <div>
          <h2 id="sensitivity-heading">Sensitivity analysis</h2>
          <p>
            Calculated from the edited base case. The outlined center cell uses
            current base assumptions.
          </p>
        </div>
        <div
          className="research-segmented"
          role="group"
          aria-label="Sensitivity model"
        >
          <button
            disabled={!availableDCF}
            aria-pressed={kind === "dcf"}
            onClick={() => setSelection("dcf")}
          >
            FCFF DCF
          </button>
          <button
            disabled={!availablePE}
            aria-pressed={kind === "pe"}
            onClick={() => setSelection("pe")}
          >
            Forward P/E
          </button>
        </div>
      </div>
      {!availableDCF && !availablePE ? (
        <p className="research-unavailable">
          DCF and P/E sensitivity are not applicable to this dataset.
        </p>
      ) : !data ? (
        <p role="alert" className="research-warning">
          Enter valid base-case inputs to calculate sensitivity.
        </p>
      ) : (
        <>
          <p className="research-caption">
            Rows: {kind === "dcf" ? "WACC" : "forward EPS"} · Columns:{" "}
            {kind === "dcf" ? "terminal growth" : "target P/E"} · USD per share
          </p>
          <div
            className="research-table-scroll"
            tabIndex={0}
            role="region"
            aria-label="Sensitivity matrix"
          >
            <table className="research-table sensitivity-matrix">
              <thead>
                <tr>
                  <th scope="col">
                    {kind === "dcf" ? "WACC / g" : "EPS / P/E"}
                  </th>
                  {data.columns.map((column, index) => (
                    <th key={index} scope="col">
                      {kind === "dcf"
                        ? percent(column * 100)
                        : `${number(column)}×`}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    <th scope="row">
                      {kind === "dcf" ? percent(row * 100) : dollars(row)}
                    </th>
                    {data.values[rowIndex].map((result, columnIndex) => (
                      <td
                        key={columnIndex}
                        data-testid={
                          rowIndex === 2 && columnIndex === 2
                            ? "sensitivity-current"
                            : undefined
                        }
                        className={`${rowIndex === 2 && columnIndex === 2 ? "sensitivity-current" : ""} ${result.status === "valid" ? (Number.isFinite(company.price) ? (result.fairValue >= company.price ? "sensitivity-above" : "sensitivity-below") : "") : "sensitivity-invalid"}`}
                        title={result.warnings.join(" ")}
                      >
                        {result.status === "valid"
                          ? dollars(result.fairValue)
                          : "Invalid"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="research-caption">
            Invalid combinations are excluded rather than shown as zero. Each
            valid cell runs the same valuation formula.
          </p>
        </>
      )}
    </section>
  );
}

export default function SensitivityTable(props) {
  return props.valuation.providerMode
    ? <ProviderSensitivity {...props} />
    : <DemoSensitivityTable {...props} />;
}
