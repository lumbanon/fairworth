import { test, expect } from "@playwright/test";

const labels = [
  "Discounted Cash Flow (FCFF)",
  "Forward P/E",
  "EV/EBITDA",
  "EV/Revenue",
];
async function useOnlyPE(page) {
  for (const label of labels.filter((label) => label !== "Forward P/E"))
    await page
      .getByRole("checkbox", { name: `Enable ${label}`, exact: true })
      .uncheck();
  await page.getByLabel("Valuation method", { exact: true }).selectOption("pe");
}

test("all datasets render distinct company dashboards with appropriate model selection", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const ticker of [
    "MSFT",
    "AAPL",
    "NVDA",
    "GOOG",
    "AMZN",
    "TSLA",
    "ORCL",
    "JPM",
    "KO",
    "O",
  ]) {
    await page.goto(`/stocks/${ticker}`);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(
      `(${ticker})`,
    );
    await expect(
      page.getByText("Demo financial data — not live market information."),
    ).toBeVisible();
    await expect(page.getByTestId("weighted-fair-value")).not.toHaveText("—");
    await expect(
      page.locator(".research-model-chart .recharts-surface"),
    ).toBeVisible();
    if (["JPM", "O", "TSLA"].includes(ticker))
      await expect(
        page.getByRole("checkbox", {
          name: "Enable Discounted Cash Flow (FCFF)",
          exact: true,
        }),
      ).toBeDisabled();
    if (ticker === "O")
      await expect(
        page.getByRole("checkbox", {
          name: "Enable REIT AFFO Valuation",
          exact: true,
        }),
      ).toBeChecked();
  }
  expect(errors).toEqual([]);
});

test("assumptions recalculate from formulas, reset, and remain scoped to each scenario", async ({
  page,
}) => {
  await page.goto("/dashboard");
  await useOnlyPE(page);
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$464.95");
  await page
    .getByRole("spinbutton", { name: "EPS growth", exact: true })
    .fill("20");
  await page
    .getByRole("spinbutton", { name: "Target Forward P/E", exact: true })
    .fill("30");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$467.03");
  await page
    .getByRole("button", { name: "Reset to Default", exact: true })
    .click();
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$464.95");
  const group = page.getByRole("group", { name: "Active valuation scenario" });
  await group.getByRole("button", { name: "Bear", exact: true }).click();
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$352.03");
  await page
    .getByRole("spinbutton", { name: "EPS growth", exact: true })
    .fill("40");
  await group.getByRole("button", { name: "Base", exact: true }).click();
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("$464.95");
  await group.getByRole("button", { name: "Bear", exact: true }).click();
  await expect(
    page.getByRole("spinbutton", { name: "EPS growth", exact: true }),
  ).toHaveValue("40");
  await page
    .getByRole("button", { name: "Reset to Default", exact: true })
    .click();
  await expect(
    page.getByRole("spinbutton", { name: "EPS growth", exact: true }),
  ).toHaveValue("6");
});

test("model weights normalize and disabled or zero-weight methods do not contribute", async ({
  page,
}) => {
  await page.goto("/dashboard");
  const original = await page.getByTestId("weighted-fair-value").textContent();
  await useOnlyPE(page);
  await expect(page.getByText("100.0% normalized")).toBeVisible();
  await page
    .getByRole("spinbutton", { name: "Forward P/E raw weight", exact: true })
    .fill("0");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  await expect(page.getByRole("alert")).toContainText(
    "No valid enabled models have a positive weight",
  );
  await page
    .getByRole("spinbutton", { name: "Forward P/E raw weight", exact: true })
    .fill("-1");
  await expect(page.getByRole("alert")).toContainText(
    "weights must be finite, non-negative",
  );
  await page
    .getByRole("button", { name: "Reset Models & Weights", exact: true })
    .click();
  await expect(page.getByTestId("weighted-fair-value")).toHaveText(original);
  for (const label of labels)
    await page
      .getByRole("checkbox", { name: `Enable ${label}`, exact: true })
      .uncheck();
  await expect(page.getByRole("alert")).toContainText(
    "No valuation models are enabled",
  );
});

