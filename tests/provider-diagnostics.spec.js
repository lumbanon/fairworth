import { test, expect } from "@playwright/test";
import { providerFixture } from "./helpers/providerFixture.js";
import { providerDiagnosticsFixture } from "./helpers/providerDiagnosticsFixture.js";

async function diagnosticsApi(page, { ticker = "MSFT", mode = "multiple", price = 100, failOnMultiple = false, partial = false } = {}) {
  const financial = providerFixture(ticker);
  const requests = [];
  const unexpected = [];
  if (price == null) financial.profile.market = null;
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith("/api/")) {
      if (["127.0.0.1", "localhost"].includes(url.hostname)) return route.continue();
      unexpected.push(`${url.origin}${url.pathname}`);
      return route.abort();
    }
    if (url.pathname.includes("/ai/")) {
      if (!url.pathname.endsWith("/status")) unexpected.push("Unexpected AI generation request");
      return route.fulfill({ json: { enabled: false, configured: false, available: false, message: "AI disabled for deterministic diagnostics tests.", limitations: [] } });
    }
    if (url.pathname.includes("/valuation/")) {
      const request = route.request().method() === "POST" ? route.request().postDataJSON() : {};
      if (route.request().method() === "POST") requests.push(request);
      if (failOnMultiple && request.assumptions?.target_pe === 99) return route.fulfill({ status: 422, json: { error: { code: "invalid_assumptions", message: "The source basis no longer supports this calculation." } } });
      const json = providerDiagnosticsFixture(ticker, { request, mode, price });
      if (partial) for (const scenario of Object.values(json.scenarios)) {
        scenario.diagnostics = { data_quality: {}, coverage: {}, aggregation: {} };
        scenario.data_completeness = { groups: { available: [] }, fields: {} };
      }
      return route.fulfill({ json });
    }
    const json = url.pathname.endsWith("/financials") ? url.searchParams.get("period") === "quarterly" ? financial.quarterly : financial.annual
      : url.pathname.endsWith("/metrics") ? financial.metrics : url.pathname.endsWith("/data-status") ? financial.dataStatus : financial.profile;
    return route.fulfill({ json: json.company ? { ...json, company: { ...json.company, ticker } } : { ...json, ticker } });
  });
  await page.goto(`/stocks/${ticker}`);
  await page.getByRole("group", { name: "Financial data mode" }).getByRole("button", { name: "Provider data", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Valuation coverage & confidence", exact: true })).toBeVisible();
  return { requests, unexpected };
}

async function fitsViewport(page) {
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width + 1);
}

test("multiple models retain low confidence and show dated quotes, source quality, blockers and exact provenance", async ({ page }) => {
  const { unexpected } = await diagnosticsApi(page);
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$701.18");
  await expect(page.getByTestId("summary-upside")).toHaveText("-12.3%");
  await expect(page.getByTestId("valuation-model-coverage")).toHaveText("2 contributing · 2 method families");
  await expect(page.getByTestId("valuation-confidence")).toHaveText("low");
  await expect(page.getByTestId("valuation-data-quality")).toHaveText("limited");
  await expect(page.getByTestId("valuation-quote-observation")).toHaveText("Quote observed: Jan 15, 2026 · stale");
  const diagnostic = page.getByRole("region", { name: "Valuation coverage & confidence", exact: true });
  await expect(diagnostic).toContainText("$650.13 to $777.77");
  await expect(diagnostic).toContainText("not a calibrated confidence interval");
  await diagnostic.getByText("Excluded models and required inputs (9)", { exact: true }).click();
  await expect(diagnostic.locator(".provider-excluded-models")).toContainText("net borrowing, change nwc");
  await page.getByRole("button", { name: "Details for Forward P/E", exact: true }).click();
  await expect(page.locator("#details-pe")).toContainText("Related methods share a family weighting budget");
  await page.locator("#details-pe").getByText("Financial input paths (1)", { exact: true }).click();
  await expect(page.locator("#details-pe .provider-input-paths")).toContainText("Available: forward eps, target pe. Missing: None");
  await expect(page.locator("#details-pe")).not.toContainText("[object Object]");
  await page.locator("#details-pe").getByText("Main assumptions and sources", { exact: true }).click();
  await expect(page.locator("#details-pe .provider-model-assumptions")).toContainText("FMP + SEC EDGAR");
  const completeness = page.getByRole("region", { name: "Data completeness", exact: true });
  await completeness.getByText("Available inputs", { exact: true }).click();
  const revenue = completeness.locator(".provider-input-record").filter({ has: page.locator("summary > span").filter({ hasText: /^Revenue$/ }) });
  await revenue.locator(":scope > summary").click();
  await expect(revenue).toContainText("Exact stored value");
  await expect(revenue).toContainText("125000000.125 USD");
  await expect(revenue).toContainText("2025-01-01 to 2025-12-31");
  await expect(revenue.getByRole("link", { name: "Original source 1", exact: true })).toHaveAttribute("href", "https://www.sec.gov/Archives/edgar/data/1/fixture.htm");
  await revenue.getByText("Complete input and provenance record", { exact: true }).click();
  await expect(revenue.locator("pre")).toContainText("0000000000-26-000001");
  await fitsViewport(page);
  expect(unexpected).toEqual([]);
});

