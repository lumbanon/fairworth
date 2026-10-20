import { test, expect } from "@playwright/test";
import { providerFixture } from "./helpers/providerFixture.js";
import { providerValuationFixture } from "./helpers/providerValuationFixture.js";

async function providerApi(page, { price = 100, respond } = {}) {
  const fixture = providerFixture();
  if (price === null) fixture.profile.market = null;
  const requests = [];
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const ticker = url.pathname.split("/")[3];
    if (url.pathname.includes("/valuation/")) {
      const request = route.request().method() === "POST" ? route.request().postDataJSON() : {};
      if (route.request().method() === "POST") requests.push(request);
      const custom = respond ? await respond({ request, route, url }) : null;
      if (custom?.handled) return;
      return route.fulfill({ json: custom?.json ?? providerValuationFixture(ticker, { request, price, forceActive: true, fairValue: 777.77 }) });
    }
    const json = url.pathname.endsWith("/financials") ? url.searchParams.get("period") === "quarterly" ? fixture.quarterly : fixture.annual
      : url.pathname.endsWith("/metrics") ? fixture.metrics : url.pathname.endsWith("/data-status") ? fixture.dataStatus : fixture.profile;
    return route.fulfill({ json: json.company ? { ...json, company: { ...json.company, ticker } } : { ...json, ticker } });
  });
  return requests;
}

async function openProvider(page, ticker = "MSFT") {
  await page.goto(`/stocks/${ticker}`);
  await page.getByRole("group", { name: "Financial data mode" }).getByRole("button", { name: "Provider data", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Python valuation engine", exact: true })).toBeVisible();
}

test("Provider values, scenario outputs, table comparisons and sensitivity use Python responses", async ({ page }) => {
  const requests = await providerApi(page);
  await openProvider(page);
  await page.getByRole("spinbutton", { name: "EPS growth", exact: true }).fill("10");
  await page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true }).fill("15");
  // Demo arithmetic for these fixture facts would be $165; Python intentionally
  // returns $777.77 to make independent browser calculation detectable.
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$777.77");
  await expect(page.getByTestId("summary-upside")).toHaveText("+65.0%");
  await expect(page.getByRole("row").filter({ has: page.getByRole("checkbox", { name: "Enable Forward P/E", exact: true }) })).toContainText("+37.3%");
  await expect(page.getByTestId("sensitivity-current")).toHaveText("$432.10");
  await expect(page.getByRole("button", { name: "Select bear scenario" })).toContainText("$145.00");
  await expect(page.getByRole("button", { name: "Select bull scenario" })).toContainText("$195.00");
  await expect(page.getByText(/calculated by Python/)).toBeVisible();
  await expect.poll(() => requests.some((request) => request.assumptions.earnings_growth === 0.1 && request.assumptions.target_pe === 15)).toBe(true);
  await page.getByRole("button", { name: "Reset Target Forward P/E", exact: true }).click();
  await expect(page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true })).toHaveValue("");
  await expect.poll(() => Object.hasOwn(requests.at(-1).assumptions, "target_pe")).toBe(false);
  await expect(page.getByRole("spinbutton", { name: "EPS growth", exact: true })).toHaveValue("10");
});

test("ORCL manual comparison price is removable, distinct from official quote, and validates positive input", async ({ page }) => {
  const requests = await providerApi(page, { price: null });
  await openProvider(page, "ORCL");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$777.77");
  await expect(page.getByTestId("summary-upside")).toHaveText("—");
  await expect(page.locator(".research-price strong")).toHaveText("—");
  await expect(page.locator(".research-model-chart .recharts-reference-line")).toHaveCount(1);
  await expect(page.locator(".research-model-chart .recharts-bar-rectangle path").first()).toHaveAttribute("fill", "#525252");
  const manual = page.getByRole("spinbutton", { name: "User-provided market price", exact: true });
  await manual.fill("180");
  await expect(page.locator(".research-chart-key")).toContainText("User-provided market price: $180.00");
  await expect(page.locator(".research-model-chart .recharts-reference-line")).toHaveCount(2);
  await expect(page.locator(".research-price strong")).toHaveText("—");
  await expect.poll(() => requests.at(-1)?.manual_market_price).toEqual({ value: 180, currency: "USD" });
  await manual.fill("0");
  await expect(page.getByRole("alert")).toContainText("positive and finite");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  await page.getByRole("button", { name: "Reset comparison price", exact: true }).click();
  await expect(manual).toHaveValue("");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$777.77");
  await expect(page.getByTestId("summary-upside")).toHaveText("—");
  await expect.poll(() => requests.at(-1)?.manual_market_price).toBe(null);
});

