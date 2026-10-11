import { useMemo } from "react";
import { calculateReverseDCF } from "@/valuation/reverseDCF";
import {
  calculationInputs,
  validateModelAssumptions,
} from "@/valuation/modelSelector";
import { percent } from "@/lib/financialFormatting";

export default function ReverseDCF({ company, valuation }) {
  const applicable = valuation.scenarios.base.results.find(
    (result) => result.id === "fcff",
  ).applicable;
  const result = useMemo(() => {
    if (!applicable) return null;
    const error = validateModelAssumptions("fcff", valuation.assumptions.base);
    return error
      ? { ...error, impliedGrowth: null }
      : calculateReverseDCF(
          calculationInputs(company, valuation.assumptions.base),
          company.price,
        );
  }, [applicable, company, valuation.assumptions.base]);
  return (
    <section
      id="reverse-dcf"
      className="research-section"
      aria-labelledby="reverse-heading"
    >
      <div className="research-section-heading">
        <div>
          <h2 id="reverse-heading">What does the price imply?</h2>
          <p>
            Reverse DCF · a growth diagnostic, separate from the weighted
            valuation.
          </p>
        </div>
        <span className="research-caption">Base-case framework</span>
      </div>
      {!applicable ? (
        <p className="research-unavailable">
          Reverse DCF is not applicable: this dataset does not support a
          positive starting FCFF forecast.
        </p>
      ) : result.status !== "valid" ? (
        <div role="alert" className="research-warning">
          {result.warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      ) : (
        <div className="reverse-dcf-results">
          <div>
            <span>Market-implied FCFF growth</span>
            <strong data-testid="implied-growth">
              {percent(result.impliedGrowth * 100)}
            </strong>
          </div>
          <div>
            <span>Edited base-case FCFF growth</span>
            <strong>
              {percent(valuation.assumptions.base.cashFlowGrowth * 100)}
            </strong>
          </div>
          <p>
            Annual cash-flow growth that equates the same FCFF DCF to the
            illustrative price, holding base WACC, terminal growth, share count,
            and balance sheet adjustments fixed.
          </p>
        </div>
      )}
      <p className="research-caption">
        Solved by bisection within −50% to +100% annual growth. A solution
        depends on the model and its terminal assumptions; it is neither a
        forecast nor proof of market expectations. No bracketed solution is
        shown as unavailable.
      </p>
    </section>
  );
}
