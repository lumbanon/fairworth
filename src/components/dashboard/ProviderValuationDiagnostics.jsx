import { dollars, percent } from "@/lib/financialFormatting";
import { diagnosticLabel, diagnosticMessages } from "@/lib/providerDiagnostics";
import ProviderModelInputPaths from "./ProviderModelInputPaths";

export default function ProviderValuationDiagnostics({ valuation, currency }) {
  const diagnostics = valuation.diagnostics;
  if (!diagnostics) return null;
  const coverage = diagnostics.coverage ?? {};
  const aggregation = diagnostics.aggregation ?? {};
  const dataQuality = diagnostics.data_quality ?? {};
  const confidence = valuation.confidence;
  const modelName = (id) => valuation.results.find((model) => model.id === id)?.name || id;
  const range = aggregation.estimate_range;
  const finiteRange = Number.isFinite(range?.minimum) && Number.isFinite(range?.maximum);
  return (
    <section className="research-section provider-valuation-diagnostics" aria-labelledby="valuation-quality-heading">
      <div className="research-section-heading"><div><h2 id="valuation-quality-heading">Valuation coverage & confidence</h2><p>Data quality, model availability and confidence describe different limitations of this estimate.</p></div></div>
      <div className="provider-quality-grid">
        <div><h3>Data quality</h3><strong data-testid="valuation-data-quality">{diagnosticLabel(dataQuality.level)}</strong><p>Reliability and completeness of the underlying inputs.</p></div>
        <div><h3>Model coverage</h3><strong data-testid="valuation-model-coverage">{coverage.contributing_count ?? "Unavailable"} contributing · {coverage.method_family_count ?? "Unavailable"} method {coverage.method_family_count === 1 ? "family" : "families"}</strong><p>{coverage.eligible_count ?? "Unavailable"} eligible of {coverage.applicable_count ?? "Unavailable"} applicable models. Families group related methods; they do not prove independence.</p></div>
        <div><h3>Valuation confidence</h3><strong data-testid="valuation-confidence">{diagnosticLabel(confidence?.label || confidence?.level)}</strong><p>A heuristic judgment about the estimate, not a statistical probability or assurance of accuracy.</p></div>
      </div>
      <div className="provider-aggregation-summary">
        <p><strong>Contributing models: </strong>{Array.isArray(coverage.contributing_models) ? coverage.contributing_models.length ? coverage.contributing_models.map((item) => modelName(typeof item === "string" ? item : item.model_id || item.id)).join(", ") : "None" : "Unavailable"}.</p>
        <p><strong>Model estimate range: </strong>{finiteRange ? `${dollars(range.minimum, currency)} to ${dollars(range.maximum, currency)}` : "Unavailable"}. This describes model outputs, not a calibrated confidence interval.</p>
        <p><strong>Model dispersion: </strong>{diagnosticLabel(aggregation.dispersion?.status)}{Number.isFinite(aggregation.dispersion?.relative_spread) ? ` · ${percent(aggregation.dispersion.relative_spread * 100)} relative spread` : ""}. <strong>Weights: </strong>{diagnosticLabel(aggregation.weight_source)}.</p>
        {diagnosticMessages(aggregation.warnings).map((warning, index) => <p className="research-caption" key={index}>{warning}</p>)}
      </div>
      <details className="provider-diagnostic-details"><summary>Why this estimate has its confidence classification</summary>
        {diagnosticMessages(dataQuality.reasons ?? dataQuality.factors).map((reason, index) => <p key={index}>{reason}</p>)}
        {(confidence?.factors ?? []).map((factor, index) => <p key={index}><strong>{factor.name}: </strong>{factor.explanation} ({diagnosticLabel(factor.status)})</p>)}
        {confidence?.disclaimer && <p className="research-caption">{confidence.disclaimer}</p>}
        {(coverage.families ?? []).map((family) => <p key={family.id}><strong>{family.label || diagnosticLabel(family.id)}: </strong>{family.model_ids?.map(modelName).join(", ") || "No contributing models"}</p>)}
        {(aggregation.shared_assumptions ?? []).length > 0 && <div><h3>Shared assumptions</h3><p className="research-caption">Related inputs may make apparently different methods depend on the same evidence.</p>{aggregation.shared_assumptions.map((shared) => <p key={shared.key}><strong>{diagnosticLabel(shared.key)}: </strong>{shared.model_ids?.map(modelName).join(", ")}</p>)}</div>}
        {aggregation.method && <p className="research-caption">Aggregation method: {diagnosticLabel(aggregation.method)}</p>}
        {(aggregation.methodology_version || diagnostics.methodology_version) && <p className="research-caption">Diagnostic methodology: {aggregation.methodology_version || diagnostics.methodology_version}</p>}
      </details>
      {(coverage.excluded_models ?? []).length > 0 && <details className="provider-diagnostic-details"><summary>Excluded models and required inputs ({coverage.excluded_models.length})</summary>
        <ul className="provider-excluded-models">{coverage.excluded_models.map((model) => <li key={model.model_id}><strong>{modelName(model.model_id)}</strong><p>{model.reason || diagnosticLabel(model.status)}</p>{model.missing_inputs?.length > 0 && <p className="research-caption">Required inputs: {model.missing_inputs.map(diagnosticLabel).join(", ")}</p>}<ProviderModelInputPaths paths={model.input_paths} /></li>)}</ul>
      </details>}
    </section>
  );
}
