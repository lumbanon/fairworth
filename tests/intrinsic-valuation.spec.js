import { test, expect } from "@playwright/test";
import { providerFixture } from "./helpers/providerFixture.js";
import { providerValuationFixture } from "./helpers/providerValuationFixture.js";

// Synthetic browser transport fixtures only; no financial calculation or live
// subscription is established by these display and request-isolation checks.
async function intrinsicApi(page, { estimate = true, imported = false, failDated = false, failDefaults = false, delayDefaults = false, defaultValue = 42.123456789 } = {}) {
  const fixture = providerFixture();
  fixture.profile.market = null;
  if (imported) fixture.annual.financial_import = { source_type: "approved_sec_financial_import", import_batch_id: "synthetic-import-batch", imported_at: "2026-10-22T10:00:00Z", original_retrieved_at: "2026-10-20T12:01:53Z", financial_owner_ticker: "MSFT", cik: "0000000001", source_sha256: "b".repeat(64) };
  const requests = [];
  const unexpected = [];
  let releaseDefaults;
  const defaultsGate = new Promise((resolve) => { releaseDefaults = resolve; });
  let pendingDefaults = 0;
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith("/api/")) {
      if (["127.0.0.1", "localhost"].includes(url.hostname)) return route.continue();
      unexpected.push(url.origin + url.pathname);
      return route.abort();
    }
    if (url.pathname.includes("/ai/")) return route.fulfill({ json: { enabled: false, available: false, configured: false, message: "AI disabled in offline intrinsic tests.", limitations: [] } });
    if (url.pathname.includes("/valuation/")) {
      const request = route.request().method() === "POST" ? route.request().postDataJSON() : {};
      if (route.request().method() === "POST") requests.push(request);
      if (delayDefaults && route.request().method() === "GET" && url.pathname.endsWith("/defaults")) {
        pendingDefaults += 1;
        await defaultsGate;
      }
      if (failDefaults && request.context !== "dated_intrinsic") return route.fulfill({ status: 503, json: { error: { code: "defaults_unavailable", message: "Automatic default inputs are unavailable." } } });
      if (failDated && request.context === "dated_intrinsic") return route.fulfill({ status: 422, json: { error: { code: "dated_evidence_unavailable", message: "No approved import matches the selected original evidence." } } });
      const response = providerValuationFixture("MSFT", { request, price: null });
      const value = request.context === "dated_intrinsic" ? 42.123456789 : defaultValue;
      response.enabled_models = ["dividend"];
      response.configured_weights = { dividend: 100 };
      for (const scenario of Object.values(response.scenarios)) {
        scenario.publication = { result_type: estimate ? "historical_illustration" : "unavailable", current_eligible: false, blockers: [{ code: "listing_verification_expired", message: "Current publication proof has expired." }], clocks: {} };
        const model = scenario.models.find((row) => row.id === "dividend");
        if (estimate) {
          Object.assign(model, { status: "valid", fair_value: value, classification: "user_defined", eligibility: { status: "eligible", required_inputs: ["dividend_per_share", "dividend_growth", "cost_of_equity"], missing_inputs: [], warnings: [] } });
          Object.assign(scenario.summary, { fair_value: value, count: 1, classification: "user_defined", upside: null, margin_of_safety: null });
        }
        scenario.intrinsic = { status: estimate ? "available" : "unavailable", value: estimate ? value : null, currency: "USD", model_ids: estimate ? ["dividend"] : [], classification: "user_defined", workflow: "user_assisted", financial_observation_date: "2026-06-30", calculated_at: "2026-10-22T10:00:00Z", forecast_horizon: { label: "Perpetual cash-dividend scenario from the dated annual base" }, assumptions: { dividend_growth: { value: 0.03, unit: "fraction", evidence_type: "user" }, cost_of_equity: { value: 0.10, unit: "fraction", evidence_type: "user" } }, source_identifiers: ["synthetic-sec-original-filing"], limitations: ["Cash-dividend-only scenario; buybacks are excluded."] };
        scenario.market_comparison = { status: "unavailable", price: null, current: false, reason: "No compatible observed quote is supplied in this dated scenario." };
      }
      return route.fulfill({ json: response });
    }
    if (url.pathname.endsWith("/coverage")) return route.fulfill({ json: { identity: fixture.profile.company, stages: { statements: { status: "available", reason: "Synthetic imported financial coverage." } } } });
    const json = url.pathname.endsWith("/financials") ? url.searchParams.get("period") === "quarterly" ? fixture.quarterly : fixture.annual : url.pathname.endsWith("/metrics") ? fixture.metrics : url.pathname.endsWith("/data-status") ? fixture.dataStatus : fixture.profile;
    return route.fulfill({ json });
  });
  await page.goto("/stocks/MSFT");
  await page.getByRole("group", { name: "Financial data mode" }).getByRole("button", { name: "Provider data", exact: true }).click();
  await expect(page.getByRole("heading", { name: "API Fixture Corporation (MSFT)", exact: true })).toBeVisible();
  return { requests, unexpected, releaseDefaults, pendingDefaults: () => pendingDefaults };
}

async function setDatedInputs(page) {
  const controls = page.getByTestId("dated-intrinsic-controls");
  await controls.locator(":scope > summary").click();
  await controls.getByLabel("Use dated intrinsic analysis").check();
  await controls.getByLabel("Evidence as-of timestamp").fill("2026-10-21T15:04:55Z");
  await controls.getByLabel("Dividend growth assumption (%)").fill("3");
  await controls.getByLabel("Required return assumption (%)").fill("10");
  await controls.getByLabel("Sustainable dividend assumption", { exact: true }).selectOption("true");
}