test("valuation API errors hide stale estimates and never substitute Demo calculations", async ({ page }) => {
  await providerApi(page, { respond: async ({ request, route }) => {
    if (request.assumptions?.target_pe === 99) {
      await route.fulfill({ status: 422, json: { error: { code: "invalid_assumptions", message: "This valuation assumption is unavailable for the requested model." } } });
      return { handled: true };
    }
  } });
  await openProvider(page);
  const multiple = page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true });
  await multiple.fill("99");
  await expect(page.getByRole("alert")).toContainText("valuation assumption is unavailable");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  await expect(page.getByText("Demo financial data — not live market information.")).toHaveCount(0);
  await multiple.fill("15");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$777.77");
});

test("debounced requests and cancellation prevent slower earlier responses overwriting current assumptions", async ({ page }) => {
  const requests = await providerApi(page, { respond: async ({ request, url }) => {
    const multiple = request.assumptions?.target_pe;
    if (multiple === 16) await new Promise((resolve) => setTimeout(resolve, 850));
    if (multiple === 17) return { json: providerValuationFixture(url.pathname.split("/")[3], { request, forceActive: true, fairValue: 888.88 }) };
    if (multiple === 16) return { json: providerValuationFixture(url.pathname.split("/")[3], { request, forceActive: true, fairValue: 111.11 }) };
  } });
  await openProvider(page);
  const multiple = page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true });
  await multiple.fill("16");
  await expect.poll(() => requests.some((request) => request.assumptions.target_pe === 16)).toBe(true);
  await multiple.fill("17");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$888.88");
  await page.waitForTimeout(1000);
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$888.88");
  const count = requests.length;
  await multiple.fill("18");
  await multiple.fill("19");
  await multiple.fill("20");
  await expect.poll(() => requests.at(-1).assumptions.target_pe).toBe(20);
  expect(requests.slice(count).filter((request) => [18, 19, 20].includes(request.assumptions.target_pe))).toHaveLength(1);
});

test("scenario edits remain independent and expanded advanced controls fit desktop and mobile", async ({ page }) => {
  const requests = await providerApi(page);
  await openProvider(page);
  await page.getByRole("group", { name: "Active valuation scenario" }).getByRole("button", { name: "Bear", exact: true }).click();
  await page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true }).fill("12");
  await expect.poll(() => requests.at(-1)?.scenario_overrides.bear.target_pe).toBe(12);
  await page.getByRole("group", { name: "Active valuation scenario" }).getByRole("button", { name: "Base", exact: true }).click();
  await expect(page.getByRole("spinbutton", { name: "Target Forward P/E", exact: true })).toHaveValue("");
  await page.getByText("Advanced assumptions and missing-input confirmations", { exact: true }).click();
  await expect(page.getByRole("spinbutton", { name: "Valuation shares", exact: true })).toHaveValue("12000000");
  await page.getByRole("combobox", { name: "Ticker share basis verified", exact: true }).selectOption("true");
  await expect.poll(() => requests.at(-1)?.assumptions.share_basis_confirmed).toBe(true);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width + 1);
});

test("negative Python equity estimates remain visible rather than being clipped to zero", async ({ page }) => {
  await providerApi(page, { respond: async ({ request, url }) => {
    const json = providerValuationFixture(url.pathname.split("/")[3], { request, forceActive: true, fairValue: -45.25 });
    json.scenarios.base.summary.margin_of_safety = null;
    return { json };
  } });
  await openProvider(page);
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("-$45.25");
  await expect(page.locator(".comparison-value-label")).toHaveText("-$45.25");
  await expect(page.locator(".research-model-chart .recharts-bar-rectangle path").first()).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width + 1);
});
