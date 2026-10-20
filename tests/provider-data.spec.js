import { test, expect } from "@playwright/test";
import { providerFixture } from "./helpers/providerFixture.js";
import { providerValuationFixture } from "./helpers/providerValuationFixture.js";

async function mockApi(
  page,
  fixture = providerFixture(),
  { delay = 0, errorStatus = 0, searchStatus = "fresh" } = {},
) {
  await page.route("**/api/**", async (route) => {
    if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
    if (errorStatus)
      return route.fulfill({
        status: errorStatus,
        json: {
          error: {
            code: "provider_unavailable",
            message: "The SEC provider is unavailable for this request.",
          },
        },
      });
    const url = new URL(route.request().url());
    if (url.pathname.includes("/valuation/")) {
      const ticker = url.pathname.split("/")[3];
      const request = route.request().method() === "POST" ? route.request().postDataJSON() : {};
      return route.fulfill({ json: providerValuationFixture(ticker, {
        request,
        price: fixture.profile.market?.price ?? null,
        missingShares: fixture.annual.periods[0].metrics.weighted_average_diluted_shares == null,
      }) });
    }
    let json = fixture.profile;
    if (url.pathname.endsWith("/search"))
      json = {
        results: [
          {
            ticker: "ACME",
            name: "API Fixture Corporation",
            cik: "0000000001",
            exchange: "NASDAQ",
          },
        ],
        status: searchStatus,
        warnings:
          searchStatus === "stale"
            ? [
                {
                  field: "company_directory",
                  code: "cached_directory",
                  message:
                    "Cached directory results are shown because the provider is unavailable.",
                },
              ]
            : [],
      };
    else if (url.pathname.endsWith("/financials"))
      json =
        url.searchParams.get("period") === "quarterly"
          ? fixture.quarterly
          : fixture.annual;
    else if (url.pathname.endsWith("/metrics")) json = fixture.metrics;
    else if (url.pathname.endsWith("/data-status")) json = fixture.dataStatus;
    if (!url.pathname.endsWith("/search")) {
      const ticker = url.pathname.split("/")[3];
      json = json.company
        ? { ...json, company: { ...json.company, ticker } }
        : { ...json, ticker };
    }
    return route.fulfill({ json });
  });
}

async function chooseProvider(page) {
  await page.goto("/dashboard");
  await page
    .getByRole("group", { name: "Financial data mode" })
    .getByRole("button", { name: "Provider data", exact: true })
    .click();
}