test("a dated user-assisted intrinsic estimate remains readable without a quote or invented upside", async ({ page }) => {
  const { unexpected } = await intrinsicApi(page);
  const panel = page.getByTestId("intrinsic-evidence");
  await expect(panel.getByRole("heading", { name: "User-assisted intrinsic estimate" })).toBeVisible();
  await expect(panel.getByTestId("intrinsic-estimate-value")).toHaveText("$42.12 per share");
  await expect(panel).toContainText("2026-06-30");
  await expect(panel).toContainText("2026-10-22T10:00:00Z");
  await expect(panel).toContainText("Perpetual cash-dividend scenario");
  await expect(panel.getByTestId("intrinsic-comparison-status")).toHaveText("Market comparison unavailable");
  await expect(page.getByTestId("summary-upside")).toHaveText("—");
  await panel.getByText("Intrinsic inputs, assumptions and source references", { exact: true }).click();
  await expect(panel).toContainText("User override");
  await expect(panel.locator("pre")).toContainText("42.123456789");
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width + 1);
  expect(unexpected).toEqual([]);
});

test("dated mode sends only the explicit dividend scenario and no manual comparison price", async ({ page }) => {
  const { requests, unexpected } = await intrinsicApi(page);
  await setDatedInputs(page);
  await expect.poll(() => requests.filter((row) => row.context === "dated_intrinsic").length).toBeGreaterThan(0);
  const request = requests.findLast((row) => row.context === "dated_intrinsic");
  expect(request.enabled_models).toEqual(["dividend"]);
  expect(request.evidence_as_of).toBe("2026-10-21T15:04:55Z");
  expect(request.assumptions).toEqual({ dividend_growth: 0.03, cost_of_equity: 0.1, stable_dividend_confirmed: true });
  expect(request.manual_market_price).toBeNull();
  await expect(page.getByLabel("User-provided market price", { exact: false })).toBeDisabled();
  expect(unexpected).toEqual([]);
});

test("imported financial evidence shows the original retrieval date separately from the batch date", async ({ page }) => {
  const { unexpected } = await intrinsicApi(page, { imported: true });
  const record = page.getByTestId("financial-import-evidence");
  await record.locator(":scope > summary").click();
  await expect(record).toContainText("synthetic-import-batch");
  await expect(record).toContainText("2026-10-20T12:01:53Z");
  await expect(record).toContainText("2026-10-22T10:00:00Z");
  await expect(record).toContainText("Import time does not refresh");
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width + 1);
  expect(unexpected).toEqual([]);
});

test("IBKR remains visibly optional and disconnected from the public website", async ({ page }) => {
  const { unexpected } = await intrinsicApi(page);
  const status = page.getByTestId("ibkr-personal-use-status");
  await status.locator(":scope > summary").click();
  await expect(status).toContainText("IBKR is not connected through this website");
  await expect(status).toContainText("applicable non-display permissions");
  await expect(status).toContainText("Public mode does not publish IBKR data");
  expect(unexpected).toEqual([]);
});

test("a rejected dated request hides the previous estimate instead of publishing it", async ({ page }) => {
  await intrinsicApi(page, { failDated: true });
  await expect(page.getByTestId("intrinsic-estimate-value")).toBeVisible();
  await setDatedInputs(page);
  await expect(page.getByRole("alert")).toContainText("No approved import matches");
  await expect(page.getByTestId("intrinsic-estimate-value")).toHaveCount(0);
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
});

test("user-assisted dated analysis remains usable when automatic defaults are unavailable", async ({ page }) => {
  const { requests, unexpected } = await intrinsicApi(page, { failDefaults: true });
  await expect(page.getByText("Automatic default inputs are unavailable.", { exact: true })).toBeVisible();
  await setDatedInputs(page);
  await expect(page.getByTestId("intrinsic-estimate-value")).toHaveText("$42.12 per share");
  expect(requests.some((request) => request.context === "dated_intrinsic")).toBe(true);
  expect(unexpected).toEqual([]);
});

for (const failDefaults of [false, true]) {
  test(`a late automatic default ${failDefaults ? "failure" : "response"} cannot replace the dated result`, async ({ page }) => {
    const api = await intrinsicApi(page, { delayDefaults: true, failDefaults, defaultValue: 271.8281828 });
    await expect.poll(api.pendingDefaults).toBeGreaterThan(0);
    await setDatedInputs(page);
    await expect(page.getByTestId("intrinsic-estimate-value")).toHaveText("$42.12 per share");
    const datedRequests = api.requests.filter((row) => row.context === "dated_intrinsic").length;
    expect(datedRequests).toBeGreaterThan(0);
    api.releaseDefaults();
    await page.waitForLoadState("networkidle");
    await expect(page.getByTestId("intrinsic-estimate-value")).toHaveText("$42.12 per share");
    await expect(page.getByLabel("Use dated intrinsic analysis")).toBeChecked();
    await expect(page.getByTestId("weighted-fair-value")).toHaveText("$42.12");
    await expect(page.getByText("Automatic default inputs are unavailable.", { exact: true })).toHaveCount(0);
    expect(api.requests.filter((row) => row.context !== "dated_intrinsic")).toEqual([]);
    expect(api.requests.filter((row) => row.context === "dated_intrinsic")).toHaveLength(datedRequests);
    expect(api.unexpected).toEqual([]);
  });
}
