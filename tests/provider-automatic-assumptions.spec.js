import { test, expect } from "@playwright/test";
import { providerFixture } from "./helpers/providerFixture.js";
import { automaticProviderValuationFixture } from "./helpers/providerValuationFixture.js";

async function automaticApi(page, { price = 100, respond } = {}) {
  const financial = providerFixture();
  if (price === null) financial.profile.market = null;
  const requests = [];
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const ticker = url.pathname.split("/")[3];
    if (url.pathname.includes("/valuation/")) {
      const request = route.request().method() === "POST" ? route.request().postDataJSON() : {};
      if (route.request().method() === "POST") requests.push(request);
      const custom = respond ? await respond({ request, route, url }) : null;
      if (custom?.handled) return;
      return route.fulfill({ json: custom?.json ?? automaticProviderValuationFixture(ticker, {
        request, price, sensitivityValue: request.assumptions?.earnings_growth === 0.12 ? 456.78 : 432.1,
      }) });
    }
    const json = url.pathname.endsWith("/financials") ? url.searchParams.get("period") === "quarterly" ? financial.quarterly : financial.annual
      : url.pathname.endsWith("/metrics") ? financial.metrics : url.pathname.endsWith("/data-status") ? financial.dataStatus : financial.profile;
    return route.fulfill({ json: json.company ? { ...json, company: { ...json.company, ticker } } : { ...json, ticker } });
  });
  return requests;
}

async function openProvider(page, ticker = "MSFT") {
  await page.goto(`/stocks/${ticker}`);
  await page.getByRole("group", { name: "Financial data mode" }).getByRole("button", { name: "Provider data", exact: true }).click();
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$777.77");
}

test("automatic defaults show sources, dates, formulas and single-model classification without editing", async ({ page }) => {
  const requests = await automaticApi(page);
  await openProvider(page);
  await expect(page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true })).toHaveValue("22.5");
  await expect(page.getByRole("spinbutton", { name: "Forward EPS", exact: true })).toHaveValue("10.8");
  await expect(page.getByRole("spinbutton", { name: "EPS growth", exact: true })).toHaveValue("8");
  await expect(page.getByTestId("weighted-classification")).toHaveText("Evidence-supported estimate");
  await expect(page.getByRole("alert")).toContainText("Single-model estimate");
  await expect(page.getByLabel("Weighted estimate composition")).toContainText("100.0% (pe)");
  const source = page.locator("#provider-assumption-help-target_pe");
  await expect(source).toContainText("FMP + SEC EDGAR");
  await expect(source).toContainText("2026-01-15");
  await expect(source).toContainText("2021-12-31 to 2025-12-31");
  await expect(source).toContainText("Median of valid, filing-date-aligned historical P/E observations");
  await expect(source).toContainText("Historical multiples are evidence");
  await expect.poll(() => requests.length).toBeGreaterThan(0);
  expect(requests[0].assumptions).toEqual({});
  await page.getByText("All assumption sources and methods", { exact: true }).click();
  const beta = page.locator(".provider-assumption-record").filter({ has: page.getByRole("heading", { name: "beta", exact: true }) });
  await expect(beta).toContainText("Read-only sourced input");
  await expect(beta).toContainText("Source quality: moderate");
  const claim = page.locator(".provider-assumption-record").filter({ has: page.getByRole("heading", { name: "Preferred equity claim", exact: true }) });
  await expect(claim).toContainText("verified zero");
  await expect(claim).toContainText("Reported or observed fact");
  const policy = page.locator(".provider-assumption-record").filter({ has: page.getByRole("heading", { name: "Cost of equity", exact: true }) });
  await expect(policy).toContainText("Modeling policy");
  await expect(policy).toContainText("No dated observation");
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width + 1);
});

test("automatic forecasts update with user growth, while individual resets restore suggested sources and sensitivity", async ({ page }) => {
  const requests = await automaticApi(page);
  await openProvider(page);
  const growth = page.getByRole("spinbutton", { name: "EPS growth", exact: true });
  const eps = page.getByRole("spinbutton", { name: "Forward EPS", exact: true });
  const multiple = page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true });
  await growth.fill("12");
  await expect(eps).toHaveValue("12.34");
  await expect(page.getByTestId("sensitivity-current")).toHaveText("$456.78");
  await expect(page.getByTestId("weighted-classification")).toHaveText("User-defined estimate");
  await multiple.fill("30");
  await expect.poll(() => requests.at(-1)?.assumptions.target_pe).toBe(30);
  await expect(page.locator("#provider-assumption-help-target_pe")).toContainText("User override");
  await page.getByRole("button", { name: "Reset Target Forward P/E", exact: true }).click();
  await expect(multiple).toHaveValue("22.5");
  await expect.poll(() => Object.hasOwn(requests.at(-1).assumptions, "target_pe")).toBe(false);
  await expect(growth).toHaveValue("12");
  await page.getByRole("button", { name: "Reset EPS growth", exact: true }).click();
  await expect(growth).toHaveValue("8");
  await expect(eps).toHaveValue("10.8");
  await expect(page.getByTestId("weighted-classification")).toHaveText("Evidence-supported estimate");
  await expect(page.getByTestId("sensitivity-current")).toHaveText("$432.10");
  await expect.poll(() => requests.at(-1)?.assumptions).toEqual({});
});

