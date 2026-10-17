import test from "node:test";
import assert from "node:assert/strict";
import { askResearchQuestion, generateResearchReport, loadResearchStatus, researchSession, safeEvidenceUrl, validateResearchResponse } from "../../src/services/aiResearch.js";
import { aiResearchFixture } from "../helpers/aiResearchFixture.js";

test("research session is opaque, tab-scoped, and works when browser storage is unavailable", () => {
  const records = new Map();
  const storage = { getItem: (key) => records.get(key), setItem: (key, value) => records.set(key, value) };
  const id = researchSession({ storage });
  assert.match(id, /^[a-zA-Z0-9_-]{16,128}$/);
  assert.equal(researchSession({ storage }), id);
  assert.deepEqual([...records.keys()], ["fairworth.research.session"]);
  assert.equal(researchSession({ storage: { getItem() { throw Error("blocked"); }, setItem() { throw Error("blocked"); } } }), id);
  records.set("fairworth.research.session", "x".repeat(120));
  assert.equal(researchSession({ storage }), id);
});

test("research transport scopes requests and sends explicit valuation inputs without provider secrets", async () => {
  const calls = [];
  const valuation = { assumptions: { target_pe: 30 }, manual_market_price: null };
  const fetcher = async (url, options) => {
    calls.push({ url, ...options });
    const json = url.endsWith("/status") ? { available: true } : aiResearchFixture("AAPL", { kind: url.endsWith("/chat") ? "chat" : "report" });
    return new Response(JSON.stringify(json));
  };
  const options = { fetcher, session: "synthetic-session-token" };
  await loadResearchStatus("AAPL", options);
  await generateResearchReport("AAPL", valuation, { ...options, regenerate: true });
  const history = Array.from({ length: 16 }, (_, index) => ({ role: index % 2 ? "assistant" : "user", content: "x".repeat(2100), privateExtra: "not sent" }));
  await askResearchQuestion("AAPL", "Why this valuation?", history, valuation, options);
  assert.ok(calls[0].url.endsWith("/AAPL/ai/status"));
  assert.equal(calls[1].headers["X-Fairworth-Session"], "synthetic-session-token");
  assert.deepEqual(JSON.parse(calls[1].body), { valuation, regenerate: true });
  const chat = JSON.parse(calls[2].body);
  assert.equal(chat.history.length, 8);
  assert.ok(chat.history.every((item) => item.content.length === 2000 && !Object.hasOwn(item, "privateExtra")));
  assert.deepEqual(chat.valuation, valuation);
  assert.ok(!calls.some((call) => /openai|api_key|apikey/i.test(call.url + JSON.stringify(call.headers))));
});

test("financial research does not require a supported valuation and safe provider failures are retained", async () => {
  const calls = [];
  const fetcher = async (_url, options) => { calls.push(options); return new Response(JSON.stringify(aiResearchFixture("NVDA", { unavailable: true }))); };
  const result = await generateResearchReport("NVDA", undefined, { fetcher, session: "synthetic-session-token" });
  assert.match(result.sections.valuation_analysis[0].explanation, /unavailable/);
  assert.deepEqual(JSON.parse(calls[0].body), { regenerate: false });
  await assert.rejects(generateResearchReport("NVDA", undefined, { session: "synthetic-session-token", fetcher: async () => new Response(JSON.stringify({ error: { message: "Research usage limit reached.", code: "ai_rate_limited" } }), { status: 429 }) }), (error) => error.code === "ai_rate_limited" && error.message === "Research usage limit reached.");
});

test("research rejects incompatible companies and malformed structured responses", () => {
  assert.throws(() => validateResearchResponse(aiResearchFixture("MSFT"), "ORCL"), /does not match/);
  assert.throws(() => validateResearchResponse({ ticker: "MSFT", sections: {}, evidence_references: [] }, "MSFT"), /incomplete/);
  const fixture = aiResearchFixture();
  fixture.sections.executive_summary[0].evidence_ids = "not an array";
  assert.throws(() => validateResearchResponse(fixture, "MSFT"), /incomplete/);
  assert.throws(() => validateResearchResponse({ ticker: "MSFT", answer: "unstructured", evidence_references: [] }, "MSFT", "chat"), /incomplete/);
  for (const mutate of [
    (finding) => { finding.evidence_ids = ["unregistered-source"]; },
    (finding) => { finding.quantitative_claims = {}; },
    (finding) => { finding.quantitative_claims[0].value = Infinity; },
  ]) {
    const malformed = aiResearchFixture();
    mutate(malformed.sections.executive_summary[0]);
    assert.throws(() => validateResearchResponse(malformed, "MSFT"), (error) => error.code === "invalid_response");
  }
});

test("citation URLs permit approved primary providers and reject arbitrary, credentialed or executable links", () => {
  assert.equal(safeEvidenceUrl("https://www.sec.gov/Archives/edgar/data/1/filing.htm"), "https://www.sec.gov/Archives/edgar/data/1/filing.htm");
  assert.ok(safeEvidenceUrl("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/2026"));
  for (const url of ["javascript:alert(1)", "http://www.sec.gov/filing", "https://www.sec.gov.attacker.test/filing", "https://username:password@www.sec.gov/filing", "https://www.sec.gov:444/filing", "https://attacker.test", "https://financialmodelingprep.com/stable/quote?apikey=synthetic-private-value", "https://www.sec.gov/Archives/edgar/data/1/filing.htm#untrusted", "https://www.sec.gov/Archives/edgar/data/../private", "https://www.sec.gov/Archives/edgar/data/%2e%2e/private", "https://www.sec.gov/Archives/edgar/data/%5cprivate", "https://www.sec.gov/unapproved-path", null]) assert.equal(safeEvidenceUrl(url), null);
});
