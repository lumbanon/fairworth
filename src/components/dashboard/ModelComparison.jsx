import { useState, lazy, Suspense } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { modelDefinitions } from "@/data/modelDefinitions";
import { dollars, percent, direction } from "@/lib/financialFormatting";
import { marketDistanceScale } from "@/lib/valuationChartColors";

const ComparisonChart = lazy(() => import("./ComparisonChart"));
const statuses = {
  valid: "Available",
  "not-applicable": "Not applicable",
  "insufficient-data": "Insufficient data",
  "invalid-input": "Invalid inputs",
};

export default function ModelComparison({
  company,
  valuation,
  setSelectedModel,
}) {
  const [details, setDetails] = useState(null);
  return (
    <section
      id="models"
      className="research-section"
      aria-labelledby="models-heading"
    >
      <div className="research-section-heading">
        <div>
          <h2 id="models-heading">Valuation models</h2>
          <p>
            Choose appropriate methods. Positive raw weights normalize
            automatically.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={valuation.resetWeights}>
          Reset Models & Weights
        </Button>
      </div>
      <div
        className="research-table-scroll"
        tabIndex={0}
        role="region"
        aria-label="Interactive valuation comparison"
      >
        <table className="research-table model-results-table">
          <thead>
            <tr>
              <th scope="col">Valuation model</th>
              <th scope="col">Fair value</th>
              <th scope="col">Upside / downside</th>
              <th scope="col">Weight</th>
              <th scope="col">Status</th>
              <th scope="col">Details</th>
            </tr>
          </thead>
          <tbody>
            {valuation.results.map((result) => {
              const isEnabled = valuation.enabled[result.id];
              const upside =
                result.status === "valid" &&
                Number.isFinite(company.price) &&
                company.price > 0
                  ? (result.fairValue / company.price - 1) * 100
                  : null;
              const normalized =
                (valuation.summary.normalizedWeights[result.id] ?? 0) * 100;
              return (
                <tr key={result.id}>
                  <th scope="row">
                    <label className="model-toggle">
                      <input
                        type="checkbox"
                        checked={isEnabled}
                        disabled={!result.applicable}
                        aria-label={`Enable ${result.name}`}
                        onChange={(event) =>
                          valuation.setEnabled((previous) => ({
                            ...previous,
                            [result.id]: event.target.checked,
                          }))
                        }
                      />
                      <span>{result.name}</span>
                    </label>
                  </th>
                  <td>{dollars(result.fairValue)}</td>
                  <td className={direction(upside)}>{percent(upside, true)}</td>
                  <td>
                    <Input
                      type="number"
                      min="0"
                      max="1000"
                      step="1"
                      disabled={!result.applicable || !isEnabled}
                      value={valuation.weights[result.id]}
                      aria-label={`${result.name} raw weight`}
                      className="research-weight-input"
                      onChange={(event) =>
                        valuation.setWeights((previous) => ({
                          ...previous,
                          [result.id]:
                            event.target.value === ""
                              ? ""
                              : Number(event.target.value),
                        }))
                      }
                    />
                    <span className="normalized-weight">
                      {isEnabled && result.status === "valid"
                        ? `${normalized.toFixed(1)}% normalized`
                        : "Not contributing"}
                    </span>
                  </td>
                  <td>
                    <span
                      className={`model-status ${result.status === "invalid-input" ? "negative" : ""}`}
                    >
                      {result.status === "valid" && !isEnabled
                        ? "Disabled"
                        : statuses[result.status]}
                    </span>
                  </td>
                  <td>
                    <button
                      className="research-text-button"
                      aria-expanded={details === result.id}
                      aria-controls={`details-${result.id}`}
                      aria-label={`Details for ${result.name}`}
                      onClick={() =>
                        setDetails(details === result.id ? null : result.id)
                      }
                    >
                      Details
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {details &&
        (() => {
          const model = modelDefinitions.find((item) => item.id === details);
          const result = valuation.results.find((item) => item.id === details);
          return (
            <div id={`details-${details}`} className="model-details">
              <h3>{model.name}</h3>
              <p>{model.description}</p>
              <p>
                <strong>Formula:</strong> {model.formula}
              </p>
              <p>
                <strong>Applicability:</strong> {model.condition}
              </p>
              <p>
                <strong>Required data:</strong>{" "}
                {model.requiredInputs.join(", ")}. Default raw weight:{" "}
                {model.defaultWeight}.
              </p>
              {result.warnings.map((warning) => (
                <p key={warning} className="negative">
                  {warning}
                </p>
              ))}
              {result.applicable && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setSelectedModel(model.id);
                    document.getElementById("assumptions")?.scrollIntoView();
                  }}
                >
                  Edit Assumptions
                </Button>
              )}
            </div>
          );
        })()}
      <div
        className="research-model-chart"
        role="img"
        aria-label="Horizontal comparison of available model fair values, weighted fair value, and reference market price. Bar colors show absolute percentage distance from the market price."
      >
        <Suspense fallback={<p>Loading model comparison…</p>}>
          <ComparisonChart
            results={valuation.results}
            enabled={valuation.enabled}
            fairValue={valuation.summary.fairValue}
            marketPrice={company.price}
          />
        </Suspense>
      </div>
      <p className="research-chart-key">
        <span>
          <i className="chart-key-line" aria-hidden="true" />
          Market price: {dollars(company.price)}
        </span>
        <span>
          <i className="chart-key-line chart-key-blue" aria-hidden="true" />
          Weighted estimate: {dollars(valuation.summary.fairValue)}
        </span>
      </p>
      <div
        className="research-distance-key"
        role="group"
        aria-label="Bar color scale"
      >
        <p>Absolute difference from market price</p>
        <div>
          {marketDistanceScale.map((band) => (
            <span key={band.label}>
              <i style={{ backgroundColor: band.color }} aria-hidden="true" />
              {band.label}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
