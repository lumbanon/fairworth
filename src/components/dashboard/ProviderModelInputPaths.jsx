import { diagnosticLabel } from "@/lib/providerDiagnostics";

export default function ProviderModelInputPaths({ paths }) {
  if (!Array.isArray(paths) || !paths.length) return null;
  if (paths.every((path) => typeof path === "string")) return <p className="research-caption"><strong>Input records: </strong>{paths.join(", ")}</p>;
  const records = paths.filter((path) => path && typeof path === "object" && Array.isArray(path.required_inputs));
  if (!records.length) return null;
  return <details className="provider-input-paths"><summary>Financial input paths ({records.length})</summary>
    <p className="research-caption">A model needs one complete financial path plus its compatibility and applicability checks. An available field alone does not establish eligibility.</p>
    <ul>{records.map((path, index) => <li key={index}><p><strong>Path {index + 1}: </strong>{path.required_inputs.map(diagnosticLabel).join(", ")}</p>
      <p className="research-caption">Available: {Array.isArray(path.available_inputs) ? path.available_inputs.length ? path.available_inputs.map(diagnosticLabel).join(", ") : "None" : "Unavailable"}. Missing: {Array.isArray(path.missing_inputs) ? path.missing_inputs.length ? path.missing_inputs.map(diagnosticLabel).join(", ") : "None" : "Unavailable"}.</p>
    </li>)}</ul>
  </details>;
}
