import { test, expect } from "@playwright/test";
import { providerFixture } from "./helpers/providerFixture.js";
import { automaticProviderValuationFixture } from "./helpers/providerValuationFixture.js";
import { aiResearchFixture, derivedCitationChatFixture } from "./helpers/aiResearchFixture.js";
import { msftV8PresentationFixture } from "./helpers/msftV8Fixture.js";
import { formatResearchValue } from "../src/lib/researchPresentation.js";

async function mockResearch(page, { available = true, reportHandler, chatHandler, statusHandler, valuationHandler, unavailable = false } = {}) {
  const calls = [];
  const financial = providerFixture();
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const ticker = url.pathname.split("/")[3];
    if (url.pathname.includes("/ai/")) {
      const body = request.method() === "POST" ? request.postDataJSON() : null;
      const call = { path: url.pathname, ticker, body, headers: await request.allHeaders() };
      calls.push(call);
      if (url.pathname.endsWith("/status")) {
        if (statusHandler && await statusHandler(route, call)) return;
        return route.fulfill({ json: { enabled: available, configured: available, available, message: available ? "Research available for the configured backend model." : "AI research is disabled. Configure the backend API key and model to enable it.", limitations: ["Financial observations are dated; source coverage may be incomplete."] } });
      }
      if (url.pathname.endsWith("/report") && reportHandler && await reportHandler(route, call)) return;
      if (url.pathname.endsWith("/chat") && chatHandler && await chatHandler(route, call)) return;
      return route.fulfill({ json: aiResearchFixture(ticker, { kind: url.pathname.endsWith("/chat") ? "chat" : "report", unavailable }) });
    }
    if (url.pathname.includes("/valuation/")) {
      const body = request.method() === "POST" ? request.postDataJSON() : {};
      if (valuationHandler && await valuationHandler(route, body)) return;
      const json = automaticProviderValuationFixture(ticker, { request: body, price: unavailable ? null : 100 });
      if (unavailable) for (const scenario of Object.values(json.scenarios)) { scenario.summary.fair_value = null; scenario.summary.classification = "unavailable"; scenario.summary.count = 0; scenario.summary.effective_weights = {}; }
      return route.fulfill({ json });
    }
    const json = url.pathname.endsWith("/financials") ? url.searchParams.get("period") === "quarterly" ? financial.quarterly : financial.annual : url.pathname.endsWith("/metrics") ? financial.metrics : url.pathname.endsWith("/data-status") ? financial.dataStatus : financial.profile;
    return route.fulfill({ json: json.company ? { ...json, company: { ...json.company, ticker } } : { ...json, ticker } });
  });
  return calls;
}

async function openResearch(page, ticker = "MSFT") {
  await page.goto(`/stocks/${ticker}`);
  await page.getByRole("group", { name: "Financial data mode" }).getByRole("button", { name: "Provider data", exact: true }).click();
  await expect(page.getByTestId("weighted-classification")).toBeVisible();
  await page.getByRole("group", { name: "Company workspace view" }).getByRole("button", { name: "AI Research", exact: true }).click();
  await expect(page.getByRole("heading", { name: `AI Research · ${ticker}`, exact: true })).toBeVisible();
  await expect.poll(async () => {
    const heading = await page.getByRole("heading", { name: `AI Research · ${ticker}`, exact: true }).boundingBox();
    const header = await page.locator(".site-header").boundingBox();
    return heading.y >= header.y + header.height;
  }).toBe(true);
  return page.getByRole("button", { name: "Generate research report", exact: true });
}

test("source-grounded report displays dated sections, safe citations, and plain text on desktop and mobile", async ({ page }) => {
  const calls = await mockResearch(page);
  const generate = await openResearch(page, "AAPL");
  await expect(generate).toBeEnabled();
  expect(calls.filter((call) => call.path.endsWith("/report"))).toHaveLength(0);
  await generate.click();
  const report = page.getByLabel("AAPL research report", { exact: true });
  await expect(report).toBeVisible();
  await expect(report.getByRole("heading", { name: "Executive summary", exact: true })).toBeVisible();
  await expect(report).toContainText("2025-12-31");
  await expect(report).toContainText("Policy-based single-model illustration");
  await expect(report).toContainText("<img src=x onerror=alert('unsafe')>");
  await expect(report.locator("img")).toHaveCount(0);
  await expect(report.getByRole("heading", { name: "What could change the valuation?", exact: true })).toBeVisible();
  await report.getByRole("button", { name: "View source: Synthetic revenue transport fixture", exact: true }).first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("SEC EDGAR");
  await expect(dialog).toContainText("125000000 USD");
  await expect(dialog.getByRole("link", { name: "Open original source" })).toHaveAttribute("href", "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json");
  await dialog.getByRole("button", { name: "Close", exact: true }).click();
  const request = calls.find((call) => call.path.endsWith("/report"));
  expect(request.body.valuation.assumptions).toEqual({});
  expect(request.headers["x-fairworth-session"]).toMatch(/^[a-zA-Z0-9_-]{16,128}$/);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width + 1);
});

