import { diagnosticLabel, providerModelBlockers } from "@/lib/providerDiagnostics";

export default function ProviderModelBlockers({ eligibility, compact = false }) {
  const blockers = providerModelBlockers(eligibility);
  if (!blockers.length) return null;
  const list = <ul className="provider-blocker-list">{blockers.map((blocker, index) => <li key={`${blocker.code}-${index}`}>
    <strong>{diagnosticLabel(blocker.code)}</strong><p>{blocker.message}</p>
    {blocker.fields.length > 0 && <p className="research-caption">Affected inputs: {blocker.fields.map(diagnosticLabel).join(", ")}</p>}
  </li>)}</ul>;
  return compact ? <details className="provider-model-blockers"><summary>{blockers.length} blocking {blockers.length === 1 ? "issue" : "issues"}</summary>{list}</details>
    : <div className="provider-model-blockers"><h4>Why this model is blocked</h4>{list}</div>;
}
