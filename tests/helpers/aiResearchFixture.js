// Synthetic UI transport data. These values and explanations are not financial
// expectations, a retrieved filing passage, or an actual OpenAI response.
export function aiResearchFixture(ticker = "MSFT", { kind = "report", marker = "Source-grounded interpretation", unavailable = false } = {}) {
  const id = `fixture:${ticker}:revenue`;
  const cik = { AAPL: "0000320193", MSFT: "0000789019", NVDA: "0001045810", ORCL: "0001341439" }[ticker];
  const evidence = { id, category: "reported_fact", provider: "SEC EDGAR", title: "Synthetic revenue transport fixture", ticker, metric: "revenue", value: 125000000, unit: "USD", period: "FY2025", observation_date: "2025-12-31", retrieved_at: "2026-10-15T08:00:00Z", source_url: `https://data.sec.gov/api/xbrl/companyfacts/CIK${cik}.json`, accession: null, derivation: "Synthetic transport value; not a financial observation.", quality_warnings: [], excerpt: null };
  const finding = { title: marker, explanation: unavailable ? "A defensible weighted intrinsic value is unavailable. Financial evidence can still be reviewed; missing model inputs are not treated as zero." : "<img src=x onerror=alert('unsafe')> This synthetic interpretation is displayed as plain text and retains its source reference.", evidence_ids: [id], category: "interpretation", uncertainty: "limited", quantitative_claims: [{ evidence_id: id, metric: "revenue", value: 125000000, unit: "USD", period: "FY2025", derivation: null }] };
  const common = { ticker, company_name: "Synthetic research fixture", generated_at: "2026-10-15T08:15:00Z", financial_snapshot_id: `financial-${ticker}`, valuation_snapshot_id: `valuation-${ticker}`, evidence_references: [evidence], snapshot_token: `synthetic-snapshot-${ticker}`, snapshot_dates: { financial: "2025-12-31", valuation: "2026-10-15T08:10:00Z", market: unavailable ? null : "2026-10-14T20:00:00Z" } };
  if (kind === "chat") return { ...common, answer: [finding], limitations: ["Synthetic answer; no live AI request was made."] };
  const unsupported = { title: "Source coverage is limited", explanation: "Verified evidence for this section is unavailable in this synthetic UI fixture. No unsupported financial claims are substituted.", evidence_ids: [], category: "unavailable", uncertainty: "unavailable", quantitative_claims: [] };
  return { ...common, sections: Object.fromEntries(["executive_summary", "business_overview", "financial_analysis", "valuation_analysis", "risks", "catalysts", "bull_case", "bear_case", "valuation_drivers", "data_limitations"].map((section) => [section, [structuredClone(section === "executive_summary" || section === "valuation_analysis" ? finding : unsupported)]])), quality_warnings: ["Policy-based single-model illustration; not independent confirmation."], cache_status: "miss" };
}

// Synthetic final API response after the backend derives citations from bound
// quantities. It tests rendering and source selection, not financial analysis.
export function derivedCitationChatFixture() {
  const response = aiResearchFixture("MSFT", { kind: "chat" });
  const reported = response.evidence_references[0];
  const source = (metric, value, unit, extra = {}) => ({
    ...reported, id: `fixture:MSFT:${metric}`, metric, value, unit,
    title: `Synthetic ${metric.replaceAll("_", " ")} source`, ...extra,
  });
  const fair = source("base_fair_value", 777.77, "USD/share", {
    category: "valuation_output", provider: "Fairworth Python valuation engine",
    source_url: null, derivation: "Synthetic base scenario summary.fair_value transport value.",
  });
  const quote = source("market_price", 100, "USD/share", {
    provider: "FMP", period: null, observation_date: "2026-01-15T16:00:00Z",
    source_url: "https://financialmodelingprep.com/stable/quote",
    derivation: null,
  });
  const count = source("base_contributing_model_count", 1, "models", {
    category: "valuation_output", provider: "Fairworth Python valuation engine",
    source_url: null, derivation: "Synthetic base scenario summary.count transport value.",
  });
  const liabilities = source("total_liabilities", 500000000, "USD", { derivation: null });
  const debt = source("debt", null, "USD", {
    category: "unavailable", derivation: "Complete synthetic current and noncurrent debt components are unavailable.",
  });
  const claim = (item) => Object.fromEntries(["id", "metric", "value", "unit", "period", "derivation"].map((key) => [key === "id" ? "evidence_id" : key, item[key]]));
  return {
    ...response, evidence_references: [fair, quote, count, liabilities, debt],
    answer: [
      {
        title: "A policy-based single-model illustration",
        explanation: "The illustrative fair value is $777.77 per share versus a dated market price of $100.00, with 1 contributing model. Independent confirmation remains unavailable.",
        category: "policy_estimate", uncertainty: "limited",
        // This final list includes the sources the server recovered from values;
        // the frontend must display the complete list without inferring its own.
        evidence_ids: [fair.id, quote.id, count.id],
        quantitative_claims: [fair, quote, count].map(claim),
      },
      {
        title: "Liabilities do not establish complete debt",
        explanation: "Reported total liabilities of $500,000,000 do not establish complete total debt. The debt-dependent valuation methods remain unsupported.",
        category: "interpretation", uncertainty: "analytical",
        evidence_ids: [debt.id, liabilities.id], quantitative_claims: [claim(liabilities)],
      },
    ],
  };
}