test("company-scoped chat retains bounded conversation and leaves valuation assumptions unchanged", async ({ page }) => {
  const calls = await mockResearch(page);
  await openResearch(page);
  await expect(page.getByRole("textbox", { name: "Your question about MSFT", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Which assumptions could change the fair value most?", exact: true }).click();
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  await expect(page.locator(".ai-turn")).toHaveCount(1);
  await page.getByRole("textbox", { name: "Your question about MSFT", exact: true }).fill("What if growth changes?");
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  await expect(page.locator(".ai-turn")).toHaveCount(2);
  const requests = calls.filter((call) => call.path.endsWith("/chat"));
  expect(requests[1].body.history).toHaveLength(2);
  expect(requests[1].body.valuation.assumptions).toEqual({});
  await page.getByRole("group", { name: "Company workspace view" }).getByRole("button", { name: "Valuation", exact: true }).click();
  await expect(page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true })).toHaveValue("22.5");
  await page.getByRole("group", { name: "Company workspace view" }).getByRole("button", { name: "AI Research", exact: true }).click();
  await expect(page.locator(".ai-turn")).toHaveCount(2);
  await page.getByRole("button", { name: "Clear conversation", exact: true }).click();
  await expect(page.locator(".ai-turn")).toHaveCount(0);
});

test("backend-derived quantity citations render every source and open the matching financial value", async ({ page }) => {
  const answer = derivedCitationChatFixture();
  const calls = await mockResearch(page, { chatHandler: async (route) => {
    await route.fulfill({ json: answer });
    return true;
  } });
  await openResearch(page);
  await page.getByRole("button", { name: "Why is MSFT's valuation available or unavailable?", exact: true }).click();
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  const turn = page.locator(".ai-turn");
  await expect(turn).toHaveCount(1);
  await expect(turn.locator(".ai-quantitative li")).toHaveCount(4);
  await expect(turn.locator(".ai-citations button")).toHaveCount(5);
  const sources = new Map(answer.evidence_references.map((item) => [item.id, item]));
  for (const [findingIndex, finding] of answer.answer.entries()) {
    const article = turn.locator(".ai-finding").nth(findingIndex);
    await expect(article.locator(":scope > p")).toHaveText(finding.explanation);
    if (finding.quantitative_claims.length) await article.locator(".ai-quantitative summary").click();
    for (const [claimIndex, claim] of finding.quantitative_claims.entries()) {
      const source = sources.get(claim.evidence_id);
      const sourcePosition = finding.evidence_ids.indexOf(claim.evidence_id);
      expect(sourcePosition).toBeGreaterThanOrEqual(0);
      await expect(article.locator(".ai-quantitative li").nth(claimIndex)).toContainText(formatResearchValue(claim));
      const citation = article.locator(".ai-citations button").nth(sourcePosition);
      await expect(citation).toHaveAttribute("aria-label", `View source: ${source.title}`);
      await citation.click();
      const dialog = page.getByRole("dialog");
      await expect(dialog.getByRole("heading", { name: source.title, exact: true })).toBeVisible();
      const sourceField = (label) => dialog.locator("dl > div").filter({ has: page.getByText(label, { exact: true }) }).locator("dd");
      await expect(sourceField("Value")).toHaveText(`${claim.value} ${claim.unit}`);
      await expect(sourceField("Metric")).toHaveText(claim.metric);
      await expect(sourceField("Provider")).toHaveText(source.provider);
      await expect(sourceField("Observation / filing date")).toHaveText(source.observation_date);
      if (claim.period) await expect(sourceField("Fiscal period")).toHaveText(claim.period);
      if (claim.derivation) await expect(sourceField("Derivation")).toHaveText(claim.derivation);
      if (source.source_url) await expect(dialog.getByRole("link", { name: "Open original source", exact: true })).toHaveAttribute("href", source.source_url);
      else await expect(dialog.getByRole("link", { name: "Open original source", exact: true })).toHaveCount(0);
      await dialog.getByRole("button", { name: "Close", exact: true }).click();
    }
  }
  const limitation = turn.locator(".ai-finding").nth(1);
  await limitation.getByRole("button", { name: "View source: Synthetic debt source", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("Complete synthetic current and noncurrent debt components are unavailable.");
  await expect(page.getByRole("dialog").locator("dl > div").filter({ has: page.getByText("Value", { exact: true }) })).toHaveCount(0);
  await page.getByRole("dialog").getByRole("button", { name: "Close", exact: true }).click();
  expect(calls.filter((call) => call.path.endsWith("/chat"))).toHaveLength(1);
  expect(calls.filter((call) => call.path.endsWith("/report"))).toHaveLength(0);
  await page.getByRole("group", { name: "Company workspace view" }).getByRole("button", { name: "Valuation", exact: true }).click();
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$777.77");
  await expect(page.getByRole("alert")).toContainText("Single-model estimate");
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width + 1);
});

test("exact successful v8 replay has natural spacing, rounded figures, dated quote and complete inspectable evidence", async ({ page }) => {
  const answer = msftV8PresentationFixture();
  const calls = await mockResearch(page, { chatHandler: async (route) => { await route.fulfill({ json: answer }); return true; } });
  await openResearch(page);
  await page.getByRole("button", { name: "Why is MSFT's valuation available or unavailable?", exact: true }).click();
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  const turn = page.locator(".ai-turn");
  await expect(turn.locator(".ai-finding")).toHaveCount(2);
  const first = turn.locator(".ai-finding").first();
  await expect(first.locator(".ai-explanation")).toHaveText(answer.answer[0].explanation);
  await expect(first.locator(".ai-explanation")).toContainText("fair value $619.56 and a dated market comparison price $539.44. Only 1 model contributes: Forward P/E. Many");
  await expect(first.locator(".ai-explanation")).not.toContainText("value$619.56and");
  const quote = first.getByLabel("Market price observation");
  await expect(quote).toContainText("$539.44 / share");
  await expect(quote.locator("time")).toHaveText("Observed Oct 15, 2026");
  await expect(quote.locator("time")).toHaveAttribute("datetime", "2026-10-15T20:00:01+00:00");
  await expect(quote).not.toContainText("Oct 16");
  await expect(first.locator(".ai-terminology")).toContainText("EV/EBITDA lists EBITDA margin as missing");
  await expect(first.locator(".ai-quantitative ul")).not.toBeVisible();
  await first.locator(".ai-quantitative summary").click();
  await expect(first.locator(".ai-quantitative li").first()).toContainText("$619.56 / share");
  await expect(first.locator(".ai-quantitative")).not.toContainText("619.5604742486083");
  await expect(first.locator(".ai-quantitative li").nth(2)).toContainText("1 model");
  const notices = turn.getByLabel("Research limitations", { exact: true });
  await expect(notices.locator("details ul")).not.toBeVisible();
  await expect(notices.locator(".ai-key-limitations")).toContainText("policy-based and illustrative");
  await expect(notices.locator(".ai-key-limitations")).toContainText("no independent model confirmation");
  await notices.locator("summary").click();
  await expect(notices.locator("details li")).toHaveCount(answer.limitations.length);
  for (const [index, finding] of answer.answer.entries()) {
    const article = turn.locator(".ai-finding").nth(index);
    await expect(article.locator(".ai-explanation")).toHaveText(finding.explanation);
    for (const id of finding.evidence_ids) {
      const source = answer.evidence_references.find((item) => item.id === id);
      await article.getByRole("button", { name: `View source: ${source.title}`, exact: true }).click();
      const dialog = page.getByRole("dialog");
      const field = (label) => dialog.locator("dl > div").filter({ has: page.getByText(label, { exact: true }) }).locator("dd");
      await expect(field("Metric")).toHaveText(source.metric);
      await expect(field("Provider")).toHaveText(source.provider);
      if (source.metric === "base_fair_value") await expect(field("Value")).toHaveText("619.5604742486083 USD/share");
      if (source.observation_date) await expect(field("Observation / filing date")).toHaveText(source.observation_date);
      if (source.retrieved_at) await expect(field("Retrieved")).toHaveText(source.retrieved_at);
      if (source.period) await expect(field("Fiscal period")).toHaveText(source.period);
      if (source.derivation) await expect(field("Derivation")).toHaveText(source.derivation);
      await dialog.getByRole("button", { name: "Close", exact: true }).click();
    }
  }
  expect(calls.filter((call) => call.path.endsWith("/chat"))).toHaveLength(1);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width + 1);
});

test("missing quote observation date never falls back to a provider retrieval date", async ({ page }) => {
  const answer = msftV8PresentationFixture();
  answer.evidence_references.find((source) => source.metric === "market_price").observation_date = null;
  await mockResearch(page, { chatHandler: async (route) => { await route.fulfill({ json: answer }); return true; } });
  await openResearch(page);
  await page.getByRole("textbox", { name: "Your question about MSFT", exact: true }).fill("Why is MSFT's valuation available or unavailable?");
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  const quote = page.getByLabel("Market price observation");
  await expect(quote).toContainText("Observation date unavailable");
  await expect(quote.locator("time")).toHaveCount(0);
});

test("manual assumption edits invalidate research while view switches preserve the valuation editor", async ({ page }) => {
  const calls = await mockResearch(page);
  await (await openResearch(page)).click();
  await expect(page.getByLabel("MSFT research report", { exact: true })).toBeVisible();
  await page.getByRole("group", { name: "Company workspace view" }).getByRole("button", { name: "Valuation", exact: true }).click();
  await page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true }).fill("30");
  await expect(page.getByTestId("weighted-classification")).toHaveText("User-defined estimate");
  await page.getByRole("group", { name: "Company workspace view" }).getByRole("button", { name: "AI Research", exact: true }).click();
  await expect(page.getByLabel("MSFT research report", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Generate research report", exact: true }).click();
  await expect(page.getByLabel("MSFT research report", { exact: true })).toBeVisible();
  expect(calls.filter((call) => call.path.endsWith("/report")).at(-1).body.valuation.assumptions.target_pe).toBe(30);
  await page.getByRole("group", { name: "Company workspace view" }).getByRole("button", { name: "Valuation", exact: true }).click();
  await expect(page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true })).toHaveValue("30");
});

