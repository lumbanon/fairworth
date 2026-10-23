import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { dollars } from "@/lib/financialFormatting";
import { providerPeriodLabel, providerPublicationLabel } from "@/lib/providerValuation";
import { isHistoricalNotice, noticeMessage } from "@/lib/sourceNotices";
import { diagnosticMessages } from "@/lib/providerDiagnostics";
import SourceNoticeGroups from "./SourceNoticeGroups";
import { providerQuoteCurrency } from "@/lib/marketDataPresentation";

export default function ProviderValuationStatus({ company, valuation }) {
  const confidence = valuation.scenarios[valuation.activeScenario].confidence ?? valuation.confidence;
  const notices = valuation.sourceNotices ?? valuation.warnings;
  const historicalNotices = notices.filter(isHistoricalNotice);
  const currentNotices = notices.filter((notice) => !isHistoricalNotice(notice));
  const publication = valuation.publication;
  const clocks = publication?.clocks ?? {};
  return (
    <section className="research-quality-notice" aria-labelledby="valuation-engine-title" aria-busy={["loading", "calculating"].includes(valuation.status)}>
      <div><h2 id="valuation-engine-title">Python valuation engine</h2>
        <p>Provider calculations use FastAPI. Financial facts, historical estimates, benchmark assumptions, and user overrides retain separate sources.</p>
      </div>
      {valuation.status === "loading" && <p role="status">Loading recommended valuation assumptions…</p>}
      {valuation.status === "calculating" && <p role="status">Updating Python valuation… The previous result is shown until recalculation completes.</p>}
      {valuation.error && <div role="alert" className="research-warning"><p>{valuation.error.message}</p><p>Valuation results are unavailable. No demonstration calculations have been substituted.</p><Button variant="outline" size="sm" onClick={valuation.retry}>Retry valuation request</Button></div>}
      {valuation.validationErrors.length > 0 && <div role="alert" className="research-warning">{valuation.validationErrors.map((error, index) => <p key={index}>{error}</p>)}</div>}
      <details className="provider-confidence" data-testid="dated-intrinsic-controls"><summary>Dated intrinsic analysis using imported financial evidence</summary>
        <p className="research-caption">An optional historical dividend scenario reads approved SEC imports and archived security proofs. It uses your explicit assumptions, requires no quote, and does not count as an automatic or current valuation.</p>
        <label className="research-caption"><input type="checkbox" checked={valuation.datedIntrinsic ?? false} onChange={(event) => valuation.setDatedIntrinsic(event.target.checked)} /> Use dated intrinsic analysis</label>
        {valuation.datedIntrinsic && <div className="assumption-grid">
          <div className="assumption-field"><label htmlFor="dated-evidence-as-of">Evidence as-of timestamp</label><Input id="dated-evidence-as-of" value={valuation.evidenceAsOf} placeholder="YYYY-MM-DDTHH:mm:ssZ" onChange={(event) => valuation.setEvidenceAsOf(event.target.value)} /><p className="assumption-explanation">Use the original interval in the approved import's archived reference attachment. Current-publication proofs are shown separately. The server verifies exact sources and identity; entering a past date cannot create proof.</p></div>
          <div className="assumption-field"><label htmlFor="dated-dividend-growth">Dividend growth assumption (%)</label><Input id="dated-dividend-growth" type="number" step="any" value={Number.isFinite(valuation.datedAssumptions.dividend_growth) ? valuation.datedAssumptions.dividend_growth * 100 : ""} onChange={(event) => valuation.editDatedAssumption("dividend_growth", event.target.value === "" ? "" : Number(event.target.value) / 100)} /></div>
          <div className="assumption-field"><label htmlFor="dated-required-return">Required return assumption (%)</label><Input id="dated-required-return" type="number" step="any" value={Number.isFinite(valuation.datedAssumptions.cost_of_equity) ? valuation.datedAssumptions.cost_of_equity * 100 : ""} onChange={(event) => valuation.editDatedAssumption("cost_of_equity", event.target.value === "" ? "" : Number(event.target.value) / 100)} /></div>
          <div className="assumption-field"><label htmlFor="dated-sustainable-dividend">Sustainable dividend assumption</label><select id="dated-sustainable-dividend" value={typeof valuation.datedAssumptions.stable_dividend_confirmed === "boolean" ? String(valuation.datedAssumptions.stable_dividend_confirmed) : ""} onChange={(event) => valuation.editDatedAssumption("stable_dividend_confirmed", event.target.value === "true")}><option value="">Not assumed</option><option value="true">Yes · explicit user assumption</option><option value="false">No</option></select><p className="assumption-explanation">A scenario assumption, not a reported sustainability fact. Only the dividend model and these forecast assumptions are used in dated mode.</p></div>
        </div>}
      </details>
      <div className="assumption-grid">
        <div className="assumption-field">
          <label htmlFor="manual-market-price">User-provided market price<span aria-hidden="true">{company.currency || "Currency unavailable"}</span></label>
          <Input id="manual-market-price" type="number" min="0" step="any" value={valuation.manualPrice ?? ""}
            disabled={valuation.datedIntrinsic || !/^[A-Z]{3}$/.test(company.currency ?? "")}
            aria-invalid={valuation.manualPrice !== null && (!Number.isFinite(valuation.manualPrice) || valuation.manualPrice <= 0)}
            aria-describedby="manual-market-price-help"
            onChange={(event) => valuation.setManualPrice(event.target.value === "" ? null : Number(event.target.value))} />
          <p id="manual-market-price-help" className="assumption-explanation">Optional comparison price in the reporting currency. It updates market comparisons and reverse DCF without changing the provider quote or stored financial facts.</p>
          {valuation.manualPrice !== null && <button className="research-text-button" onClick={() => valuation.setManualPrice(null)}>Reset comparison price</button>}
        </div>
        <div className="assumption-field">
          <p className="research-caption">Comparison source: {valuation.market.label || "Market provider price unavailable"}</p>
          <p className="research-caption">Provider-observed quote: {dollars(company.price, providerQuoteCurrency(company.market))} · {company.market?.price_timestamp || "Timestamp unavailable"}</p>
          <p className="research-caption">Engine: {valuation.engineVersion || "Loading"} · Calculated: {valuation.calculatedAt || "Unavailable"}</p>
          {valuation.assumptionMethodologyVersion && <p className="research-caption">Assumption methodology: {valuation.assumptionMethodologyVersion}</p>}
        </div>
      </div>
      {valuation.status === "ready" && valuation.summary.fairValue == null && <p className="research-caption">No supported weighted estimate is available. Open a model's details to see its missing inputs, then edit the relevant assumptions. An unsupported estimate is kept unavailable.</p>}
      {publication && <details className="provider-confidence" data-testid="valuation-publication-details"><summary>Valuation publication basis: {providerPublicationLabel(publication)}</summary>
        <p className="research-caption">Financial evidence availability, security compatibility and model eligibility are separate requirements. A manual comparison price does not establish a current provider quote.</p>
        {(publication.blockers ?? []).length > 0 && <ul className="provider-blocker-list">{publication.blockers.map((blocker, index) => <li key={`${blocker.code}-${index}`}><strong>{blocker.code?.replaceAll("_", " ") || "Unresolved check"}</strong><p>{blocker.message}</p>{blocker.fields?.length > 0 && <p className="research-caption">Affected inputs: {blocker.fields.join(", ")}</p>}</li>)}</ul>}
        <dl className="provider-record-metadata">
          <div><dt>Calculation time</dt><dd>{clocks.calculated_at || valuation.calculatedAt || "Unavailable"}</dd></div>
          <div><dt>Financial reporting period</dt><dd>{providerPeriodLabel(clocks.financial?.reporting_period) || "Unavailable"}</dd></div>
          <div><dt>Financial filing dates</dt><dd>{Array.isArray(clocks.financial?.filed_at) ? clocks.financial.filed_at.join(", ") || "Unavailable" : clocks.financial?.filed_at || "Unavailable"}</dd></div>
          <div><dt>Financial snapshot retrieved</dt><dd>{clocks.financial?.retrieved_at || "Unavailable"}</dd></div>
          <div><dt>Listing observed</dt><dd>{clocks.listing?.observed_on || "Unavailable"}</dd></div>
          <div><dt>Listing proof expires</dt><dd>{clocks.listing?.expires_at || "Unavailable"}</dd></div>
          <div><dt>Issuer linkage observed</dt><dd>{clocks.issuer_linkage?.observed_on || "Unavailable"}</dd></div>
          <div><dt>Issuer linkage proof expires</dt><dd>{clocks.issuer_linkage?.expires_at || "Unavailable"}</dd></div>
          <div><dt>Provider quote observed</dt><dd>{clocks.quote?.observed_at || "Unavailable"}</dd></div>
          <div><dt>Provider quote retrieved</dt><dd>{clocks.quote?.retrieved_at || "Unavailable"}</dd></div>
        </dl>
        {diagnosticMessages(publication.limitations).map((limitation, index) => <p className="research-caption" key={index}>{limitation}</p>)}
        <details className="research-original-diagnostics"><summary>Complete publication evidence and clocks</summary><pre>{JSON.stringify(publication, null, 2)}</pre></details>
      </details>}
      {Object.keys(valuation.snapshotDates ?? {}).length > 0 && <details className="provider-confidence"><summary>Financial and market snapshot dates</summary>
        {Object.entries(valuation.snapshotDates).map(([key, value]) => <p className="research-caption" key={key}><strong>{key.replaceAll("_", " ")}: </strong>{providerPeriodLabel(value) || "Unavailable"}</p>)}
      </details>}
      {currentNotices.map((notice, index) => <p className="research-caption" key={index}>{noticeMessage(notice)}</p>)}
      <SourceNoticeGroups notices={historicalNotices} label="Historical financial source checks" />
      {confidence && !valuation.diagnostics && <details className="provider-confidence"><summary>Valuation quality: {confidence.label || confidence.level || "See breakdown"}</summary>
        <p className="research-caption">A heuristic assessment of model and input quality, not a statistical probability or a measure of investment accuracy.</p>
        {Object.entries(confidence.breakdown ?? confidence.components ?? {}).map(([key, value]) => <p className="research-caption" key={key}><strong>{key.replaceAll("_", " ")}: </strong>{typeof value === "object" && value !== null ? value.explanation || value.description || JSON.stringify(value) : String(value)}</p>)}
        {(confidence.factors ?? []).map((factor, index) => <p className="research-caption" key={index}><strong>{factor.name}: </strong>{factor.explanation} ({factor.status?.replaceAll("_", " ")})</p>)}
        {confidence.disclaimer && <p className="research-caption">{confidence.disclaimer}</p>}
        {(confidence.warnings ?? []).map((warning, index) => <p className="research-caption" key={index}>{typeof warning === "string" ? warning : warning.message}</p>)}
      </details>}
    </section>
  );
}
