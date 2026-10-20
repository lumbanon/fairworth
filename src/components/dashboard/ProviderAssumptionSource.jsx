import { providerAssumptionEvidence, providerPeriodLabel } from "@/lib/providerValuation";

function sourceText(value) {
  if (value == null) return null;
  if (Array.isArray(value)) return value.map(sourceText).filter(Boolean).join(" · ");
  if (typeof value === "object") return value.description || value.provider || value.source || value.id || JSON.stringify(value);
  return String(value);
}

export default function ProviderAssumptionSource({ metadata = {}, overridden = false, id }) {
  const period = providerPeriodLabel(metadata.financial_period ?? metadata.observation_period);
  const method = metadata.derivation_formula || metadata.derivation_method;
  const category = metadata.source_category || metadata.source_type;
  const quality = metadata.quality;
  const warnings = [...(metadata.warnings ?? []), ...(quality?.warnings ?? [])]
    .map((warning) => typeof warning === "string" ? warning : warning.message).filter(Boolean);
  return (
    <div className="provider-assumption-source" id={id}>
      <p className="assumption-explanation"><strong>{overridden ? "User override" : providerAssumptionEvidence(metadata)}</strong>
        {category && ` · ${category.replaceAll("_", " ")}`}
        {metadata.source_provider && ` · ${sourceText(metadata.source_provider)}`}
      </p>
      {metadata.source_description && <p className="assumption-explanation">{metadata.source_description}</p>}
      <p className="research-caption">Observed: {sourceText(metadata.observation_date) || "No dated observation"}{period && ` · Financial period: ${period}`}</p>
      {method && <p className="research-caption"><strong>Method: </strong>{method}</p>}
      {metadata.input_status && <p className="research-caption">Input status: {metadata.input_status.replaceAll("_", " ")}</p>}
      {quality && <p className="research-caption">Source quality: {typeof quality === "string" ? quality : quality.label || quality.level || "See source warnings"}</p>}
      {[...new Set(warnings)].map((warning) => <p className="research-caption" key={warning}>{warning}</p>)}
      {metadata.source_identifiers?.length > 0 && <details className="provider-source-identifiers"><summary>Source identifiers</summary><p className="research-caption">{sourceText(metadata.source_identifiers)}</p></details>}
    </div>
  );
}