test("invalid discount rates and share counts show warnings without NaN or Infinity", async ({
  page,
}) => {
  await page.goto("/dashboard");
  await page.getByRole("spinbutton", { name: "WACC", exact: true }).fill("50");
  await expect(page.locator('#sensitivity [role="alert"]')).toContainText(
    "Enter valid base-case inputs",
  );
  await expect(page.getByTestId("sensitivity-current")).toHaveCount(0);
  await expect(page.locator('#reverse-dcf [role="alert"]')).toContainText(
    "WACC must be a finite value",
  );
  await expect(page.getByTestId("implied-growth")).toHaveCount(0);
  await page.getByRole("spinbutton", { name: "WACC", exact: true }).fill("2");
  await expect(
    page.locator('.assumptions-editor [role="alert"]'),
  ).toContainText("discount rate must exceed terminal growth");
  await page
    .getByRole("spinbutton", {
      name: "Diluted shares outstanding",
      exact: true,
    })
    .fill("0");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  await expect(
    page.locator('.assumptions-editor [role="alert"]'),
  ).toContainText("Diluted shares outstanding must be a finite value");
  await expect(page.locator("body")).not.toContainText("NaN");
  await expect(page.locator("body")).not.toContainText("Infinity");
  await page
    .getByRole("button", { name: "Reset to Default", exact: true })
    .click();
  await expect(page.getByTestId("weighted-fair-value")).not.toHaveText("—");
});

test("sensitivity center uses the base formula and statements reconcile with model data", async ({
  page,
}) => {
  await page.goto("/dashboard");
  await page.getByLabel("Valuation method", { exact: true }).selectOption("pe");
  await page
    .getByRole("group", { name: "Sensitivity model" })
    .getByRole("button", { name: "Forward P/E", exact: true })
    .click();
  await expect(page.getByTestId("sensitivity-current")).toHaveText("$464.95");
  await page
    .getByRole("spinbutton", { name: "Target Forward P/E", exact: true })
    .fill("30");
  await expect(page.getByTestId("sensitivity-current")).toHaveText("$435.89");
  await page
    .getByRole("button", { name: "Balance Sheet", exact: true })
    .click();
  await expect(
    page
      .locator(".statements-table")
      .getByRole("row", { name: /Shareholders/ }),
  ).toContainText("$250B");
  await page
    .getByRole("button", { name: "Cash Flow Statement", exact: true })
    .click();
  await expect(
    page
      .locator(".statements-table")
      .getByRole("row", { name: "FCFF proxy", exact: false }),
  ).toContainText("$92.37B");
  await expect(page.getByTestId("implied-growth")).toBeVisible();
});

test("global search supports extra demo tickers, rejects unsupported data, and resets company assumptions", async ({
  page,
}) => {
  await page.goto("/stocks/MSFT");
  await page.getByRole("spinbutton", { name: "WACC", exact: true }).fill("12");
  await page
    .getByRole("combobox", { name: "Search by company or ticker", exact: true })
    .fill("Coca-Cola");
  await page.getByRole("option", { name: /KO Coca-Cola/ }).click();
  await expect(page).toHaveURL("/stocks/KO");
  await expect(
    page.getByRole("spinbutton", { name: "WACC", exact: true }),
  ).toHaveValue("7.5");
  await page
    .getByRole("combobox", { name: "Search by company or ticker", exact: true })
    .fill("ABCDE");
  await page
    .getByRole("combobox", { name: "Search by company or ticker", exact: true })
    .press("Enter");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "No demo dataset for ABCDE.",
  );
  await expect(page.getByTestId("weighted-fair-value")).toHaveCount(0);
});

test("dashboard navigation, details, and responsive layouts work without page overflow", async ({
  page,
}, testInfo) => {
  await page.goto("/dashboard");
  await page.locator(".research-model-chart .recharts-surface").waitFor();
  await page.screenshot({
    path: `test-results/dashboard-${testInfo.project.name}.png`,
    fullPage: true,
  });
  for (const width of [320, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
  }
  await page
    .getByRole("navigation", { name: "Dashboard sections" })
    .getByRole("link", { name: "Financials", exact: true })
    .click();
  await expect(page).toHaveURL("/dashboard#financials");
  await expect(
    page.getByRole("heading", { name: "Financial fundamentals" }),
  ).toBeInViewport();
  await page
    .getByRole("button", { name: "Details for Forward P/E", exact: true })
    .click();
  await expect(page.locator(".model-details")).toContainText("Formula:");
  await page
    .getByRole("button", { name: "Edit Assumptions", exact: true })
    .click();
  await expect(
    page.getByLabel("Valuation method", { exact: true }),
  ).toHaveValue("pe");
});