test("related methods share one family and disclose shared assumptions without raising confidence", async ({ page }) => {
  await diagnosticsApi(page, { ticker: "NVDA", mode: "correlated" });
  await expect(page.getByTestId("valuation-model-coverage")).toHaveText("2 contributing · 1 method family");
  await expect(page.getByTestId("valuation-confidence")).toHaveText("low");
  await page.getByText("Why this estimate has its confidence classification", { exact: true }).click();
  const diagnostic = page.getByRole("region", { name: "Valuation coverage & confidence", exact: true });
  await expect(diagnostic).toContainText("Shared assumptions");
  await expect(diagnostic).toContainText("forward eps: Forward P/E, PEG-Based Valuation");
  await expect(diagnostic).toContainText("they do not prove independence");
  await fitsViewport(page);
});

test("single-model and unavailable results keep honest coverage and never display unavailable models as zero", async ({ page }) => {
  await diagnosticsApi(page, { ticker: "AAPL", mode: "single" });
  await expect(page.getByTestId("valuation-model-coverage")).toHaveText("1 contributing · 1 method family");
  await expect(page.getByRole("region", { name: "Valuation coverage & confidence", exact: true })).toContainText("Model estimate range: Unavailable");
  await expect(page.getByTestId("valuation-confidence")).toHaveText("low");
  await expect(page.getByTestId("single-model-coverage-warning")).toContainText("Single-model estimate");
  await expect(page.getByTestId("single-model-coverage-warning")).toContainText("one contributing model");
  await expect(page.getByRole("row").filter({ has: page.getByRole("checkbox", { name: "Enable EV/Revenue", exact: true }) })).toContainText("—");
  await fitsViewport(page);
});

test("ORCL restricted price and no eligible models remain unavailable with expandable missing inputs", async ({ page }) => {
  const { unexpected } = await diagnosticsApi(page, { ticker: "ORCL", mode: "none", price: null });
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  await expect(page.getByTestId("summary-upside")).toHaveText("—");
  await expect(page.getByTestId("valuation-model-coverage")).toHaveText("0 contributing · 0 method families");
  await expect(page.getByTestId("valuation-confidence")).toHaveText("unavailable");
  await expect(page.getByTestId("valuation-quote-observation")).toHaveCount(0);
  const completeness = page.getByRole("region", { name: "Data completeness", exact: true });
  await completeness.getByText("Provider restrictions", { exact: true }).click();
  const price = completeness.locator(".provider-completeness-group[open] .provider-input-record");
  await price.locator(":scope > summary").click();
  await expect(price).toContainText("Provider endpoint restricted (HTTP 402)");
  await expect(price).toContainText("Observation date unavailable");
  await fitsViewport(page);
  expect(unexpected).toEqual([]);
});

test("user overrides and weights remain inspectable and reset independently from reported facts", async ({ page }) => {
  const { requests } = await diagnosticsApi(page);
  const multiple = page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true });
  await multiple.fill("30");
  await expect.poll(() => requests.at(-1)?.assumptions.target_pe).toBe(30);
  const completeness = page.getByRole("region", { name: "Data completeness", exact: true });
  await completeness.getByText("User overrides", { exact: true }).click();
  await expect(completeness.locator(".provider-completeness-group[open]")).toContainText("30×");
  await page.getByRole("spinbutton", { name: "Forward P/E raw weight", exact: true }).fill("80");
  await expect.poll(() => requests.at(-1)?.weights?.pe).toBe(80);
  await expect(page.locator(".provider-aggregation-summary")).toContainText("Weights: mixed");
  await page.getByRole("button", { name: "Reset Models & Weights", exact: true }).click();
  await expect(page.locator(".provider-aggregation-summary")).toContainText("Weights: default");
  await expect(multiple).toHaveValue("30");
  await page.getByRole("button", { name: "Reset Target Forward P/E", exact: true }).click();
  await expect(multiple).toHaveValue("22.5");
  await expect(completeness.locator(".provider-completeness-group[open]")).toContainText("No inputs in this group");
  await fitsViewport(page);
});

