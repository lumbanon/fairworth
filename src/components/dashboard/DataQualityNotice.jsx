function sourceLink(source) {
  const value =
    typeof source === "string" ? source : (source.url ?? source.filing_url);
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

export default function DataQualityNotice({ company }) {
  const status = company.dataStatus;
  const references = [
    ...new Set(company.sourceReferences.map(sourceLink).filter(Boolean)),
  ];
  return (
    <section
      className="research-quality-notice"
      aria-labelledby="data-quality-title"
    >
      <div>
        <h2 id="data-quality-title">Data quality & sources</h2>
        <p>
          SEC EDGAR reported financial statements · provider availability and
          reporting dates are shown explicitly.
        </p>
      </div>
      <div className="research-source-summary">
        <span>
          Financial retrieval:{" "}
          <strong>
            {company.financialRetrievedAt ||
              status?.last_financial_update ||
              "Unavailable"}
          </strong>
        </span>
        <span>
          Financial status:{" "}
          <strong>
            {company.financialStatus ||
              status?.provider_status?.financial?.status ||
              "See source warnings"}
          </strong>
        </span>
        <span>
          Company status:{" "}
          <strong>{company.profileStatus || "Unavailable"}</strong>
        </span>
        <span>
          Market status:{" "}
          <strong>
            {company.market?.status ||
              status?.provider_status?.market?.status ||
              "Unavailable"}
          </strong>
        </span>
      </div>
      {status?.missing_fields?.length > 0 && (
        <p className="research-caption">
          Missing reported fields: {status.missing_fields.join(", ")}.
        </p>
      )}
      <details>
        <summary>
          {company.warnings.length} source and compatibility notices
        </summary>
        <ul>
          {company.warnings.map((warning, index) => (
            <li key={`${warning.code}-${index}`}>
              {warning.field && <strong>{warning.field}: </strong>}
              {warning.message}
            </li>
          ))}
        </ul>
      </details>
      {references.length > 0 && (
        <div className="research-source-links">
          {references.map((url, index) => (
            <a href={url} key={url} target="_blank" rel="noreferrer">
              Source {index + 1}
            </a>
          ))}
        </div>
      )}
    </section>
  );
}
