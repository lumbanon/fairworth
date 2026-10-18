import { securityLabel } from "@/lib/securityIdentity";

const stageLabels = { symbol_resolution: "Symbol resolution", classification: "Security classification", profile: "Company profile", statements: "Financial statements", normalization: "Normalized evidence", freshness: "Source freshness", valuation: "Valuation eligibility", ai_research: "AI evidence coverage" };
const statusLabels = { available: "Available", missing_evidence: "Missing evidence", provider_restricted: "Provider restricted", not_supported: "Not yet supported", financially_inapplicable: "Financially inapplicable", temporarily_unavailable: "Temporarily unavailable", identity_ambiguous: "Identity ambiguous" };

export default function ProviderCoverage({ company }) {
  const coverage = company.coverage;
  if (!coverage?.stages) {
    const warnings = (company.warnings ?? []).filter((warning) => warning.field === "coverage");
    return warnings.length ? <section className="research-section provider-coverage" aria-labelledby="company-coverage-heading"><h2 id="company-coverage-heading">Company analysis coverage</h2>{warnings.map((warning, index) => <p className="research-warning" role="status" key={index}>{warning.message}</p>)}</section> : null;
  }
  const identity = coverage.identity ?? company.identity ?? {};
  return <section className="research-section provider-coverage" aria-labelledby="company-coverage-heading">
    <div className="research-section-heading"><div><h2 id="company-coverage-heading">Company analysis coverage</h2><p>Finding a security does not guarantee that its financial evidence supports a valuation.</p></div></div>
    <p className="research-caption">{[identity.exchange, securityLabel(identity.instrument_type), identity.share_class && `Share class ${identity.share_class}`, identity.listing_status && `Listing: ${identity.listing_status.replaceAll("_", " ")}`].filter(Boolean).join(" · ")}</p>
    <dl className="provider-coverage-grid">{Object.entries(stageLabels).map(([key, label]) => {
      const stage = coverage.stages[key];
      return <div key={key}><dt>{label}</dt><dd><strong>{statusLabels[stage?.status] || "Not assessed"}</strong><p>{stage?.reason || "No assessment was supplied for this stage."}</p>{key === "valuation" && Number.isInteger(stage?.contributing_model_count) && <p>{stage.contributing_model_count} contributing model{stage.contributing_model_count === 1 ? "" : "s"}</p>}</dd></div>;
    })}</dl>
    {coverage.as_of && <p className="research-caption">Coverage assessed: {coverage.as_of}</p>}
    <details className="research-original-diagnostics"><summary>Identity and complete coverage diagnostics</summary><pre>{JSON.stringify(coverage, null, 2)}</pre></details>
  </section>;
}
