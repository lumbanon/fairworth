import { test, expect } from "@playwright/test";
import { providerFixture } from "./helpers/providerFixture.js";
import { providerValuationFixture } from "./helpers/providerValuationFixture.js";

// Synthetic UI transport records. No provider, licensing or valuation fact is
// established by these fixtures; every outgoing external request is blocked.
async function marketApi(page, { currencyStatus = "verified", accessStatus = "observed_access", quote = true } = {}) {
  const fixture = providerFixture();
  const source = { provider: "fmp", source_kind: "provider_quote", source_url: "https://financialmodelingprep.com/stable/quote", source_record_hash: "a".repeat(64), source_version_date: "2026-01-15", retrieved_at: "2026-02-11T10:00:00Z", issuer_id: "synthetic-issuer", instrument_id: "synthetic-instrument", listing_id: "synthetic-listing", provider_symbol: "MSFT", mic: "XNAS", original_record: { symbol: "MSFT", currency: "USD", exchange: "NASDAQ", cik: "0000000001" } };
  const capabilities = { methodology_version: "provider-capabilities-1", provider: "fmp", subscription: "free", scope: { ticker: "MSFT" }, display_license_status: "unresolved", endpoints: {
    quote: { endpoint: "quote", access_status: accessStatus, observed_at: accessStatus === "not_yet_tested" ? null : "2026-02-11T10:00:00Z", error_code: accessStatus === "requires_paid_subscription" ? "provider_subscription_required" : null, evidence_kind: "dated_request_outcome", display_license_status: "unresolved" },
    profile: { endpoint: "profile", access_status: "requires_paid_subscription", observed_at: "2026-02-10T10:00:00Z", error_code: "provider_subscription_required", display_license_status: "unresolved" },
    splits: { endpoint: "splits", access_status: "not_yet_tested", observed_at: null, display_license_status: "unresolved" },
  } };
  fixture.profile.provider_capabilities = capabilities;
  if (quote) fixture.profile.market = { ...fixture.profile.market, provider: "fmp", currency: currencyStatus === "verified" ? "USD" : null, provider_capabilities: capabilities, currency_resolution: { methodology_version: "quote-currency-1", status: currencyStatus, currency: currencyStatus === "verified" ? "USD" : null, reason_codes: currencyStatus === "verified" ? [] : ["quote_currency_unverified"], evidence: currencyStatus === "verified" ? [source] : [] } };
  else fixture.profile.market = null;
  fixture.dataStatus.provider_status.market = { provider: "fmp", status: quote ? "partial" : "unavailable", provider_capabilities: capabilities };
  const unexpected = [];
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith("/api/")) {
      if (["127.0.0.1", "localhost"].includes(url.hostname)) return route.continue();
      unexpected.push(`${url.origin}${url.pathname}`);
      return route.abort();
    }
    if (url.pathname.includes("/ai/")) return route.fulfill({ json: { enabled: false, configured: false, available: false, message: "AI disabled in offline market tests.", limitations: [] } });
    if (url.pathname.includes("/valuation/")) {
      const response = providerValuationFixture("MSFT", { price: quote && currencyStatus === "verified" ? 100 : null });
      for (const scenario of Object.values(response.scenarios)) scenario.publication = { result_type: "unavailable", blockers: [{ code: currencyStatus === "verified" ? "required_metric_missing" : "quote_currency_unverified", message: "Complete compatible model evidence is not supplied by this synthetic fixture." }], clocks: {} };
      return route.fulfill({ json: response });
    }
    if (url.pathname.endsWith("/coverage")) return route.fulfill({ status: 404, json: { error: { code: "not_supplied", message: "No coverage snapshot in this fixture." } } });
    const json = url.pathname.endsWith("/financials") ? url.searchParams.get("period") === "quarterly" ? fixture.quarterly : fixture.annual
      : url.pathname.endsWith("/metrics") ? fixture.metrics : url.pathname.endsWith("/data-status") ? fixture.dataStatus : fixture.profile;
    return route.fulfill({ json });
  });
  await page.goto("/stocks/MSFT");
  await page.getByRole("group", { name: "Financial data mode" }).getByRole("button", { name: "Provider data", exact: true }).click();
  await expect(page.getByRole("heading", { name: "API Fixture Corporation (MSFT)", exact: true })).toBeVisible();
  return { unexpected };
}

async function fitsViewport(page) {
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width + 1);
}

test("source-backed quote currency keeps its observation, retrieval and exact source separate", async ({ page }) => {
  const { unexpected } = await marketApi(page);
  await expect(page.getByTestId("quote-currency-status")).toHaveText("Quote currency: USD · Source-backed quote currency");
  await expect(page.locator("#overview")).toContainText("Quote observed: 2026-01-15T16:00:00Z");
  const details = page.getByTestId("market-evidence-details");
  await details.locator(":scope > summary").click();
  await expect(details).toContainText("Subscription: free");
  await expect(details).toContainText("Public display rights: Unresolved");
  await expect(details).toContainText("Share splits: Not yet tested");
  await details.getByText("Currency source 1: fmp", { exact: true }).click();
  await expect(details).toContainText("2026-02-11T10:00:00Z");
  await expect(details).toContainText("synthetic-listing");
  await details.getByText("Exact currency evidence record", { exact: true }).click();
  await expect(details.locator("pre")).toContainText('"currency": "USD"');
  await fitsViewport(page);
  expect(unexpected).toEqual([]);
});

test("missing currency is explicit despite a USD financial statement and successful dated quote access", async ({ page }) => {
  const { unexpected } = await marketApi(page, { currencyStatus: "quote_currency_unverified" });
  await expect(page.getByTestId("quote-currency-status")).toHaveText("Quote currency: Unverified · Quote currency unverified");
  await expect(page.locator(".research-price strong")).toHaveText("100 (currency unavailable)");
  await expect(page.locator("#overview")).toContainText("Financial reporting currency: USD");
  await expect(page.locator("#overview")).toContainText("a US exchange do not establish quote currency");
  await expect(page.getByTestId("quote-access-status")).toContainText("Dated successful request");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  await expect(page.getByTestId("summary-upside")).toHaveText("—");
  await fitsViewport(page);
  expect(unexpected).toEqual([]);
});

for (const [accessStatus, label] of [["requires_paid_subscription", "Subscription restricted"], ["rate_limited", "Rate limited"], ["temporarily_unavailable", "Temporarily unavailable"], ["not_yet_tested", "Not yet tested"]]) test(`${accessStatus} remains distinct and cannot create a provider quote or fair value`, async ({ page }) => {
  const { unexpected } = await marketApi(page, { accessStatus, quote: false });
  await expect(page.getByTestId("quote-access-status")).toContainText(label);
  await expect(page.locator(".research-price strong")).toHaveText("—");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  await expect(page.getByTestId("valuation-publication-type")).toHaveText("Unavailable");
  if (accessStatus === "requires_paid_subscription") await expect(page.locator("#overview")).toContainText("restricted under the configured provider access");
  else await expect(page.locator("#overview")).not.toContainText("restricted under the configured provider access");
  await fitsViewport(page);
  expect(unexpected).toEqual([]);
});