test("provider mode shows loading, reported financials, source timestamps and quarterly periods", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await mockApi(page, providerFixture(), { delay: 500 });
  await chooseProvider(page);
  await expect(
    page.getByRole("heading", { name: "Loading MSFT financial data…" }),
  ).toBeVisible();
  await expect(
    page.getByText("Demo financial data — not live market information."),
  ).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "API Fixture Corporation (MSFT)" }),
  ).toBeVisible();
  await expect(
    page.getByText("2026-01-15T16:00:00Z", { exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  await expect(
    page.getByRole("row", { name: /^Revenue \$1.4B$/ }),
  ).toBeVisible();
  await page.locator(".research-quality-notice").filter({ has: page.getByRole("heading", { name: "Data quality & sources", exact: true }) }).locator(".research-source-notices > summary").click();
  await expect(
    page.locator(".research-notice-groups > li > p").filter({ hasText: /configured market price is stale/ }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Cash Flow Statement", exact: true })
    .click();
  await expect(
    page.getByRole("row", { name: /^Free cash flow \$100M$/ }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Income Statement", exact: true })
    .click();
  await page
    .getByRole("group", { name: "Reporting period" })
    .getByRole("button", { name: "Quarterly" })
    .click();
  await expect(
    page.getByRole("columnheader", { name: /Q1 2025/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("row", { name: /^Diluted EPS \$2.50$/ }),
  ).toBeVisible();
  await page
    .getByRole("group", { name: "Reporting period" })
    .getByRole("button", { name: "Annual" })
    .click();
  await page.locator(".research-financial-provenance summary").click();
  await expect(page.getByText(/0000000001-26-000001/)).toBeVisible();
  expect(errors).toEqual([]);
});

test("explicit user assumptions and weights calculate only compatible provider models and remain separate from demo", async ({
  page,
}) => {
  await mockApi(page);
  await chooseProvider(page);
  const growth = page.getByRole("spinbutton", {
    name: "EPS growth",
    exact: true,
  });
  const multiple = page.getByRole("spinbutton", {
    name: "Target Forward P/E",
    exact: true,
  });
  await expect(growth).toHaveValue("");
  await expect(multiple).toHaveValue("");
  await expect(
    page.getByRole("checkbox", {
      name: "Enable Discounted Cash Flow (FCFF)",
      exact: true,
    }),
  ).toBeDisabled();
  await growth.fill("10");
  await multiple.fill("15");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$165.00");
  await expect(page.getByTestId("summary-upside")).toHaveText("+65.0%");
  await expect(
    page.locator(".research-model-chart .recharts-surface"),
  ).toBeVisible();
  await page
    .getByRole("spinbutton", { name: "Forward P/E raw weight", exact: true })
    .fill("0");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  await page
    .getByRole("button", { name: "Reset Models & Weights", exact: true })
    .click();
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$165.00");
  const scenarios = page.getByRole("group", {
    name: "Active valuation scenario",
  });
  await scenarios.getByRole("button", { name: "Bear", exact: true }).click();
  await expect(growth).toHaveValue("");
  await scenarios.getByRole("button", { name: "Base", exact: true }).click();
  await expect(growth).toHaveValue("10");
  await page
    .getByRole("button", { name: "Reset to Default", exact: true })
    .click();
  await expect(growth).toHaveValue("");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  await page
    .getByRole("group", { name: "Financial data mode" })
    .getByRole("button", { name: "Demonstration", exact: true })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Microsoft Corporation",
  );
  await expect(
    page.getByText("Demo financial data — not live market information."),
  ).toBeVisible();
  await expect(page.getByTestId("weighted-fair-value")).not.toHaveText("—");
});

test("provider request errors never silently substitute demonstration data", async ({
  page,
}) => {
  await mockApi(page, providerFixture(), { errorStatus: 503 });
  await chooseProvider(page);
  await expect(
    page.getByRole("heading", { name: "Unable to load MSFT provider data." }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toContainText(
    "SEC provider is unavailable",
  );
  await expect(
    page.getByText("Demo financial data — not live market information."),
  ).toHaveCount(0);
  await expect(page.getByTestId("weighted-fair-value")).toHaveCount(0);
  await page.getByRole("button", { name: "Retry provider request" }).click();
  await expect(
    page.getByRole("heading", { name: "Unable to load MSFT provider data." }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Use demonstration data", exact: true })
    .click();
  await expect(
    page.getByText("Demo financial data — not live market information."),
  ).toBeVisible();
});

test("missing provider price preserves fair value but excludes market comparisons and its reference line", async ({
  page,
}) => {
  const fixture = providerFixture();
  fixture.profile.market = null;
  fixture.dataStatus.provider_status.market = {
    provider: "disabled",
    status: "unavailable",
  };
  await mockApi(page, fixture);
  await chooseProvider(page);
  await page
    .getByRole("spinbutton", { name: "EPS growth", exact: true })
    .fill("10");
  await page
    .getByRole("spinbutton", { name: "Target Forward P/E", exact: true })
    .fill("15");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$165.00");
  await expect(page.getByTestId("summary-upside")).toHaveText("—");
  await expect(page.locator(".research-price strong")).toHaveText("—");
  await expect(
    page.locator(".research-model-chart .recharts-reference-line"),
  ).toHaveCount(1);
  await expect(
    page.getByText("Market provider price unavailable", { exact: true }),
  ).toBeVisible();
});

test("missing shares and incompatible earnings disable formulas without fabricated defaults", async ({
  page,
}) => {
  const fixture = providerFixture();
  fixture.annual.periods[0].metrics.weighted_average_diluted_shares = null;
  fixture.quarterly.periods = [];
  await mockApi(page, fixture);
  await chooseProvider(page);
  await expect(
    page.getByRole("heading", { name: "API Fixture Corporation (MSFT)" }),
  ).toBeVisible();
  await expect(
    page.getByRole("row").filter({ hasText: "Forward P/E" }).first(),
  ).toContainText("Insufficient data");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  await expect(
    page.getByRole("button", { name: "Quarterly", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText(/same-period net income, diluted weighted share count/).first(),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Details for Forward P/E", exact: true })
    .click();
  await expect(page.locator(".model-details")).toContainText(
    "same-period net income, diluted weighted share count",
  );
});

test("provider-backed global search uses API directory results and preserves the selected mode", async ({
  page,
}) => {
  await mockApi(page);
  await chooseProvider(page);
  await expect(
    page.getByRole("heading", { name: "API Fixture Corporation (MSFT)" }),
  ).toBeVisible();
  const search = page.getByRole("combobox", {
    name: "Search by company or ticker",
    exact: true,
  });
  await search.fill("ACME");
  await expect(
    page.getByRole("listbox", { name: "Provider stock suggestions" }),
  ).toBeVisible();
  await page
    .getByRole("option", { name: /ACME API Fixture Corporation/ })
    .click();
  await expect(page).toHaveURL(/\/stocks\/ACME$/);
  await expect(
    page.getByRole("heading", { name: "API Fixture Corporation (ACME)" }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("group", { name: "Financial data mode" })
      .getByRole("button", { name: "Provider data", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
});

test("stale provider search suggestions disclose their directory status and source warning", async ({
  page,
}) => {
  await mockApi(page, providerFixture(), { searchStatus: "stale" });
  await chooseProvider(page);
  await expect(
    page.getByRole("heading", { name: "API Fixture Corporation (MSFT)" }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Search by company or ticker", exact: true })
    .fill("ACME");
  await expect(
    page.getByRole("listbox", { name: "Provider stock suggestions" }),
  ).toBeVisible();
  await expect(page.locator(".search-help[role=status]")).toContainText(
    "Company directory status: stale.",
  );
  await expect(page.locator(".search-help[role=status]")).toContainText(
    "Cached directory results",
  );
});

test("expanded SEC concept notices fit the viewport without horizontal page overflow", async ({ page }) => {
  const fixture = providerFixture();
  fixture.annual.warnings = [{
    field: "shareholders_equity",
    code: "unverified_ownership_basis",
    message: "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest cannot substitute for parent equity.",
  }];
  await mockApi(page, fixture);
  await chooseProvider(page);
  await expect(page.getByRole("heading", { name: "API Fixture Corporation (MSFT)" })).toBeVisible();
  await page.locator(".research-quality-notice").filter({ has: page.getByRole("heading", { name: "Data quality & sources", exact: true }) }).locator(".research-source-notices > summary").click();
  await expect(page.locator(".research-notice-groups > li > p").filter({ hasText: /cannot substitute for parent equity/ })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width + 1);
});

test("historical diagnostics collapse and group by issue type while exact source records remain inspectable", async ({ page }) => {
  const fixture = providerFixture();
  const warnings = Array.from({ length: 50 }, (_, index) => ({
    code: index % 2 ? "restated_fact" : "incomplete_debt_components",
    field: index % 2 ? "revenue" : "total_debt",
    message: `FY${2000 + index} FY (${2000 + index}-06-30): ${index % 2 ? "a later filing revised this exact reporting period." : "current maturities of long-term debt are unavailable."}`,
    source_id: `fixture:exact-source:${index}`,
  }));
  fixture.annual.warnings = warnings;
  await mockApi(page, fixture);
  await page.route("**/api/stocks/*/valuation/**", async (route) => {
    const request = route.request().method() === "POST" ? route.request().postDataJSON() : {};
    const response = providerValuationFixture("MSFT", { request, forceActive: true });
    response.warnings = [...warnings, { code: "missing_share_count", message: "The market provider did not supply a usable current share count." }];
    return route.fulfill({ json: response });
  });
  await chooseProvider(page);
  await expect(page.getByRole("heading", { name: "API Fixture Corporation (MSFT)" })).toBeVisible();
  const status = page.getByRole("region", { name: "Python valuation engine" });
  const history = status.locator(".research-source-notices");
  await expect(history).not.toHaveAttribute("open");
  await expect(history.locator(":scope > summary")).toHaveText("Historical financial source checks: 2 issue types · 50 notices");
  await expect(status.getByText("The market provider did not supply a usable current share count.", { exact: true })).toBeVisible();
  await expect(status.locator("summary").filter({ hasText: "Valuation quality: low" })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("Single-model estimate");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$165.00");
  await expect(history.locator("pre").first()).not.toBeVisible();
  await history.locator(":scope > summary").click();
  await expect(history.locator(".research-notice-groups > li")).toHaveCount(2);
  await expect(history).toContainText("25 notices");
  await expect(history).toContainText("Affected periods:");
  const debt = history.locator(".research-notice-groups > li").filter({ has: page.getByText("Incomplete debt components", { exact: true }) });
  await debt.locator("summary").click();
  await expect(debt.locator("pre")).toHaveCount(25);
  await expect(debt.locator("pre").first()).toHaveText(JSON.stringify(warnings[0], null, 2));
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width + 1);
});

test("long company overview expands accessibly and research checklist links to the actual AI workspace", async ({ page }) => {
  const fixture = providerFixture();
  fixture.profile.company.description = "Provider business overview covering software, cloud services and recurring enterprise revenue. ".repeat(30).trim();
  await mockApi(page, fixture);
  await chooseProvider(page);
  await expect(page.getByRole("heading", { name: "API Fixture Corporation (MSFT)" })).toBeVisible();
  const preview = page.locator(".research-company-description");
  expect((await preview.innerText()).length).toBeLessThanOrEqual(280);
  const full = page.locator(".research-company-full-description");
  await expect(full).not.toHaveAttribute("open");
  await expect(full.locator("p")).not.toBeVisible();
  await full.locator("summary").focus();
  await page.keyboard.press("Enter");
  await expect(full.locator("p")).toHaveText(fixture.profile.company.description);
  await expect(full.locator("p")).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(full.locator("p")).not.toBeVisible();
  const checklist = page.getByRole("region", { name: "Research insights", exact: true });
  await expect(checklist).toContainText("Static research checklist");
  await expect(checklist).not.toContainText(fixture.profile.company.description);
  await expect(checklist).not.toContainText("available in a later phase");
  await expect(checklist).not.toContainText("No AI-generated analysis is provided");
  await checklist.getByRole("link", { name: "Open MSFT AI Research", exact: true }).click();
  await expect(page).toHaveURL(/#ai-research$/);
  await expect(page.getByRole("heading", { name: "AI Research · MSFT", exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width + 1);
});
