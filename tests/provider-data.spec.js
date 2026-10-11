import { test, expect } from "@playwright/test";
import { providerFixture } from "./helpers/providerFixture.js";

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
  await page.locator(".research-quality-notice summary").click();
  await expect(
    page.getByText(/configured market price is stale/),
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
    page.getByText("Market provider price unavailable"),
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
    page.getByRole("checkbox", { name: "Enable Forward P/E", exact: true }),
  ).toBeDisabled();
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  await expect(
    page.getByRole("button", { name: "Quarterly", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText(
      /No valuation method has compatible required financial inputs/,
    ),
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
  await expect(page.getByRole("status")).toContainText(
    "Company directory status: stale.",
  );
  await expect(page.getByRole("status")).toContainText(
    "Cached directory results",
  );
});
