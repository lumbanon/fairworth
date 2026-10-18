import { totalDollars, dollars } from "@/lib/financialFormatting";
import { companyDescriptionPreview } from "@/lib/sourceNotices";
import { securityLabel } from "@/lib/securityIdentity";

export default function CompanyHeader({ company }) {
  const provider = company.dataMode === "provider";
  const description = companyDescriptionPreview(company.description || "Company description unavailable from the configured provider.");
  return (
    <section
      id="overview"
      className="research-company"
      aria-labelledby="company-title"
    >
      <div className="research-breadcrumb">
        Equity research <span>/</span> {company.ticker}
      </div>
      <div className="research-company-row">
        <div>
          <h1 id="company-title">
            {company.companyName} <span>({company.ticker})</span>
          </h1>
          <p className="company-classification">
            {[company.exchange, company.instrumentType && securityLabel(company.instrumentType), company.shareClass && `Share class ${company.shareClass}`, company.sector, company.industry]
              .filter(Boolean)
              .join(" · ") || "Company classification unavailable"}
          </p>
        </div>
        <div className="research-price">
          <span>
            {provider ? "Latest provider price" : "Illustrative market price"}
          </span>
          <strong>
            {dollars(
              company.price,
              provider ? (company.market?.currency ?? null) : "USD",
            )}
          </strong>
        </div>
      </div>
      <p className="research-company-description">
        {description.preview}
      </p>
      {description.expandable && <details className="research-company-full-description">
        <summary>Read full company description</summary>
        <p>{description.full}</p>
      </details>}
      <div className="company-metadata">
        <span>
          Market cap{" "}
          <strong>
            {totalDollars(
              provider
                ? company.marketCap
                : company.price * company.latest.shares,
              provider ? (company.market?.currency ?? null) : "USD",
            )}
          </strong>
        </span>
        <span>{company.updatedLabel}</span>
      </div>
      {provider && (
        <div className="company-metadata">
          <span>
            Price timestamp:{" "}
            <strong>{company.market?.price_timestamp || "Unavailable"}</strong>
          </span>
          <span>
            Market source:{" "}
            {company.market?.provider ||
              company.dataStatus?.provider_status?.market?.provider ||
              "Not configured"}
          </span>
          <span>CIK: {company.cik || "Unavailable"}</span>
          {company.listingStatus && <span>Listing: {company.listingStatus.replaceAll("_", " ")}</span>}
          {company.identityStatus && <span>Identity: {company.identityStatus.replaceAll("_", " ")}</span>}
        </div>
      )}
      {provider && ["adr", "ads"].includes(company.instrumentType) && <p className="research-warning">This listed depositary security is distinct from its underlying issuer. Reporting currency, ADR ratio and per-security share basis must be compatible before a valuation can contribute. No currency or share-ratio conversion is assumed.</p>}
      {provider && Object.keys(company.adrMetadata ?? {}).length > 0 && <details className="research-original-diagnostics"><summary>Depositary security basis and provenance</summary><pre>{JSON.stringify(company.adrMetadata, null, 2)}</pre></details>}
      <p className="research-demo-notice">
        {provider
          ? "Provider-backed financial data — reported periods and price timestamps determine freshness."
          : "Demo financial data — not live market information."}
      </p>
    </section>
  );
}
