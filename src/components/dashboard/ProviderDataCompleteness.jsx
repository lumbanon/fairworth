import { completenessGroups, completenessFieldLabel, completenessValue, diagnosticLabel, diagnosticMessages, providerSourceLinks } from "@/lib/providerDiagnostics";
import { providerPeriodLabel } from "@/lib/providerValuation";

function SourceField({ fieldKey, field = {} }) {
  const links = providerSourceLinks(field);
  const warnings = diagnosticMessages(field.warnings);
  return (
    <details className="provider-input-record">
      <summary><span>{completenessFieldLabel(fieldKey, field)}</span><strong>{completenessValue(field)}</strong></summary>
      <dl className="provider-record-metadata">
        <div><dt>Source</dt><dd>{field.provider || "Provider unavailable"} · {diagnosticLabel(field.source_type)}</dd></div>
        <div><dt>Exact stored value</dt><dd><code>{field.value == null ? "Unavailable" : JSON.stringify(field.value)}</code>{field.value != null && field.unit ? ` ${field.unit}` : ""}</dd></div>
        {field.reported_value != null && <div><dt>Original reported value</dt><dd><code>{JSON.stringify(field.reported_value)}</code>{field.unit ? ` ${field.unit}` : ""}</dd></div>}
        <div><dt>Financial period</dt><dd>{providerPeriodLabel(field.period) || "Not supplied"}</dd></div>
        <div><dt>Observed</dt><dd>{field.observation_date || "Observation date unavailable"}</dd></div>
        <div><dt>Retrieved</dt><dd>{field.retrieved_at || "Retrieval date unavailable"}</dd></div>
        {field.derivation && <div><dt>Derivation</dt><dd>{typeof field.derivation === "string" ? field.derivation : JSON.stringify(field.derivation)}</dd></div>}
        {field.source_identifiers?.length > 0 && <div><dt>Source identifiers</dt><dd>{field.source_identifiers.join(" · ")}</dd></div>}
      </dl>
      {field.source_description && <p className="research-caption">{field.source_description}</p>}
      {warnings.map((warning, index) => <p className="research-caption" key={index}>{warning}</p>)}
      {links.length > 0 && <div className="research-source-links">{links.map((url, index) => <a key={url} href={url} target="_blank" rel="noreferrer">Original source {index + 1}</a>)}</div>}
      <details className="research-original-diagnostics"><summary>Complete input and provenance record</summary><pre>{JSON.stringify(field, null, 2)}</pre></details>
    </details>
  );
}

export default function ProviderDataCompleteness({ valuation }) {
  const completeness = valuation.dataCompleteness;
  if (!completeness) return null;
  return (
    <section className="research-section provider-completeness" aria-labelledby="data-completeness-heading">
      <div className="research-section-heading"><div><h2 id="data-completeness-heading">Data completeness</h2>
        <p>Reported inputs, derived metrics and modeling assumptions keep separate sources. Expand a group to inspect its exact basis.</p></div></div>
      <p className="research-caption">Financial period: {providerPeriodLabel(completeness.reporting_period) || "Unavailable"} · Financial snapshot retrieved: {completeness.as_of || "Unavailable"}</p>
      <div className="provider-completeness-grid">
        {completenessGroups.map(([key, label]) => {
          const fields = completeness.groups?.[key];
          return <details className="provider-completeness-group" key={key}>
            <summary><span>{label}</span><strong>{Array.isArray(fields) ? fields.length : "Unavailable"}</strong></summary>
            {Array.isArray(fields) && fields.length > 0
              ? fields.map((fieldKey) => <SourceField key={fieldKey} fieldKey={fieldKey} field={completeness.fields?.[fieldKey]} />)
              : <p className="research-caption">{Array.isArray(fields) ? "No inputs in this group." : "This group was not supplied by the valuation service."}</p>}
          </details>;
        })}
      </div>
      <p className="research-caption">Groups can overlap: a derived or user-supplied input may also be available. Availability alone does not establish suitability for a valuation model.</p>
      {completeness.methodology_version && <p className="research-caption">Completeness methodology: {completeness.methodology_version}</p>}
      {diagnosticMessages(completeness.limitations).map((limitation, index) => <p className="research-caption" key={index}>{limitation}</p>)}
    </section>
  );
}
