import { useMemo } from "react";
import { calculateReverseDCF } from "@/valuation/reverseDCF";
import {
  calculationInputs,
  validateModelAssumptions,
} from "@/valuation/modelSelector";
import { percent } from "@/lib/financialFormatting";

function DemoReverseDCF({ company, valuation }) {
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

function ProviderReverseDCF({ valuation }) {
  const diagnostic = valuation.reverseDCF;
  return (
    <section id="reverse-dcf" className="research-section" aria-labelledby="reverse-heading">
      <div className="research-section-heading">
        <div>
          <h2 id="reverse-heading">What does the price imply?</h2>
          <p>Reverse DCF · Python diagnostic, excluded from weighted intrinsic value.</p>
        </div>
        <span className="research-caption">Base-case framework</span>
      </div>
      {diagnostic?.status === "valid" ? (
        <div className="reverse-dcf-results">
          <div>
            <span>Market-implied {diagnostic.solvedVariable || "growth"}</span>
            <strong data-testid="implied-growth">{percent(diagnostic.impliedGrowth * 100)}</strong>
          </div>
          <p>{diagnostic.explanation}</p>
        </div>
      ) : (
        <p className="research-unavailable">{diagnostic?.explanation || "A compatible market price and valid base-case FCFF assumptions are required."}</p>
      )}
      {diagnostic?.warnings?.map((warning, index) => <p className="research-caption" key={index}>{warning}</p>)}
      {diagnostic?.bounds && <p className="research-caption">Solver bounds: {percent(diagnostic.bounds[0] * 100)} to {percent(diagnostic.bounds[1] * 100)}. Convergence: {diagnostic.convergence || diagnostic.status}.</p>}
      <details className="provider-reverse-details"><summary>Assumptions held constant</summary><p className="research-caption">Base discount rate, terminal assumptions, share count, and enterprise-to-equity bridge. Implied growth depends on this framework and is not a forecast.</p>
        {Object.entries(diagnostic?.heldConstants ?? {}).map(([key, value]) => <p className="research-caption" key={key}><strong>{key.replaceAll("_", " ")}: </strong>{typeof value === "object" && value !== null ? JSON.stringify(value) : String(value)}</p>)}
      </details>
    </section>
  );
}

export default function ReverseDCF(props) {
  return props.valuation.providerMode
    ? <ProviderReverseDCF {...props} />
    : <DemoReverseDCF {...props} />;
}