test("failed calculations remove previous completeness and confidence until valid inputs recover", async ({ page }) => {
  await diagnosticsApi(page, { failOnMultiple: true });
  await page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true }).fill("99");
  await expect(page.getByRole("alert")).toContainText("source basis no longer supports");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  await expect(page.getByRole("heading", { name: "Valuation coverage & confidence", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Data completeness", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Reset Target Forward P/E", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Data completeness", exact: true })).toBeVisible();
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$701.18");
});

test("partial additive diagnostics remain explicit and do not invent missing coverage or source records", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await diagnosticsApi(page, { partial: true });
  await expect(page.getByTestId("valuation-model-coverage")).toHaveText("Unavailable contributing · Unavailable method families");
  await expect(page.getByTestId("valuation-data-quality")).toHaveText("Unavailable");
  await expect(page.locator(".provider-aggregation-summary")).toContainText("Contributing models: Unavailable");
  const completeness = page.getByRole("region", { name: "Data completeness", exact: true });
  await expect(completeness.getByRole("heading", { name: "Financial basis and market comparison", exact: true })).toHaveCount(0);
  await expect(completeness.getByRole("region", { name: "Financial evidence by reporting period", exact: true })).toHaveCount(0);
  await completeness.getByText("Missing inputs", { exact: true }).click();
  await expect(completeness.locator(".provider-completeness-group[open]")).toContainText("This group was not supplied by the valuation service");
  await fitsViewport(page);
  expect(errors).toEqual([]);
});

test("blocked models retain multiple reasons and period evidence cannot manufacture a price target", async ({ page }) => {
  const { unexpected } = await diagnosticsApi(page, { ticker: "ORCL", mode: "none", price: null });
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  await expect(page.getByTestId("single-model-coverage-warning")).toHaveCount(0);
  const row = page.getByRole("row").filter({ has: page.getByRole("checkbox", { name: "Enable Discounted Cash Flow (FCFE)", exact: true }) });
  await row.getByText("2 blocking issues", { exact: true }).click();
  await expect(row).toContainText("required metric missing");
  await expect(row).toContainText("share basis unverified");
  await expect(row).toContainText("net borrowing, change nwc");
  await page.getByRole("button", { name: "Details for Discounted Cash Flow (FCFE)", exact: true }).click();
  await expect(page.locator("#details-fcfe .provider-blocker-list")).toContainText("verified current-share ownership basis");
  const completeness = page.getByRole("region", { name: "Data completeness", exact: true });
  const basis = completeness.locator(".provider-basis-grid");
  await expect(basis).toContainText("Selected-security share basis");
  await expect(basis).toContainText("Unverified");
  await expect(basis).toContainText("Reporting / trading currency");
  await expect(basis).toContainText("The quote endpoint is restricted; no market price was substituted.");
  const table = completeness.getByRole("region", { name: "Financial evidence by reporting period", exact: true });
  await expect(table.getByRole("row")).toHaveCount(3);
  const current = table.getByRole("row").filter({ hasText: "2025-01-01 to 2025-12-31" });
  await expect(current).toContainText("3 available");
  await expect(current).toContainText("2 missing");
  await current.getByText("View missing metrics", { exact: true }).click();
  await expect(current).toContainText("Interest expense");
  await current.getByText("2 source references", { exact: true }).click();
  await expect(current).toContainText("fixture:debt:2025");
  await expect(table).toContainText("2024-01-01 to 2024-12-31");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  await fitsViewport(page);
  expect(unexpected).toEqual([]);
});

test("quote observation freshness remains independent from financial snapshot retrieval", async ({ page }) => {
  await diagnosticsApi(page, { ticker: "MSFT", mode: "single" });
  const completeness = page.getByRole("region", { name: "Data completeness", exact: true });
  await expect(completeness).toContainText("Financial snapshot retrieved: 2026-10-14");
  const quote = completeness.locator(".provider-basis-grid > div").filter({ hasText: "Market-price freshness" });
  await expect(quote).toContainText("Stale observation");
  await expect(quote).toContainText("Observed: 2026-01-15T16:00:00Z");
  await expect(quote).toContainText("remains stale despite recent retrieval");
  await expect(page.getByTestId("valuation-quote-observation")).toContainText("Jan 15, 2026");
  await fitsViewport(page);
});