test("disabled AI and provider errors are clear and never substitute fabricated reports", async ({ page }) => {
  await mockResearch(page, { available: false });
  const generate = await openResearch(page);
  await expect(generate).toBeDisabled();
  await expect(page.locator("#ai-research")).toContainText("AI research is disabled");
  await expect(page.getByRole("textbox", { name: "Your question about MSFT", exact: true })).toBeDisabled();
  await expect(page.getByLabel("MSFT research report", { exact: true })).toHaveCount(0);
});

test("report and chat failures allow retry, preserve questions, and show loading states", async ({ page }) => {
  let reports = 0, chats = 0;
  await mockResearch(page, {
    reportHandler: async (route) => { reports += 1; if (reports !== 1) return false; await new Promise((resolve) => setTimeout(resolve, 400)); await route.fulfill({ status: 429, json: { error: { code: "ai_rate_limited", message: "Research usage limit reached. Please try again later." } } }); return true; },
    chatHandler: async (route) => { chats += 1; if (chats !== 1) return false; await route.fulfill({ status: 503, json: { error: { code: "ai_unavailable", message: "The research provider is temporarily unavailable." } } }); return true; },
  });
  const generate = await openResearch(page);
  await generate.click();
  await expect(page.getByRole("button", { name: "Generating research…", exact: true })).toBeDisabled();
  await expect(page.locator("#ai-research [role=alert]")).toContainText("Research usage limit reached");
  await expect(page.getByLabel("MSFT research report", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Generate research report", exact: true }).click();
  await expect(page.getByLabel("MSFT research report", { exact: true })).toBeVisible();
  const question = page.getByRole("textbox", { name: "Your question about MSFT", exact: true });
  await question.fill("Explain the available evidence.");
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  await expect(page.locator("#ai-research [role=alert]")).toContainText("temporarily unavailable");
  await expect(question).toHaveValue("Explain the available evidence.");
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  await expect(page.locator(".ai-turn")).toHaveCount(1);
});

for (const ticker of ["NVDA", "ORCL"]) test(`${ticker} research works with unavailable valuation and discloses missing evidence`, async ({ page }) => {
  await mockResearch(page, { unavailable: true });
  await (await openResearch(page, ticker)).click();
  const report = page.getByLabel(`${ticker} research report`, { exact: true });
  await expect(report).toBeVisible();
  await expect(report).toContainText("A defensible weighted intrinsic value is unavailable");
  await expect(report).toContainText("Financial evidence can still be reviewed");
});

test("Demo mode does not issue AI requests", async ({ page }) => {
  const calls = await mockResearch(page);
  await page.goto("/stocks/MSFT#ai-research");
  await expect(page.getByRole("heading", { name: /Microsoft/ })).toBeVisible();
  await expect(page.getByRole("group", { name: "Company workspace view" })).toHaveCount(0);
  expect(calls).toHaveLength(0);
});

test("changing company clears report and chat instead of carrying another company's research", async ({ page }) => {
  await mockResearch(page);
  await (await openResearch(page)).click();
  await expect(page.getByLabel("MSFT research report", { exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "Your question about MSFT", exact: true }).fill("Explain this company's evidence.");
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  await expect(page.locator(".ai-turn")).toHaveCount(1);
  const search = page.getByRole("combobox", { name: "Search by company or ticker", exact: true });
  await search.fill("AAPL");
  await search.press("Enter");
  await expect(page).toHaveURL(/\/stocks\/AAPL$/);
  await page.getByRole("group", { name: "Company workspace view" }).getByRole("button", { name: "AI Research", exact: true }).click();
  await expect(page.getByRole("heading", { name: "AI Research · AAPL", exact: true })).toBeVisible();
  await expect(page.getByLabel("MSFT research report", { exact: true })).toHaveCount(0);
  await expect(page.locator(".ai-turn")).toHaveCount(0);
  await expect(page.getByRole("textbox", { name: "Your question about AAPL", exact: true })).toHaveValue("");
});

test("a delayed report for prior assumptions cannot repopulate the updated research workspace", async ({ page }) => {
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  let first = true;
  const calls = await mockResearch(page, { reportHandler: async (route, call) => {
    if (!first) return false;
    first = false;
    await pending;
    await route.fulfill({ json: aiResearchFixture(call.ticker, { marker: "Stale prior-assumption finding" }) }).catch(() => {});
    return true;
  } });
  await (await openResearch(page)).click();
  await expect.poll(() => calls.filter((call) => call.path.endsWith("/report")).length).toBe(1);
  await page.getByRole("group", { name: "Company workspace view" }).getByRole("button", { name: "Valuation", exact: true }).click();
  await page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true }).fill("31");
  await expect(page.getByTestId("weighted-classification")).toHaveText("User-defined estimate");
  release();
  await page.getByRole("group", { name: "Company workspace view" }).getByRole("button", { name: "AI Research", exact: true }).click();
  await expect(page.getByRole("button", { name: "Generate research report", exact: true })).toBeEnabled();
  await expect(page.getByText("Stale prior-assumption finding", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("MSFT research report", { exact: true })).toHaveCount(0);
});

test("research availability failures offer a safe retry", async ({ page }) => {
  let checks = 0;
  await mockResearch(page, { statusHandler: async (route) => {
    checks += 1;
    if (checks !== 1) return false;
    await route.fulfill({ status: 503, json: { error: { code: "service_unavailable", message: "The research service is temporarily unavailable." } } });
    return true;
  } });
  await openResearch(page);
  await expect(page.locator("#ai-research [role=alert]")).toContainText("temporarily unavailable");
  await page.getByRole("button", { name: "Retry research status", exact: true }).click();
  await expect(page.getByRole("button", { name: "Generate research report", exact: true })).toBeEnabled();
});

test("a failed dashboard calculation preserves valid user assumptions in research requests", async ({ page }) => {
  const calls = await mockResearch(page, { valuationHandler: async (route, body) => {
    if (body.assumptions?.target_pe !== 31) return false;
    await route.fulfill({ status: 503, json: { error: { code: "valuation_unavailable", message: "The dashboard valuation request temporarily failed." } } });
    return true;
  } });
  await openResearch(page);
  await page.getByRole("group", { name: "Company workspace view" }).getByRole("button", { name: "Valuation", exact: true }).click();
  await page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true }).fill("31");
  await expect(page.getByText("The dashboard valuation request temporarily failed.", { exact: true })).toBeVisible();
  await page.getByRole("group", { name: "Company workspace view" }).getByRole("button", { name: "AI Research", exact: true }).click();
  await expect(page.locator("#ai-research")).toContainText("retry with your current valid assumptions");
  await page.getByRole("button", { name: "Generate research report", exact: true }).click();
  await expect(page.getByLabel("MSFT research report", { exact: true })).toBeVisible();
  expect(calls.find((call) => call.path.endsWith("/report")).body.valuation.assumptions.target_pe).toBe(31);
});
