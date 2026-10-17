import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { askResearchQuestion, generateResearchReport, loadResearchStatus, safeEvidenceUrl } from "@/services/aiResearch";
import { financialTerminologyNote, formatObservationDate, formatResearchValue, researchMetricLabel } from "@/lib/researchPresentation";
import "@/ai-research.css";

const sections = [
  ["executive_summary", "Executive summary"], ["business_overview", "Business overview"],
  ["financial_analysis", "Financial performance"], ["valuation_analysis", "Valuation analysis"],
  ["risks", "Risks"], ["catalysts", "Potential catalysts"], ["bull_case", "Bull case"],
  ["bear_case", "Bear case"], ["valuation_drivers", "What could change the valuation?"],
  ["data_limitations", "Data limitations"],
];

const categoryLabels = {
  reported_fact: "Reported financial fact", fact: "Reported financial fact", historical_derived_metric: "Historical derived metric",
  historical_metric: "Historical derived metric", derived_metric: "Historical derived metric", valuation_output: "Valuation model output", valuation_model_output: "Valuation model output", model_output: "Valuation model output",
  policy_based: "Policy-based estimate", policy_estimate: "Policy-based estimate", user_defined: "User-defined assumption",
  user_assumption: "User-defined assumption", interpretation: "AI-generated interpretation", analytical_scenario: "Analytical scenario",
  unavailable: "Unavailable information", data_limitation: "Data limitation",
  filing_excerpt: "Retrieved filing passage", company_profile: "Provider company profile",
};

function readable(value) {
  if (value === null || value === undefined || value === "") return "Unavailable";
  if (typeof value === "object") return Object.entries(value).map(([key, item]) => `${key.replaceAll("_", " ")}: ${readable(item)}`).join(" · ");
  return String(value);
}

function SourceDialog({ source, onClose }) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  const url = safeEvidenceUrl(source.source_url);
  const fields = [
    ["Provider", source.provider], ["Company", source.ticker], ["Evidence category", categoryLabels[source.category] ?? source.category?.replaceAll("_", " ")],
    ["Fiscal period", source.period], ["Observation / filing date", source.observation_date], ["Retrieved", source.retrieved_at],
    ["Metric", source.metric], ["Value", source.value === null || source.value === undefined ? null : `${readable(source.value)} ${source.unit ?? ""}`],
    ["Accession", source.accession], ["Derivation", source.derivation], ["Source excerpt", source.excerpt],
  ];
  return <dialog ref={ref} className="ai-source-dialog" aria-labelledby="ai-source-title" onCancel={onClose} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <h2 id="ai-source-title">{source.title || "Evidence source"}</h2>
    <button type="button" onClick={onClose} autoFocus>Close</button>
    <dl>{fields.filter(([, value]) => value !== null && value !== undefined && value !== "").map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{readable(value)}</dd></div>)}</dl>
    {(source.quality_warnings ?? []).map((warning, index) => <p key={index}>{warning}</p>)}
    {url ? <a href={url} target="_blank" rel="noopener noreferrer">Open original source</a> : <p>An approved original source link is unavailable. The evidence details above remain available for review.</p>}
  </dialog>;
}

function Finding({ finding, evidence, onSource }) {
  const claims = finding.quantitative_claims ?? [];
  const quote = claims.find((claim) => claim.metric === "market_price");
  const quoteSource = quote && evidence.find((item) => item.id === quote.evidence_id);
  const observed = formatObservationDate(quoteSource?.observation_date);
  const terminology = financialTerminologyNote(finding, evidence);
  return <article className="ai-finding">
    <h4>{finding.title}</h4>
    <div className="ai-finding-meta"><span>{categoryLabels[finding.category] ?? finding.category?.replaceAll("_", " ") ?? "AI-generated interpretation"}</span>{finding.uncertainty && <span>Uncertainty: {finding.uncertainty.replaceAll("_", " ")}</span>}</div>
    <p className="ai-explanation">{finding.explanation}</p>
    {quote && <div className="ai-quote-observation" aria-label="Market price observation"><span>Market price <strong>{formatResearchValue(quote)}</strong></span>{observed ? <time dateTime={quoteSource.observation_date}>Observed {observed}</time> : <span>Observation date unavailable</span>}</div>}
    {terminology && <aside className="ai-terminology">{terminology}</aside>}
    {claims.length > 0 && <details className="ai-quantitative"><summary>Verified figures ({claims.length})</summary><ul aria-label="Evidence-backed quantities">{claims.map((claim, index) => <li key={index}><span>{researchMetricLabel(claim.metric)}</span><strong>{formatResearchValue(claim)}</strong>{claim.period && <small>{readable(claim.period)}</small>}</li>)}</ul><p className="ai-disclaimer">Rounded for display. Open a source to inspect the exact value, units, period and derivation.</p></details>}
    <div className="ai-evidence"><div className="ai-evidence-label">Sources · {finding.evidence_ids.length}</div><div className="ai-citations">{finding.evidence_ids.map((id) => {
      const source = evidence.find((item) => item.id === id);
      return source ? <button type="button" key={id} onClick={() => onSource(source)} aria-label={`View source: ${source.title}`}><span>{researchMetricLabel(source.metric)}</span><span className="ai-citation-provider">{source.provider || "Source"}</span></button> : <span key={id} className="ai-disclaimer">Referenced source unavailable</span>;
    })}</div></div>
  </article>;
}

