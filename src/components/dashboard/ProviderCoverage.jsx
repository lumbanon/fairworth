import { issuerCategoryLabel, issuerLinkageSummary, listingSourceUrl, listingVerificationSummary, securityFormLabel } from "@/lib/securityIdentity";

const stageLabels = { symbol_resolution: "Symbol resolution", security_identity: "Security identity", active_listing: "Active US listing", classification: "Security classification", share_basis: "Compatible share basis", profile: "Company profile", statements: "Financial statements", normalization: "Normalized evidence", valuation: "Valuation eligibility", ai_research: "AI evidence coverage" };
const statusLabels = { available: "Available", missing_evidence: "Missing evidence", provider_restricted: "Provider restricted", not_supported: "Not yet supported", financially_inapplicable: "Financially inapplicable", temporarily_unavailable: "Temporarily unavailable", identity_ambiguous: "Identity ambiguous", verification_expired: "Verification expired" };

export default function ProviderCoverage({ company }) {
  const coverage = company.coverage;
  const imported = company.financialImport;
  if (!coverage?.stages) {
    const warnings = (company.warnings ?? []).filter((warning) => warning.field === "coverage");
    return warnings.length ? <section className="research-section provider-coverage" aria-labelledby="company-coverage-heading"><h2 id="company-coverage-heading">Company analysis coverage</h2>{warnings.map((warning, index) => <p className="research-warning" role="status" key={index}>{warning.message}</p>)}</section> : null;
  }
  const identity = coverage.identity ?? company.identity ?? {};
  const verification = listingVerificationSummary(identity);
  const issuerLinkage = issuerLinkageSummary(identity);
  const sourceUrl = listingSourceUrl(verification.source_url);
  const issuerSourceUrl = listingSourceUrl(issuerLinkage.source_url);
  const freshness = coverage.stages.freshness;
  return <section className="research-section provider-coverage" aria-labelledby="company-coverage-heading">
    <div className="research-section-heading"><div><h2 id="company-coverage-heading">Company analysis coverage</h2><p>Finding a security does not guarantee that its financial evidence supports a valuation.</p></div></div>
    {imported && <details className="research-original-diagnostics" data-testid="financial-import-evidence"><summary>Imported SEC financial evidence</summary><p>Financial statements belong to the reporting issuer; security share-class compatibility is assessed separately.</p><dl className="provider-record-metadata"><div><dt>Import batch</dt><dd>{imported.import_batch_id || "Unavailable"}</dd></div><div><dt>Financial owner</dt><dd>{imported.financial_owner_ticker || "Unavailable"} · CIK {imported.cik || "Unavailable"}</dd></div><div><dt>Original source retrieved</dt><dd>{imported.original_retrieved_at || "Unavailable"}</dd></div><div><dt>Imported</dt><dd>{imported.imported_at || "Unavailable"}</dd></div><div><dt>Original source hash</dt><dd>{imported.source_sha256 || "Unavailable"}</dd></div></dl><p className="research-caption">Import time does not refresh the original financial observation or its currentness.</p></details>}
    <p className="research-caption">{[identity.exchange, `Security form: ${securityFormLabel(identity)}`, identity.share_class && `Share class ${identity.share_class}`, `Issuer category: ${issuerCategoryLabel(identity)}`].filter(Boolean).join(" · ")}</p>
    <p className="provider-listing-summary"><strong>{verification.label}</strong>{verification.observed_on && <span>Listing observed: {verification.observed_on}</span>}</p>
    {identity.proof_expiry?.issuer_linkage && <p className="provider-listing-summary" data-testid="issuer-linkage-verification"><strong>{issuerLinkage.label}</strong>{issuerLinkage.observed_on && <span>Issuer linkage observed: {issuerLinkage.observed_on}</span>}</p>}
    {verification.conflicting && <p className="research-warning" role="status">Source records disagree. Listing verification and affected valuation eligibility remain unresolved; inspect the source observations below.</p>}
    {verification.expired && <p className="research-warning" role="status">{verification.reason || "The listing source proof has expired under its verification policy."} Source: {verification.source || "Unavailable"}. Observed: {verification.observed_on || "Unavailable"}. Expires: {verification.expires_at || "Unavailable"}. Financial filings and quotes do not renew this proof.</p>}
    {verification.stale && !verification.expired && <p className="research-warning" role="status">The listing observation is dated. A recent retrieval does not establish a current active listing or fresh financial statements.</p>}
    {issuerLinkage.expired && <p className="research-warning" role="status">{issuerLinkage.reason || "The SEC issuer-to-security linkage proof has expired under its verification policy."} Source: {issuerLinkage.source || "Unavailable"}. Observed: {issuerLinkage.observed_on || "Unavailable"}. Expires: {issuerLinkage.expires_at || "Unavailable"}. A listing refresh or quote does not renew issuer ownership evidence.</p>}
    <dl className="provider-coverage-grid">{Object.entries(stageLabels).map(([key, label]) => {
      const stage = coverage.stages[key];
      return <div key={key}><dt>{label}</dt><dd><strong>{statusLabels[stage?.status] || "Not assessed"}</strong><p>{stage?.reason || "No assessment was supplied for this stage."}</p>{key === "valuation" && Number.isInteger(stage?.contributing_model_count) && <p>{stage.contributing_model_count} contributing model{stage.contributing_model_count === 1 ? "" : "s"}</p>}</dd></div>;
    })}</dl>
    {freshness && <p className="provider-source-freshness"><strong>Source freshness: {statusLabels[freshness.status] || "Not assessed"}.</strong> {freshness.reason}</p>}
    {identity.listing_verification && <details className="provider-listing-provenance">
      <summary>Listing verification sources and dates</summary>
      <dl className="provider-listing-dates">
        <div><dt>Verification source</dt><dd>{verification.source || "Unavailable"}{sourceUrl && <> · <a href={sourceUrl} target="_blank" rel="noreferrer">View listing source</a></>}</dd></div>
        <div><dt>Listing observed</dt><dd>{verification.observed_on || "Unavailable"}</dd></div>
        <div><dt>Status effective</dt><dd>{verification.effective_on || verification.status_effective_on || "Not supplied by source"}</dd></div>
        <div><dt>Source published{verification.source_timezone ? ` (${verification.source_timezone})` : " (timezone unspecified)"}</dt><dd>{verification.published_at || "Not supplied by source"}</dd></div>
        <div><dt>Retrieved by Fairworth</dt><dd>{verification.retrieved_at || "Unavailable"}</dd></div>
        <div><dt>Source record hash</dt><dd>{verification.record_hash || "Unavailable"}</dd></div>
        {verification.expires_at && <div><dt>Listing proof expires</dt><dd>{verification.expires_at}</dd></div>}
      </dl>
      <p className="research-caption">Listing dates describe the security reference. Statement periods and quote observation dates are assessed independently.</p>
      {(verification.warnings ?? []).length > 0 && <ul>{verification.warnings.map((warning, index) => <li key={index}>{typeof warning === "string" ? warning : warning.message ?? JSON.stringify(warning)}</li>)}</ul>}
    </details>}
    {identity.proof_expiry?.issuer_linkage && <details className="provider-listing-provenance">
      <summary>Issuer linkage sources and dates</summary>
      <dl className="provider-listing-dates">
        <div><dt>Issuer linkage source</dt><dd>{issuerLinkage.source || "Unavailable"}{issuerSourceUrl && <> · <a href={issuerSourceUrl} target="_blank" rel="noreferrer">View issuer linkage source</a></>}</dd></div>
        <div><dt>Issuer linkage observed</dt><dd>{issuerLinkage.observed_on || "Unavailable"}</dd></div>
        <div><dt>Issuer linkage published</dt><dd>{issuerLinkage.published_at || "Not supplied by source"}</dd></div>
        <div><dt>Issuer linkage retrieved</dt><dd>{issuerLinkage.retrieved_at || "Unavailable"}</dd></div>
        <div><dt>Issuer linkage proof expires</dt><dd>{issuerLinkage.expires_at || "Unavailable"}</dd></div>
      </dl>
      <p className="research-caption">Issuer ownership and exchange listing dates are assessed separately. Neither establishes current financial or market-price evidence.</p>
    </details>}
    {coverage.as_of && <p className="research-caption">Coverage assessed: {coverage.as_of}</p>}
    <details className="research-original-diagnostics"><summary>Identity and complete coverage diagnostics</summary><pre>{JSON.stringify(coverage, null, 2)}</pre></details>
  </section>;
}