test("scenario-specific edits and model-weight resets preserve automatic defaults", async ({ page }) => {
  const requests = await automaticApi(page);
  await openProvider(page);
  const scenario = page.getByRole("group", { name: "Active valuation scenario" });
  await scenario.getByRole("button", { name: "Bear", exact: true }).click();
  await page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true }).fill("18");
  await expect.poll(() => requests.at(-1)?.scenario_overrides.bear.target_pe).toBe(18);
  await expect(page.getByTestId("weighted-classification")).toHaveText("User-defined estimate");
  await scenario.getByRole("button", { name: "Base", exact: true }).click();
  await expect(page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true })).toHaveValue("22.5");
  await expect(page.getByTestId("weighted-classification")).toHaveText("Evidence-supported estimate");
  await page.getByRole("spinbutton", { name: "Forward P/E raw weight", exact: true }).fill("0");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  await expect(page.getByTestId("weighted-classification")).toHaveText("Unavailable");
  await page.getByRole("button", { name: "Reset Models & Weights", exact: true }).click();
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$777.77");
  await expect.poll(() => requests.at(-1)?.scenario_overrides.bear.target_pe).toBe(18);
  await scenario.getByRole("button", { name: "Bear", exact: true }).click();
  await page.getByRole("button", { name: "Reset to Default", exact: true }).click();
  await expect(page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true })).toHaveValue("22.5");
  await expect.poll(() => requests.at(-1)?.scenario_overrides.bear).toEqual({});
});

test("missing inputs expose an edit action without silently enabling an unsupported model", async ({ page }) => {
  await automaticApi(page);
  await openProvider(page);
  await page.getByRole("button", { name: "Details for EV/Revenue", exact: true }).click();
  await expect(page.locator("#details-evRevenue")).toContainText("Missing inputs");
  await page.locator("#details-evRevenue").getByRole("button", { name: "Edit Assumptions", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Valuation method", exact: true })).toHaveValue("evRevenue");
  await expect(page.locator("#assumptions p").filter({ hasText: "Required next inputs:" })).toContainText("supported financial inputs");
  await expect(page.getByRole("checkbox", { name: "Enable EV/Revenue", exact: true })).toBeDisabled();
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$777.77");
});

test("inherited base edits have a working reset only in their own scenario and revenue arrays remain explicit", async ({ page }) => {
  const requests = await automaticApi(page);
  await openProvider(page);
  const scenario = page.getByRole("group", { name: "Active valuation scenario" });
  const multiple = page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true });
  await multiple.fill("30");
  await expect.poll(() => requests.at(-1)?.assumptions.target_pe).toBe(30);
  await scenario.getByRole("button", { name: "Bear", exact: true }).click();
  await expect(multiple).toHaveValue("30");
  await expect(page.getByRole("button", { name: "Reset Target Forward P/E", exact: true })).toHaveCount(0);
  await expect(page.getByText(/Inherited from the primary base assumption/)).toBeVisible();
  await multiple.fill("18");
  await expect.poll(() => requests.at(-1)?.scenario_overrides.bear.target_pe).toBe(18);
  await page.getByRole("button", { name: "Reset Target Forward P/E", exact: true }).click();
  await expect(multiple).toHaveValue("30");
  await expect.poll(() => requests.at(-1)?.scenario_overrides.bear).toEqual({});
  await scenario.getByRole("button", { name: "Base", exact: true }).click();
  await page.getByRole("button", { name: "Reset Target Forward P/E", exact: true }).click();
  await expect(multiple).toHaveValue("22.5");
  await page.getByText("Advanced assumptions and missing-input confirmations", { exact: true }).click();
  const revenue = page.getByRole("textbox", { name: "Annual projected revenue", exact: true });
  await expect(revenue).toHaveValue("");
  expect(Object.hasOwn(requests.at(-1).assumptions, "projected_revenue")).toBe(false);
  await revenue.fill("100, 0, 120");
  await expect(page.getByRole("alert")).toContainText("positive annual amounts");
  await revenue.fill("100, 110, 120");
  await expect.poll(() => requests.at(-1)?.assumptions.projected_revenue).toEqual([100, 110, 120]);
  await page.getByRole("button", { name: "Reset Annual projected revenue", exact: true }).click();
  await expect(revenue).toHaveValue("");
  await expect.poll(() => Object.hasOwn(requests.at(-1).assumptions, "projected_revenue")).toBe(false);
});

test("ORCL automatic intrinsic estimate keeps restricted quote absent and manual comparison separate", async ({ page }) => {
  const requests = await automaticApi(page, { price: null });
  await openProvider(page, "ORCL");
  await expect(page.getByTestId("summary-upside")).toHaveText("—");
  await expect(page.locator(".research-price strong")).toHaveText("—");
  await page.getByRole("spinbutton", { name: "User-provided market price", exact: true }).fill("180");
  await expect(page.locator(".research-chart-key")).toContainText("User-provided market price: $180.00");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$777.77");
  await expect(page.getByTestId("weighted-classification")).toHaveText("Evidence-supported estimate");
  await expect(page.locator(".research-price strong")).toHaveText("—");
  await expect.poll(() => requests.at(-1)?.manual_market_price).toEqual({ value: 180, currency: "USD" });
  await page.getByRole("button", { name: "Reset comparison price", exact: true }).click();
  await expect(page.getByTestId("summary-upside")).toHaveText("—");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$777.77");
});

test("automatic valuation request errors hide stale value and stale classification until recovery", async ({ page }) => {
  await automaticApi(page, { respond: async ({ request, route }) => {
    if (request.assumptions?.target_pe === 99) {
      await route.fulfill({ status: 422, json: { error: { code: "invalid_assumptions", message: "The selected automatic multiple is no longer supportable." } } });
      return { handled: true };
    }
  } });
  await openProvider(page);
  await page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true }).fill("99");
  await expect(page.getByRole("alert")).toContainText("no longer supportable");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  await expect(page.getByTestId("weighted-classification")).toHaveText("Unavailable");
  await page.getByRole("button", { name: "Reset Target Forward P/E", exact: true }).click();
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$777.77");
  await expect(page.getByTestId("weighted-classification")).toHaveText("Evidence-supported estimate");
});
