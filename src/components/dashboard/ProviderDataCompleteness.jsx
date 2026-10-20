import { completenessGroups, completenessFieldLabel, completenessValue, diagnosticLabel, diagnosticMessages, providerSourceLinks, providerCompatibilityLabel, providerReportingPeriods } from "@/lib/providerDiagnostics";
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

const compatibilityLabels = { share_basis: "Selected-security share basis", currency: "Reporting / trading currency", reporting_regime: "Accounting / reporting regime", market_price: "Market-price freshness" };

function FinancialBasis({ compatibility }) {
  if (!compatibility || typeof compatibility !== "object") return null;
  return <div className="provider-financial-basis">
    <h3>Financial basis and market comparison</h3>
    <dl className="provider-basis-grid">{Object.entries(compatibilityLabels).map(([key, label]) => {
      const assessment = compatibility[key];
      return <div key={key}><dt>{label}</dt><dd><strong>{providerCompatibilityLabel(assessment?.status)}</strong><p>{assessment?.reason || "No assessment was supplied for this basis."}</p>{assessment?.observation_date && <p className="research-caption">Observed: {assessment.observation_date}</p>}</dd></div>;
    })}</dl>
    <p className="research-caption">These assessments are independent. A fresh quote cannot verify a share class, currency conversion or financial reporting basis.</p>
  </div>;
}

function ReportingPeriods({ completeness }) {
  const periods = providerReportingPeriods(completeness);
  if (!periods.length) return null;
  return <div className="provider-period-coverage">
    <h3>Financial evidence by reporting period</h3>
    <p className="research-caption">Availability describes normalized evidence for each period. It does not establish a complete model input path or permission to combine periods.</p>
    <div className="research-table-scroll" role="region" aria-label="Financial evidence by reporting period" tabIndex={0}>
      <table className="research-table provider-period-table"><thead><tr><th scope="col">Reporting period</th><th scope="col">Available metrics</th><th scope="col">Missing metrics</th><th scope="col">Evidence references</th></tr></thead><tbody>
        {periods.map((period, index) => <tr key={`${period.end_date}-${period.fiscal_period}-${index}`}>
          <th scope="row">{[period.fiscal_period, period.fiscal_year].filter((value) => value != null).join(" ") || "Fiscal period unavailable"}<span className="normalized-weight">{providerPeriodLabel({ start_date: period.start_date, end_date: period.end_date }) || "Period dates unavailable"}</span></th>
          <td>{period.available_metrics ? <><span>{period.available_metrics.length} available</span>{period.available_metrics.length > 0 && <details><summary>View available metrics</summary><p>{period.available_metrics.map((metric) => completenessFieldLabel(metric)).join(", ")}</p></details>}</> : "Not assessed"}</td>
          <td>{period.missing_metrics ? <><span>{period.missing_metrics.length} missing</span>{period.missing_metrics.length > 0 && <details><summary>View missing metrics</summary><p>{period.missing_metrics.map((metric) => completenessFieldLabel(metric)).join(", ")}</p></details>}</> : "Not assessed"}</td>
          <td>{period.source_identifiers.length > 0 ? <details><summary>{period.source_identifiers.length} source {period.source_identifiers.length === 1 ? "reference" : "references"}</summary><ul>{period.source_identifiers.map((source, sourceIndex) => <li key={sourceIndex}>{source}</li>)}</ul></details> : "No source identifiers supplied"}{period.warnings.map((warning, warningIndex) => <p className="research-caption" key={warningIndex}>{warning}</p>)}</td>
        </tr>)}
      </tbody></table>
    </div>
  </div>;
}

export default function ProviderDataCompleteness({ valuation }) {
  const completeness = valuation.dataCompleteness;
  if (!completeness) return null;
  return (
    <section className="research-section provider-completeness" aria-labelledby="data-completeness-heading">
      <div className="research-section-heading"><div><h2 id="data-completeness-heading">Data completeness</h2>
        <p>Reported inputs, derived metrics and modeling assumptions keep separate sources. Expand a group to inspect its exact basis.</p></div></div>
      <p className="research-caption">Financial period: {providerPeriodLabel(completeness.reporting_period) || "Unavailable"} · Financial snapshot retrieved: {completeness.as_of || "Unavailable"}</p>
      <FinancialBasis compatibility={completeness.compatibility} />
      <ReportingPeriods completeness={completeness} />
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
