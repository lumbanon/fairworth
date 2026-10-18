import { useState, lazy, Suspense } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { modelDefinitions } from "@/data/modelDefinitions";
import { dollars, percent, direction } from "@/lib/financialFormatting";
import { marketDistanceScale } from "@/lib/valuationChartColors";
import { providerClassificationLabel } from "@/lib/providerValuation";
import ProviderCalculationDetails from "./ProviderCalculationDetails";
import ProviderAssumptionSource from "./ProviderAssumptionSource";
import { completenessValue, diagnosticLabel } from "@/lib/providerDiagnostics";
import ProviderModelInputPaths from "./ProviderModelInputPaths";

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
                valuation.providerMode ? result.upside : result.status === "valid" &&
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
                  <td>{dollars(result.fairValue, valuation.providerMode ? company.currency : "USD")}</td>
                  <td className={direction(upside)}>{percent(upside, true)}</td>
                  <td>
                    <Input
                      type="number"
                      min="0"
                      max="1000"
                      step="1"
                      disabled={!result.applicable || !isEnabled}
                      value={valuation.weights[result.id] ?? 0}
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
                    {valuation.providerMode && result.classification && <span className="normalized-weight">{providerClassificationLabel(result.classification) || "Classification unavailable"}</span>}
                    {valuation.providerMode && (typeof result.sourceQuality === "string" || result.sourceQuality?.level) && <span className="normalized-weight">Source quality: {typeof result.sourceQuality === "string" ? result.sourceQuality : result.sourceQuality.level}</span>}
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
          const result = valuation.results.find((item) => item.id === details);
          const model = valuation.providerMode
            ? result.definition
            : modelDefinitions.find((item) => item.id === details);
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
                {model.requiredInputPaths?.length > 1 ? "Review the alternative financial input paths below" : model.requiredInputs.join(", ")}. Suggested raw weight:{" "}
                {valuation.providerMode ? valuation.suggestedWeights[result.id] ?? 0 : model.defaultWeight}.
              </p>
              {result.warnings.map((warning) => (
                <p key={warning} className="negative">
                  {warning}
                </p>
              ))}
              {valuation.providerMode && result.classificationReasons?.map((reason) => <p className="research-caption" key={reason}>{reason}</p>)}
              {valuation.providerMode && result.eligibility.missing_inputs?.length > 0 && <p className="research-caption"><strong>Missing inputs: </strong>{result.eligibility.missing_inputs.map((field) => field.replaceAll("_", " ")).join(", ")}. Provide a supported assumption or review the source basis. Missing financial facts remain unavailable.</p>}
              {valuation.providerMode && result.sourceQuality?.warnings?.map((warning, index) => <p className="research-caption" key={index}>{typeof warning === "string" ? warning : warning.message}</p>)}
              {valuation.providerMode && <p className="research-caption"><strong>Weight basis: </strong>{diagnosticLabel(valuation.diagnostics?.aggregation?.per_model_weight_sources?.[result.id] ?? "Basis not supplied")}. {result.eligibility.weight_explanation || "Configured weights are normalized across contributing eligible models."}</p>}
              {valuation.providerMode && <ProviderModelInputPaths paths={result.eligibility.input_paths} />}
              {valuation.providerMode && result.definition.requiredInputs.some((key) => valuation.assumptionMetadata?.[key]) && <details className="provider-model-assumptions"><summary>Main assumptions and sources</summary>
                {result.definition.requiredInputs.filter((key) => valuation.assumptionMetadata?.[key]).map((key) => <div key={key} className="provider-assumption-record"><h4>{diagnosticLabel(key)} · {completenessValue(valuation.assumptionMetadata[key])}</h4><ProviderAssumptionSource metadata={valuation.assumptionMetadata[key]} overridden={valuation.overriddenKeys?.includes(key)} /></div>)}
              </details>}
              {valuation.providerMode && <ProviderCalculationDetails details={result.details} currency={company.currency} />}
              {(result.applicable || valuation.providerMode) && (
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
            marketPrice={valuation.providerMode ? valuation.comparisonPrice : company.price}
            currency={valuation.providerMode ? company.currency : "USD"}
          />
        </Suspense>
      </div>
      <p className="research-chart-key">
        <span>
          <i className="chart-key-line" aria-hidden="true" />
          {valuation.providerMode && valuation.market?.source_type === "user" ? "User-provided market price" : "Market price"}: {dollars(valuation.providerMode ? valuation.comparisonPrice : company.price, valuation.providerMode ? company.currency : "USD")}
        </span>
        <span>
          <i className="chart-key-line chart-key-blue" aria-hidden="true" />
          Weighted estimate: {dollars(valuation.summary.fairValue, valuation.providerMode ? company.currency : "USD")}
        </span>
      </p>
      <div
        className="research-distance-key"
        role="group"
        aria-label="Bar color scale"
      >
        <p>{valuation.providerMode && valuation.comparisonPrice == null ? "Comparison price unavailable · neutral bars" : "Absolute difference from market price"}</p>
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
