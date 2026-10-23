import { dollars, percent, direction } from "@/lib/financialFormatting";
import { providerClassificationLabel, providerPublicationLabel } from "@/lib/providerValuation";
import { formatObservationDate } from "@/lib/researchPresentation";
import ProviderIntrinsicValue from "./ProviderIntrinsicValue";

export default function ValuationSummary({ company, valuation }) {
  const { summary, scenarios, activeScenario } = valuation;
  const enabledCount = valuation.results.filter(
    (result) => result.applicable && valuation.enabled[result.id],
  ).length;
  const range = [
    scenarios.bear.summary.fairValue,
    scenarios.bull.summary.fairValue,
  ];
  const finiteRange = range.every(Number.isFinite);
  const quoteDate = formatObservationDate(valuation.market?.price_timestamp);
  return (
    <section className="research-summary" aria-labelledby="summary-title">
      <div className="research-section-heading">
        <h2 id="summary-title">Valuation overview</h2>
        <span className="research-caption">
          {activeScenario[0].toUpperCase() + activeScenario.slice(1)} scenario ·
          {valuation.providerMode ? "calculated by Python" : "calculated locally"}
        </span>
      </div>
      <div className="research-metrics">
        <div>
          <span>Market price</span>
          <strong>
            {dollars(
              valuation.providerMode ? valuation.comparisonPrice : company.price,
              company.dataMode === "provider"
                ? (valuation.market?.currency ?? null)
                : "USD",
            )}
          </strong>
          <small>
            {company.dataMode === "provider"
              ? valuation.comparisonPrice == null
                ? "Market provider price unavailable"
                : valuation.market?.label || "Provider price · timestamp above"
              : "Fictional reference price"}
          </small>
          {valuation.providerMode && valuation.market?.source_type !== "user" && valuation.comparisonPrice != null && <small data-testid="valuation-quote-observation">Quote observed: {quoteDate || "Date unavailable"}{valuation.market?.status && ` · ${valuation.market.status.replaceAll("_", " ")}`}</small>}
        </div>
        <div>
          <span>Weighted fair value</span>
          <strong data-testid="weighted-fair-value" className="research-accent">
            {dollars(summary.fairValue, valuation.providerMode ? company.currency : "USD")}
          </strong>
          <small>
            {enabledCount} enabled · {summary.count} contributing
          </small>
          {valuation.providerMode && summary.classification && <small data-testid="weighted-classification">{providerClassificationLabel(summary.classification) || "Classification unavailable"}</small>}
          {valuation.providerMode && <small data-testid="valuation-publication-type">{providerPublicationLabel(valuation.publication)}</small>}
          {valuation.providerMode && valuation.diagnostics && <small>Confidence: {valuation.confidence?.level || "unavailable"} · {valuation.diagnostics.coverage?.method_family_count ?? "Unavailable"} method {valuation.diagnostics.coverage?.method_family_count === 1 ? "family" : "families"}</small>}
        </div>
        <div>
          <span>Potential upside / downside</span>
          <strong
            data-testid="summary-upside"
            className={direction(summary.upside)}
          >
            {percent(summary.upside, true)}
          </strong>
          <small>(Fair value / price − 1) × 100</small>
        </div>
        <div>
          <span>Margin of safety</span>
          <strong className={direction(summary.marginOfSafety)}>
            {percent(summary.marginOfSafety, true)}
          </strong>
          <small>(Fair value − price) / fair value × 100</small>
        </div>
      </div>
      {valuation.providerMode && <ProviderIntrinsicValue valuation={valuation} />}
      {valuation.providerMode && valuation.publication?.result_type === "historical_illustration" && <p className="research-warning" data-testid="historical-valuation-warning">This illustrative calculation does not satisfy current publication requirements. Review its dated evidence and unresolved checks below. Calculating it today does not refresh its sources or establish a previously published valuation.</p>}
      {valuation.providerMode && summary.count === 1 && Number.isFinite(summary.fairValue) && <p className="research-warning provider-single-model-warning" data-testid="single-model-coverage-warning"><strong>Single-model estimate.</strong> Coverage is limited to one contributing model; this is not a robust multi-model consensus. Review its assumptions and the data-quality limitations below.</p>}
      {valuation.providerMode && summary.composition?.length > 0 && <div className="provider-valuation-composition" aria-label="Weighted estimate composition">
        <p className="research-caption">Weighted estimate composition: {summary.composition.map((part) => `${providerClassificationLabel(part.classification) || "Unclassified"}: ${Number.isFinite(part.weight) ? `${(part.weight * 100).toFixed(1)}%` : "Unavailable"} (${part.model_ids?.join(", ") || "No contributing models"})`).join(" · ")}</p>
        <p className="research-caption">Classification describes the assumptions supporting the estimate; it does not verify the intrinsic value.</p>
      </div>}
      {valuation.providerMode && summary.sourceWarnings?.map((warning) => <p className="research-caption" key={warning}>{warning}</p>)}
      <div className="research-summary-bottom">
        <span>
          Bear / bull fair values{" "}
          <strong>
            {finiteRange
              ? `${dollars(range[0], valuation.providerMode ? company.currency : "USD")} / ${dollars(range[1], valuation.providerMode ? company.currency : "USD")}`
              : "Unavailable"}
          </strong>
        </span>
        <span>
          Model estimates are uncertain; a weighted average does not guarantee
          accuracy.
        </span>
      </div>
      {summary.warnings.length > 0 && (
        <div role="alert" className="research-warning">
          {summary.warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      )}
    </section>
  );
}
