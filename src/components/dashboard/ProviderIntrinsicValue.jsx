import { dollars, percent } from "@/lib/financialFormatting";
import { providerAssumptionEvidence, providerPeriodLabel } from "@/lib/providerValuation";
import { completenessValue, diagnosticMessages } from "@/lib/providerDiagnostics";
import { intrinsicEstimateLabel, intrinsicHorizonLabel, intrinsicAssumptionEntries, comparisonStatusLabel } from "@/lib/intrinsicPresentation";

export default function ProviderIntrinsicValue({ valuation }) {
  const intrinsic = valuation.intrinsic;
  const comparison = valuation.marketComparison;
  if (!intrinsic) return null;
  const available = intrinsic.status === "available" && Number.isFinite(intrinsic.value);
  const modelNames = (intrinsic.model_ids ?? []).map((id) => valuation.results.find((model) => model.id === id)?.name || id);
  const entries = intrinsicAssumptionEntries(intrinsic.assumptions);
  return <div className="provider-intrinsic-evidence" data-testid="intrinsic-evidence">
    <h3>{intrinsicEstimateLabel(intrinsic)}</h3>
    {available && <p><strong data-testid="intrinsic-estimate-value">{dollars(intrinsic.value, intrinsic.currency)} per share</strong>{modelNames.length > 0 && ` · ${modelNames.join(", ")}`}</p>}
    <p className="research-caption">Intrinsic calculation, financial evidence date and current publication are assessed separately. A supported estimate can exist without a market-price comparison.</p>
    {intrinsic.classification === "user_defined" && <p className="research-warning" data-testid="user-assisted-valuation-warning">This scenario uses explicit user assumptions. It is excluded from automatic default valuation coverage and does not establish a current published value.</p>}
    <dl className="provider-record-metadata">
      <div><dt>Financial evidence as of</dt><dd>{providerPeriodLabel(intrinsic.financial_observation_date) || "Unavailable"}</dd></div>
      {intrinsic.source_retrieved_at && <div><dt>Original financial source retrieved</dt><dd>{intrinsic.source_retrieved_at}</dd></div>}
      {intrinsic.evidence_context?.evidence_as_of && <div><dt>Archived identity evidence time</dt><dd>{intrinsic.evidence_context.evidence_as_of}</dd></div>}
      <div><dt>Calculation time</dt><dd>{intrinsic.calculated_at || valuation.calculatedAt || "Unavailable"}</dd></div>
      <div><dt>Forecast horizon</dt><dd>{intrinsicHorizonLabel(intrinsic.forecast_horizon)}</dd></div>
      <div><dt>Market comparison</dt><dd data-testid="intrinsic-comparison-status">{comparisonStatusLabel(comparison)}</dd></div>
      {comparison?.status === "available" && <>
        <div><dt>Compatible observed price</dt><dd>{dollars(comparison.price, comparison.currency)} · {comparison.provider || "Source unavailable"}</dd></div>
        <div><dt>Quote observed</dt><dd>{comparison.observed_at || "Unavailable"}</dd></div>
        <div><dt>Premium / discount</dt><dd>{percent(comparison.upside, true)}</dd></div>
      </>}
    </dl>
    {comparison?.reason && <p className="research-caption">{comparison.reason}</p>}
    {diagnosticMessages(intrinsic.limitations).map((limitation, index) => <p className="research-caption" key={index}>{limitation}</p>)}
    {(entries.length > 0 || intrinsic.source_identifiers?.length > 0) && <details className="research-original-diagnostics"><summary>Intrinsic inputs, assumptions and source references</summary>
      {entries.length > 0 && <dl className="provider-record-metadata">{entries.map(([key, metadata]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{completenessValue(metadata)} · {providerAssumptionEvidence(metadata)}{metadata.source_description && <p className="research-caption">{metadata.source_description}</p>}</dd></div>)}</dl>}
      {(intrinsic.source_identifiers ?? []).map((source, index) => <p className="research-caption" key={index}>{typeof source === "string" ? source : source.source_id || source.accession || "See original evidence record"}</p>)}
      <pre>{JSON.stringify(intrinsic, null, 2)}</pre>
    </details>}
  </div>;
}