function ResearchLimitations({ items, label = "Research limitations" }) {
  const priorities = [/illustrative|policy.based/i, /independent model confirmation|single.model/i, /observations are.*dated/i];
  const important = [...new Set(priorities.map((pattern) => items.find((item) => pattern.test(item))).filter(Boolean))];
  return <aside className="ai-note ai-limitations" aria-label={label}>
    <h4>{label}</h4>
    {important.length > 0 && <ul className="ai-key-limitations">{important.map((item) => <li key={item}>{item}</li>)}</ul>}
    <details><summary>View all source and data notices ({items.length})</summary><ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul></details>
  </aside>;
}

function Report({ report, onSource }) {
  return <div aria-label={`${report.ticker} research report`}>
    <dl className="ai-snapshot">
      {[ ["Report generated", report.generated_at], ["Financial snapshot date", report.snapshot_dates?.financial], ["Financial reporting period", report.snapshot_dates?.reporting_period], ["Valuation snapshot date", report.snapshot_dates?.valuation], ["Market observation", report.snapshot_dates?.market] ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{readable(value)}</dd></div>)}
      <div><dt>Report reuse</dt><dd>{report.cache_status === "hit" ? "Reused report for this evidence snapshot" : "Newly generated report"}</dd></div>
    </dl>
    {report.quality_warnings?.length > 0 && <ResearchLimitations items={report.quality_warnings} label="Research quality warnings" />}
    {sections.map(([key, label]) => <section className="ai-report-section" key={key} aria-labelledby={`ai-${key}`}><h3 id={`ai-${key}`}>{label}</h3>{report.sections[key]?.length ? report.sections[key].map((finding, index) => <Finding finding={finding} evidence={report.evidence_references} onSource={onSource} key={index} />) : <p>Verified evidence for this section is unavailable. No unsupported findings have been substituted.</p>}</section>)}
    <section className="ai-report-section" aria-labelledby="ai-sources"><h3 id="ai-sources">Sources</h3><ul className="ai-source-list">{report.evidence_references.map((source) => <li key={source.id}><button type="button" onClick={() => onSource(source)}>{source.title || source.id}</button><span>{source.provider} · {readable(source.period || source.observation_date)}</span></li>)}</ul>{!report.evidence_references.length && <p>No source references were returned.</p>}</section>
  </div>;
}

export default function AIResearchWorkspace({ company, valuation, active }) {
  const [status, setStatus] = useState({ response: null, error: null });
  const [statusAttempt, setStatusAttempt] = useState(0);
  const [report, setReport] = useState(null);
  const [reportState, setReportState] = useState({ loading: false, error: null });
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState([]);
  const [chatState, setChatState] = useState({ loading: false, error: null });
  const [source, setSource] = useState(null);
  const controllers = useRef(new Set());
  const ticker = company.ticker;

  useEffect(() => {
    if (!active || status.response) return;
    const controller = new AbortController();
    loadResearchStatus(ticker, { signal: controller.signal }).then((response) => {
      if (!controller.signal.aborted) setStatus({ response, error: null });
    }).catch((error) => {
      if (!controller.signal.aborted) setStatus({ response: null, error });
    });
    return () => controller.abort();
  }, [active, ticker, statusAttempt, status.response]);

  useEffect(() => {
    const current = controllers.current;
    return () => { current.forEach((controller) => controller.abort()); };
  }, []);

  const inputInvalid = valuation.validationErrors.length > 0;
  const updating = ["loading", "calculating"].includes(valuation.status);
  const busy = reportState.loading || chatState.loading;
  const available = status.response?.available === true;
  const enabled = available && !inputInvalid && !updating && !busy;
  // A failed dashboard calculation must not discard valid explicit inputs.
  // The research backend retries the same request and labels unavailable results.
  const context = inputInvalid ? undefined : valuation.valuationRequest;

  async function generate(regenerate = false) {
    if (!enabled) return;
    const controller = new AbortController();
    controllers.current.add(controller);
    setReportState({ loading: true, error: null });
    try {
      const response = await generateResearchReport(ticker, context, { regenerate, signal: controller.signal });
      if (!controller.signal.aborted) { setReport(response); setReportState({ loading: false, error: null }); }
    } catch (error) {
      if (!controller.signal.aborted) setReportState({ loading: false, error });
    } finally { controllers.current.delete(controller); }
  }

  async function ask(event) {
    event.preventDefault();
    const submitted = question.trim();
    if (!enabled || !submitted || submitted.length > 1500) return;
    const controller = new AbortController();
    controllers.current.add(controller);
    setChatState({ loading: true, error: null });
    try {
      const history = turns.flatMap((turn) => [{ role: "user", content: turn.question }, { role: "assistant", content: turn.response.answer.map((finding) => finding.explanation).join("\n") }]);
      const response = await askResearchQuestion(ticker, submitted, history, context, { signal: controller.signal });
      if (!controller.signal.aborted) { setTurns((previous) => [...previous.slice(-3), { question: submitted, response }]); setQuestion(""); setChatState({ loading: false, error: null }); }
    } catch (error) {
      if (!controller.signal.aborted) setChatState({ loading: false, error });
    } finally { controllers.current.delete(controller); }
  }

  const examples = [`Why is ${ticker}'s valuation available or unavailable?`, "Which assumptions could change the fair value most?", "What financial risks are supported by the evidence?", "What is the difference between FCFF and FCFE?"];
  return <section id="ai-research" className="ai-workspace" hidden={!active} aria-labelledby="ai-research-title">
    <div className="ai-intro"><h2 id="ai-research-title">AI Research · {ticker}</h2><p>Explore verified company evidence and understand Fairworth's deterministic valuation results. Research remains available when a supported fair value cannot be calculated.</p><p className="ai-disclaimer">AI-generated interpretation, not audited research or investment advice. Financial facts, historical estimates, policy assumptions, user inputs, and unavailable information are identified separately. Review the sources and observation dates.</p><p className="ai-disclaimer">Changing valuation inputs or companies clears this research and conversation. Chat does not modify your assumptions. Numerical what-if calculations require the valuation editor.</p></div>
    {!status.response && !status.error && <p className="ai-status" role="status">Checking AI research availability…</p>}
    {status.error && <div className="ai-note" role="alert"><p>{status.error.message}</p><Button variant="outline" size="sm" onClick={() => { setStatus({ response: null, error: null }); setStatusAttempt((value) => value + 1); }}>Retry research status</Button></div>}
    {status.response && <div className="ai-note"><p className="ai-status">{status.response.message || (available ? "AI research is available." : "AI research is disabled or not configured on the backend.")}</p>{status.response.limitations?.length > 0 && <ul>{status.response.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul>}</div>}
    {inputInvalid && <p className="ai-status" role="status">Resolve the invalid valuation inputs before researching this assumption set.</p>}
    {updating && <p className="ai-status" role="status">Waiting for the valuation request to finish so research uses the matching assumptions.</p>}
    {valuation.status === "error" && <p className="ai-status">The dashboard calculation failed. Research will retry with your current valid assumptions against available financial evidence and disclose any unavailable valuation results.</p>}
    <div className="ai-controls"><Button onClick={() => generate(false)} disabled={!enabled}>{reportState.loading ? "Generating research…" : report ? "Load matching report" : "Generate research report"}</Button>{report && <Button variant="outline" onClick={() => generate(true)} disabled={!enabled}>Regenerate report</Button>}</div>
    {reportState.loading && <p role="status" className="ai-status">Preparing a source-grounded report. This may take a moment.</p>}
    {reportState.error && <div role="alert" className="ai-note"><p>{reportState.error.message}</p><p>No replacement research has been fabricated. You can retry generation.</p></div>}
    {report && <Report report={report} onSource={setSource} />}
    <section className="ai-chat" aria-labelledby="ai-chat-title"><h3 id="ai-chat-title">Ask Fairworth AI</h3><p>Questions use {ticker}'s verified evidence and the displayed valuation assumptions. This conversation stays in this workspace; only the most recent four exchanges are retained.</p><div className="ai-examples">{examples.map((example) => <button type="button" key={example} onClick={() => setQuestion(example)} disabled={!enabled}>{example}</button>)}</div>
      <form onSubmit={ask}><label htmlFor="ai-question">Your question about {ticker}</label><textarea id="ai-question" maxLength={1500} value={question} onChange={(event) => setQuestion(event.target.value)} disabled={!enabled} placeholder="Ask about financial performance, assumptions, or valuation limitations…" /><div className="ai-chat-actions"><Button type="submit" disabled={!enabled || !question.trim()}>{chatState.loading ? "Preparing answer…" : "Ask question"}</Button><span>{question.length} / 1,500 characters</span>{turns.length > 0 && <Button variant="ghost" type="button" onClick={() => setTurns([])} disabled={busy}>Clear conversation</Button>}</div></form>
      {chatState.loading && <p role="status" className="ai-status">Reviewing the company evidence…</p>}
      {chatState.error && <div role="alert" className="ai-note"><p>{chatState.error.message}</p><p>Your question is preserved so you can retry.</p></div>}
      <div aria-live="polite">{turns.map((turn, index) => <article className="ai-turn" key={index}><p className="ai-user-question">You: {turn.question}</p>{turn.response.answer.map((finding, findingIndex) => <Finding finding={finding} evidence={turn.response.evidence_references} onSource={setSource} key={findingIndex} />)}{turn.response.limitations?.length > 0 && <ResearchLimitations items={turn.response.limitations} />}<p className="ai-disclaimer">Answered: {turn.response.generated_at} · AI-generated interpretation</p></article>)}</div>
    </section>
    {source && <SourceDialog source={source} onClose={() => setSource(null)} />}
  </section>;
}
