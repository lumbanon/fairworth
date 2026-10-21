import { test, expect } from "@playwright/test";
import { providerFixture } from "./helpers/providerFixture.js";
import { providerValuationFixture } from "./helpers/providerValuationFixture.js";
import { aiResearchFixture } from "./helpers/aiResearchFixture.js";

// Real-world symbol spellings exercise transport identity. All financial values,
// provider statuses and research here are synthetic UI fixtures, never observations.
const securities = [
  { ticker: "GOOGL", name: "Alphabet Inc.", instrument_id: "fixture-alphabet-a", issuer_id: "fixture-alphabet", listing_id: "fixture-xnas-googl", cik: "0001652044", exchange: "NASDAQ", instrument_type: "common_stock", share_class: "A", listing_status: "active", identity_status: "verified" },
  { ticker: "GOOG", name: "Alphabet Inc.", instrument_id: "fixture-alphabet-c", issuer_id: "fixture-alphabet", listing_id: "fixture-xnas-goog", cik: "0001652044", exchange: "NASDAQ", instrument_type: "common_stock", share_class: "C", listing_status: "active", identity_status: "verified" },
  { ticker: "TSM", name: "Taiwan Semiconductor Manufacturing Company", instrument_id: "fixture-tsm-adr", issuer_id: "fixture-tsmc", listing_id: "fixture-xnys-tsm", cik: "0001046179", exchange: "NYSE", instrument_type: "adr", listing_status: "active", identity_status: "verified" },
  { ticker: "SPY", name: "SPDR S&P 500 ETF Trust", instrument_id: "fixture-spy", issuer_id: "fixture-spdr", listing_id: "fixture-arcx-spy", cik: "0000884394", exchange: "NYSE Arca", instrument_type: "etf", listing_status: "active", identity_status: "verified" },
];

async function registryApi(page, { sparse = false, mismatch = false, paginated = false, searchError = false, staleSearch = false, multipleListings = false, coverageError = 0, identityOverrides = {} } = {}) {
  const requests = [], unexpected = [];
  const listingSamples = (multipleListings ? [securities[0], { ...securities[0], exchange: "NYSE", listing_id: "fixture-xnys-googl" }] : securities).map((security) => ({ ...security, ...(typeof identityOverrides === "function" ? identityOverrides(security) : identityOverrides) }));
  await page.addInitScript(() => sessionStorage.setItem("fairworth-data-mode", "provider"));
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith("/api/")) {
      if (["127.0.0.1", "localhost"].includes(url.hostname)) return route.continue();
      unexpected.push(`${url.origin}${url.pathname}`);
      return route.abort();
    }
    requests.push({ pathname: url.pathname, parameters: Object.fromEntries(url.searchParams), method: route.request().method() });
    if (url.pathname.endsWith("/search")) {
      if (searchError) return route.fulfill({ status: 429, json: { error: { code: "registry_rate_limited", message: "The mocked registry search is temporarily rate limited." } } });
      const query = (url.searchParams.get("q") || "").toUpperCase();
      const offset = Number(url.searchParams.get("offset") || 0);
      const results = paginated ? Array.from({ length: 10 }, (_, index) => ({ ...securities[0], ticker: `ZZ${offset + index}`, name: `Synthetic security ${offset + index}`, instrument_id: `fixture-${offset + index}`, listing_id: `fixture-listing-${offset + index}` }))
        : listingSamples.filter((item) => `${item.ticker} ${item.display_symbol ?? ""} ${item.name}`.toUpperCase().includes(query));
      return route.fulfill({ json: { results, limit: 10, offset, has_more: paginated && offset === 0, status: staleSearch ? "stale" : "fresh", warnings: staleSearch ? [{ message: "Registry observations are dated; current listing status requires confirmation." }] : [], as_of: "2026-10-18", registry_version: "fixture-registry-1" } });
    }
    const ticker = decodeURIComponent(url.pathname.split("/")[3]);
    if (ticker === "DUP") return route.fulfill({ status: 409, json: { error: { code: "identity_ambiguous", message: "This symbol refers to more than one security.", details: { candidates: securities.slice(0, 2) } } } });
    if (multipleListings && !url.searchParams.get("listing_id")) return route.fulfill({ status: 409, json: { error: { code: "identity_ambiguous", message: "Select the intended listing venue.", details: { candidates: listingSamples } } } });
    const identity = listingSamples.find((item) => item.listing_id === url.searchParams.get("listing_id")) ?? listingSamples.find((item) => item.instrument_id === url.searchParams.get("instrument_id")) ?? listingSamples.find((item) => item.ticker === ticker);
    if (!identity) {
      unexpected.push(`Unknown mocked stock endpoint ${url.pathname}`);
      return route.fulfill({ status: 404, json: { error: { code: "unknown_ticker", message: "No verified instrument matches this symbol." } } });
    }
    const financial = providerFixture(identity.ticker);
    financial.profile.company = { ...financial.profile.company, ...identity };
    for (const key of ["annual", "quarterly", "metrics", "dataStatus"]) financial[key].identity = identity;
    if (url.pathname.includes("/ai/")) {
      if (url.pathname.endsWith("/status")) return route.fulfill({ json: { available: true, enabled: true, configured: true, message: "Mocked research is ready; no external AI service is called.", limitations: [] } });
      if (!url.pathname.endsWith("/chat")) unexpected.push(`Unexpected AI generation ${url.pathname}`);
      const response = aiResearchFixture(identity.ticker, { kind: "chat", marker: "Identity-scoped mocked research" });
      response.identity = identity;
      for (const evidence of response.evidence_references) { evidence.identity = identity; evidence.source_url = `https://data.sec.gov/api/xbrl/companyfacts/CIK${identity.cik}.json`; }
      return route.fulfill({ json: response });
    }
    if (url.pathname.endsWith("/coverage")) {
      if (coverageError) return route.fulfill({ status: coverageError, json: { error: { code: coverageError === 429 ? "provider_rate_limited" : "coverage_unavailable", message: "The mocked coverage service is temporarily unavailable." } } });
      const unsupported = identity.instrument_type === "etf";
      const stages = Object.fromEntries(["symbol_resolution", "security_identity", "active_listing", "classification", "share_basis", "profile", "statements", "normalization", "freshness", "valuation", "ai_research"].map((key) => [key, { status: "available", reason: "Synthetic offline assessment; no provider request was made." }]));
      if (unsupported) { stages.classification = { status: "financially_inapplicable", reason: "Ordinary operating-company valuation models do not apply to an ETF." }; stages.valuation = stages.classification; }
      else { stages.valuation = { status: "missing_evidence", reason: "No supported model inputs are supplied by this synthetic fixture.", contributing_model_count: 0 }; }
      if (sparse) stages.statements = { status: "provider_restricted", reason: "The mocked provider restricts annual statements." };
      return route.fulfill({ json: { identity, as_of: "2026-10-18", methodology_version: "coverage-fixture-1", stages } });
    }
    if (url.pathname.includes("/valuation/")) {
      const request = route.request().method() === "POST" ? route.request().postDataJSON() : {};
      const response = providerValuationFixture(identity.ticker, { request });
      response.company = { ...response.company, ...identity };
      return route.fulfill({ json: response });
    }
    if (url.pathname.endsWith("/financials")) {
      if (sparse && (url.searchParams.get("period") === "annual" || sparse === "all")) return route.fulfill({ status: 402, json: { error: { code: "provider_restricted", message: "The mocked provider restricts financial statements." } } });
      const response = url.searchParams.get("period") === "quarterly" ? financial.quarterly : financial.annual;
      if (identity.instrument_type === "etf") response.periods = [];
      if (mismatch && url.searchParams.get("period") === "annual") response.identity = { ...identity, instrument_id: "another-share-class" };
      return route.fulfill({ json: response });
    }
    if (url.pathname.endsWith("/metrics")) return route.fulfill({ json: financial.metrics });
    if (url.pathname.endsWith("/data-status")) return route.fulfill({ json: financial.dataStatus });
    return route.fulfill({ json: financial.profile });
  });
  return { requests, unexpected };
}

async function fitsViewport(page) {
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width + 1);
}

async function tabTo(page, target) {
  // Chromium may include the scrollable listbox in sequential focus order.
  for (let step = 0; step < 4; step += 1) {
    await page.keyboard.press("Tab");
    if (await target.evaluate((element) => element === document.activeElement)) return;
  }
  await expect(target).toBeFocused();
}

test("outside-four search preserves instrument identity through dashboard navigation and mocked AI citations", async ({ page }) => {
  const { requests, unexpected } = await registryApi(page);
  await page.goto("/");
  const search = page.getByRole("combobox", { name: "Search by company or ticker", exact: true });
  await search.fill("GOOGL");
  const option = page.getByRole("option");
  await expect(option).toContainText("NASDAQ · Common stock · Class A");
  await search.press("ArrowDown");
  await search.press("Enter");
  await expect(page).toHaveURL(/\/stocks\/GOOGL\?instrument_id=fixture-alphabet-a&listing_id=fixture-xnas-googl$/);
  await expect(page.getByRole("heading", { name: "Company analysis coverage", exact: true })).toBeVisible();
  await expect(page.locator(".company-classification")).toContainText("Share class A");
  await page.getByRole("button", { name: "AI Research", exact: true }).click();
  await expect(page).toHaveURL(/instrument_id=fixture-alphabet-a&listing_id=fixture-xnas-googl#ai-research$/);
  await page.getByRole("button", { name: "Why is GOOGL's valuation available or unavailable?", exact: true }).click();
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Identity-scoped mocked research", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "View source: Synthetic revenue transport fixture", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("GOOGL");
  await page.getByRole("button", { name: "Close", exact: true }).click();
  const scoped = requests.filter((request) => !request.pathname.endsWith("/search"));
  expect(scoped.length).toBeGreaterThan(6);
  expect(scoped.every((request) => request.parameters.instrument_id === "fixture-alphabet-a")).toBeTruthy();
  expect(scoped.every((request) => request.parameters.listing_id === "fixture-xnas-googl")).toBeTruthy();
  expect(unexpected).toEqual([]);
  await fitsViewport(page);
});

test("duplicate company names require explicit share-class selection", async ({ page }) => {
  const { unexpected } = await registryApi(page);
  await page.goto("/");
  const search = page.getByRole("combobox", { name: "Search by company or ticker", exact: true });
  await search.fill("Alphabet Inc.");
  await expect(page.getByRole("option")).toHaveCount(2);
  await search.press("Enter");
  await expect(page.getByRole("alert")).toContainText("Several securities match");
  await expect(page).toHaveURL(/\/$/);
  await page.getByRole("option").filter({ hasText: "Class C" }).click();
  await expect(page).toHaveURL(/\/stocks\/GOOG\?instrument_id=fixture-alphabet-c&listing_id=fixture-xnas-goog$/);
  await expect(page.locator(".company-classification")).toContainText("Share class C");
  expect(unexpected).toEqual([]);
  await fitsViewport(page);
});

test("bounded search pagination replaces a page of suggestions and discloses stale registry data", async ({ page }) => {
  const { requests, unexpected } = await registryApi(page, { paginated: true, staleSearch: true });
  await page.goto("/");
  await page.getByRole("combobox", { name: "Search by company or ticker", exact: true }).fill("ZZ");
  await expect(page.getByRole("option")).toHaveCount(10);
  await expect(page.locator(".search-help[role=status]")).toContainText("Registry observations are dated");
  await page.getByRole("button", { name: "Show more matching securities", exact: true }).click();
  await expect(page.getByRole("option").first()).toContainText("ZZ10");
  await expect(page.getByRole("option")).toHaveCount(10);
  await page.getByRole("button", { name: "Previous matching securities", exact: true }).click();
  await expect(page.getByRole("option").first()).toContainText("ZZ0");
  expect(requests.every((request) => request.parameters.limit === "10")).toBeTruthy();
  expect(requests.map((request) => request.parameters.offset)).toEqual(["0", "10", "0"]);
  expect(unexpected).toEqual([]);
  await fitsViewport(page);
});

test("provider-restricted statements retain the company dashboard without inventing annual values", async ({ page }) => {
  const { unexpected } = await registryApi(page, { sparse: true });
  await page.goto("/stocks/GOOGL?instrument_id=fixture-alphabet-a");
  await expect(page.locator("#company-title")).toContainText("Alphabet Inc.");
  await expect(page.getByRole("region", { name: "Company analysis coverage", exact: true })).toContainText("Provider restricted");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  await expect(page.locator("#financials")).toContainText("SEC EDGAR · quarterly");
  await expect(page.getByRole("button", { name: "Annual", exact: true })).toHaveCount(0);
  await expect(page.locator("#financials")).not.toContainText("SEC EDGAR · annual");
  await expect(page.locator(".research-quality-notice").first()).toContainText("Financial status:");
  expect(unexpected).toEqual([]);
  await fitsViewport(page);
});

test("complete statement absence keeps identity and coverage visible without a blank dashboard", async ({ page }) => {
  const { unexpected } = await registryApi(page, { sparse: "all" });
  await page.goto("/stocks/GOOGL?instrument_id=fixture-alphabet-a");
  await expect(page.locator("#company-title")).toContainText("Alphabet Inc.");
  await expect(page.locator("#financials")).toContainText("No compatible financial statement periods");
  await expect(page.locator("#financials table")).toHaveCount(0);
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  expect(unexpected).toEqual([]);
  await fitsViewport(page);
});

test("unsupported ETF profiles explain applicability without requesting an ordinary-stock valuation", async ({ page }) => {
  const { requests, unexpected } = await registryApi(page);
  await page.goto("/");
  await page.getByRole("combobox", { name: "Search by company or ticker", exact: true }).fill("SPY");
  await expect(page.getByRole("option")).toContainText("Operating-company models inapplicable");
  await page.getByRole("option").click();
  await expect(page.getByRole("heading", { name: "Ordinary-stock valuation unavailable", exact: true })).toBeVisible();
  await expect(page.locator(".company-classification")).toContainText("ETF");
  await expect(page.locator("#models")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Company analysis coverage", exact: true })).toContainText("Financially inapplicable");
  expect(requests.some((request) => request.pathname.includes("/valuation/"))).toBeFalsy();
  expect(unexpected).toEqual([]);
  await fitsViewport(page);
});

test("ADRs disclose underlying issuer and per-security currency and ratio requirements", async ({ page }) => {
  const { unexpected } = await registryApi(page);
  await page.goto("/stocks/TSM?instrument_id=fixture-tsm-adr");
  await expect(page.locator(".company-classification")).toContainText("ADR / ADS");
  await expect(page.locator(".research-company .research-warning")).toContainText("Reporting currency, ADR ratio and per-security share basis");
  await expect(page.getByTestId("weighted-fair-value")).toHaveText("—");
  expect(unexpected).toEqual([]);
  await fitsViewport(page);
});

test("ambiguous bare symbols offer explicit identities and mismatched financial responses fail closed", async ({ page }) => {
  const { unexpected } = await registryApi(page, { mismatch: true });
  await page.goto("/stocks/DUP");
  await expect(page.getByRole("alert")).toContainText("more than one security");
  const candidates = page.locator(".provider-identity-candidates a");
  await expect(candidates).toHaveCount(2);
  await candidates.first().click();
  await expect(page.getByRole("alert")).toContainText("does not match");
  await expect(page.locator("#company-title")).toHaveCount(0);
  expect(unexpected).toEqual([]);
  await fitsViewport(page);
});

test("search provider errors are readable and never substitute demonstration results", async ({ page }) => {
  const { unexpected } = await registryApi(page, { searchError: true });
  await page.goto("/");
  await page.getByRole("combobox", { name: "Search by company or ticker", exact: true }).fill("ALPHABET");
  await expect(page.getByRole("alert")).toContainText("temporarily rate limited");
  await expect(page.getByRole("option")).toHaveCount(0);
  await expect(page.getByRole("alert")).toContainText("No demo suggestions have been substituted");
  expect(unexpected).toEqual([]);
  await fitsViewport(page);
});

test("same-instrument listings retain distinct search choices and isolate the selected venue and research state", async ({ page }) => {
  const { requests, unexpected } = await registryApi(page, { multipleListings: true });
  await page.goto("/stocks/GOOGL?instrument_id=fixture-alphabet-a");
  await expect(page.getByRole("alert")).toContainText("intended listing venue");
  const candidates = page.locator(".provider-identity-candidates a");
  await expect(candidates).toHaveCount(2);
  await expect(candidates.first()).toContainText("Class A · CIK 0001652044 · Listing active");
  await expect(candidates.nth(1)).toContainText("Listing ID fixture-xnys-googl");
  await candidates.nth(1).click();
  await expect(page).toHaveURL(/instrument_id=fixture-alphabet-a&listing_id=fixture-xnys-googl$/);
  await expect(page.locator(".company-classification")).toContainText("NYSE");
  await page.getByRole("button", { name: "AI Research", exact: true }).click();
  await page.getByRole("button", { name: "Why is GOOGL's valuation available or unavailable?", exact: true }).click();
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  await expect(page.locator(".ai-turn")).toHaveCount(1);
  const search = page.getByRole("combobox", { name: "Search by company or ticker", exact: true });
  await search.fill("GOOGL");
  await expect(page.getByRole("option")).toHaveCount(2);
  await page.getByRole("option").filter({ hasText: "NASDAQ" }).click();
  await expect(page).toHaveURL(/instrument_id=fixture-alphabet-a&listing_id=fixture-xnas-googl$/);
  await expect(page.locator(".company-classification")).toContainText("NASDAQ");
  await page.getByRole("button", { name: "AI Research", exact: true }).click();
  await expect(page.locator(".ai-turn")).toHaveCount(0);
  // Availability is fetched in an effect after the newly selected panel mounts.
  // Wait for that actual request before taking the transport assertion snapshot.
  await expect.poll(() => requests.some((request) => request.pathname.includes("/ai/") && request.parameters.listing_id === "fixture-xnys-googl")).toBeTruthy();
  await expect.poll(() => requests.some((request) => request.pathname.includes("/ai/") && request.parameters.listing_id === "fixture-xnas-googl")).toBeTruthy();
  expect(unexpected).toEqual([]);
  await fitsViewport(page);
});

test("keyboard focus reaches search pagination and leaving the search closes its results", async ({ page }) => {
  const { unexpected } = await registryApi(page, { paginated: true });
  await page.goto("/");
  const search = page.getByRole("combobox", { name: "Search by company or ticker", exact: true });
  await search.fill("ZZ");
  await expect(page.getByRole("option")).toHaveCount(10);
  await search.press("Tab");
  await expect(page.getByRole("button", { name: "Search stock", exact: true })).toBeFocused();
  await tabTo(page, page.getByRole("button", { name: "Show more matching securities", exact: true }));
  await page.keyboard.press("Enter");
  await expect(page.getByRole("option").first()).toContainText("ZZ10");
  await search.press("Tab");
  await tabTo(page, page.getByRole("button", { name: "Previous matching securities", exact: true }));
  await page.keyboard.press("Enter");
  await expect(page.getByRole("option").first()).toContainText("ZZ0");
  await page.getByRole("link", { name: "Fairworth home", exact: true }).focus();
  await expect(page.getByRole("listbox")).toHaveCount(0);
  expect(unexpected).toEqual([]);
  await fitsViewport(page);
});

test("coverage outages are explicit while legacy missing endpoints retain a usable financial dashboard", async ({ page }) => {
  for (const coverageError of [503, 429, 404]) {
    const { unexpected } = await registryApi(page, { coverageError });
    await page.goto("/stocks/GOOGL?instrument_id=fixture-alphabet-a&listing_id=fixture-xnas-googl");
    await expect(page.locator("#company-title")).toContainText("Alphabet Inc.");
    await expect(page.locator("#financials table")).toHaveCount(1);
    const coverage = page.getByRole("region", { name: "Company analysis coverage", exact: true });
    if (coverageError === 404) await expect(coverage).toHaveCount(0);
    else {
      await expect(coverage).toContainText("Company coverage diagnostics are unavailable");
      await expect(coverage).toContainText("temporarily unavailable");
      await expect(coverage.locator(".provider-coverage-grid")).toHaveCount(0);
    }
    expect(unexpected).toEqual([]);
    await fitsViewport(page);
  }
});

const syntheticListingVerification = {
  status: "verified", confidence: "source_backed", source: "synthetic_exchange_directory",
  freshness: "fresh", stale: false,
  observed_on: "2026-10-16", published_at: "1016202617:03", source_timezone: null,
  retrieved_at: "2026-10-19T12:00:00Z", record_hash: "f".repeat(64),
  source_url: "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
  conflicts: [], warnings: ["Synthetic listing observation for offline UI tests only."],
};

test("verified listing labels separate security form, issuer category and all source clocks", async ({ page }) => {
  const { unexpected } = await registryApi(page, { identityOverrides: { security_form: "common_stock", issuer_business_category: "bank", instrument_type: "financial_institution", listing_verification: syntheticListingVerification } });
  await page.goto("/");
  await page.getByRole("combobox", { name: "Search by company or ticker", exact: true }).fill("GOOGL");
  await expect(page.getByRole("option")).toContainText("NASDAQ · Common stock · Class A");
  await expect(page.getByRole("option")).toContainText("Verified active listing · Observed 2026-10-16");
  await page.getByRole("option").click();
  await expect(page.locator(".company-classification")).toContainText("Common stock · Share class A · Issuer: Bank");
  await expect(page.locator(".company-listing-verification")).toHaveText("Verified active listing · Listing observed 2026-10-16");
  const coverage = page.getByRole("region", { name: "Company analysis coverage", exact: true });
  await expect(coverage.locator(".provider-coverage-grid > div")).toHaveCount(10);
  await expect(coverage).toContainText("Security form: Common stock · Share class A · Issuer category: Bank");
  await expect(coverage).toContainText("Source freshness: Available");
  await coverage.getByText("Listing verification sources and dates", { exact: true }).click();
  const dates = coverage.locator(".provider-listing-dates");
  await expect(dates).toContainText("Listing observed2026-10-16");
  await expect(dates).toContainText("Source published (timezone unspecified)1016202617:03");
  await expect(dates).toContainText("Retrieved by Fairworth2026-10-19T12:00:00Z");
  await expect(dates).toContainText("Status effectiveNot supplied by source");
  await expect(coverage.getByRole("link", { name: "View listing source", exact: true })).toHaveAttribute("href", syntheticListingVerification.source_url);
  await coverage.getByText("Identity and complete coverage diagnostics", { exact: true }).click();
  await expect(coverage.locator("pre")).toContainText(syntheticListingVerification.record_hash);
  expect(unexpected).toEqual([]);
  await fitsViewport(page);
});

test("reference-only active declarations remain discoverable without claiming a verified listing", async ({ page }) => {
  const { unexpected } = await registryApi(page, { identityOverrides: { security_form: "unknown", identity_status: "reference_only", registry_retrieved_at: "2026-10-19T12:00:00Z", listing_verification: { status: "reference_only", confidence: "unverified", retrieved_at: "2026-10-19T12:00:00Z" } } });
  await page.goto("/");
  await page.getByRole("combobox", { name: "Search by company or ticker", exact: true }).fill("GOOGL");
  await expect(page.getByRole("option")).toContainText("Classification unverified");
  await expect(page.getByRole("option")).toContainText("Reference only · listing unverified");
  await expect(page.getByRole("option")).not.toContainText("Verified active listing");
  await page.getByRole("option").click();
  await expect(page.locator(".company-listing-verification")).toHaveText("Reference only · listing unverified");
  await expect(page.locator("#financials table")).toHaveCount(1);
  expect(unexpected).toEqual([]);
  await fitsViewport(page);
});

test("conflicting listing observations remain inspectable and cannot inherit a verified active label", async ({ page }) => {
  const conflicts = [{ field: "listing_status", observations: [{ source: "synthetic_exchange_a", value: "active", observed_on: "2026-10-16" }, { source: "synthetic_exchange_b", value: "suspended", observed_on: "2026-10-16" }] }];
  const { unexpected } = await registryApi(page, { identityOverrides: { security_form: "common_stock", listing_verification: { ...syntheticListingVerification, status: "conflicting", confidence: "conflicted", conflicts } } });
  await page.goto("/stocks/GOOGL?instrument_id=fixture-alphabet-a&listing_id=fixture-xnas-googl");
  await expect(page.locator(".company-listing-verification")).toContainText("Listing sources conflict");
  const coverage = page.getByRole("region", { name: "Company analysis coverage", exact: true });
  await expect(coverage.getByRole("status")).toContainText("Source records disagree");
  await expect(coverage).not.toContainText("Verified active listing");
  await coverage.getByText("Identity and complete coverage diagnostics", { exact: true }).click();
  await expect(coverage.locator("pre")).toContainText("synthetic_exchange_a");
  await expect(coverage.locator("pre")).toContainText("synthetic_exchange_b");
  expect(unexpected).toEqual([]);
  await fitsViewport(page);
});

test("stale listing observations retain their source date despite a later retrieval", async ({ page }) => {
  const { unexpected } = await registryApi(page, { identityOverrides: { security_form: "common_stock", registry_status: "stale", listing_verification: { ...syntheticListingVerification, observed_on: "2026-09-01" } } });
  await page.goto("/stocks/GOOGL?instrument_id=fixture-alphabet-a&listing_id=fixture-xnas-googl");
  await expect(page.locator(".company-listing-verification")).toHaveText("Dated active-listing observation · Listing observed 2026-09-01");
  const coverage = page.getByRole("region", { name: "Company analysis coverage", exact: true });
  await expect(coverage.getByRole("status")).toContainText("A recent retrieval does not establish a current active listing");
  await expect(coverage).not.toContainText("Verified active listing");
  await coverage.getByText("Listing verification sources and dates", { exact: true }).click();
  await expect(coverage.locator(".provider-listing-dates")).toContainText("2026-09-01");
  await expect(coverage.locator(".provider-listing-dates")).toContainText("2026-10-19T12:00:00Z");
  expect(unexpected).toEqual([]);
  await fitsViewport(page);
});

test("explicitly sourced suspended status is distinguished from an active listing", async ({ page }) => {
  const { unexpected } = await registryApi(page, { identityOverrides: { listing_status: "suspended", security_form: "common_stock", listing_verification: syntheticListingVerification } });
  await page.goto("/");
  await page.getByRole("combobox", { name: "Search by company or ticker", exact: true }).fill("GOOGL");
  await expect(page.getByRole("option")).toContainText("Verified suspended listing");
  await expect(page.getByRole("option")).not.toContainText("Verified active listing");
  expect(unexpected).toEqual([]);
  await fitsViewport(page);
});

test("source display symbols preserve the canonical ticker and exact selected security route", async ({ page }) => {
  const { requests, unexpected } = await registryApi(page, { identityOverrides: (security) => security.ticker === "GOOGL" ? { display_symbol: "SYNTH.A", security_form: "common_stock", listing_verification: syntheticListingVerification } : {} });
  await page.goto("/");
  const search = page.getByRole("combobox", { name: "Search by company or ticker", exact: true });
  await search.fill("SYNTH.A");
  await expect(page.getByRole("option")).toHaveCount(1);
  await expect(page.locator(".suggestion-ticker")).toHaveText("SYNTH.A");
  await search.press("Enter");
  await expect(page).toHaveURL(/\/stocks\/GOOGL\?instrument_id=fixture-alphabet-a&listing_id=fixture-xnas-googl$/);
  await expect(page.locator("#company-title")).toContainText("(SYNTH.A)");
  await expect(page.locator(".company-metadata")).toContainText(["Canonical symbol: GOOGL"]);
  const financialRequests = requests.filter((request) => !request.pathname.endsWith("/search"));
  expect(financialRequests.every((request) => request.pathname.includes("/GOOGL"))).toBeTruthy();
  expect(financialRequests.every((request) => request.parameters.listing_id === "fixture-xnas-googl")).toBeTruthy();
  expect(unexpected).toEqual([]);
  await fitsViewport(page);
});

test("expired listing and issuer proofs expose their original sources and independent dates", async ({ page }) => {
  const proof = { state: "verification_expired", observed_on: "2026-10-19", published_at: "1019202607:00", retrieved_at: "2026-10-20T12:00:00Z", expires_at: "2026-10-20T00:00:00Z", ttl_seconds: 86400 };
  const { unexpected } = await registryApi(page, { identityOverrides: { security_form: "common_stock", listing_verification: { ...syntheticListingVerification, observed_on: "2026-10-19" }, verification_state: "verification_expired", proof_expiry: { listing: { ...proof, source: "Synthetic exchange directory", source_url: "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt", reason: "Exchange observation expired under the listing policy." }, issuer_linkage: { ...proof, source: "SEC issuer-symbol directory", source_url: "https://www.sec.gov/files/company_tickers_exchange.json", observed_on: "2026-10-18", expires_at: "2026-10-19T00:00:00Z", reason: "SEC ownership proof expired independently." } } } });
  await page.goto("/stocks/GOOGL?instrument_id=fixture-alphabet-a&listing_id=fixture-xnas-googl");
  await expect(page.locator(".company-listing-verification")).toContainText("Listing verification expired");
  const coverage = page.getByRole("region", { name: "Company analysis coverage", exact: true });
  await expect(coverage).toContainText("Issuer linkage verification expired");
  await expect(coverage).toContainText("Exchange observation expired under the listing policy");
  await expect(coverage).toContainText("SEC ownership proof expired independently");
  await expect(coverage).not.toContainText("Verified active listing");
  await coverage.getByText("Issuer linkage sources and dates", { exact: true }).click();
  await expect(coverage).toContainText("2026-10-18");
  await expect(coverage).toContainText("2026-10-19T00:00:00Z");
  await expect(coverage.getByRole("link", { name: "View issuer linkage source", exact: true })).toHaveAttribute("href", "https://www.sec.gov/files/company_tickers_exchange.json");
  await fitsViewport(page);
  expect(unexpected).toEqual([]);
});

test("a current exchange listing cannot renew expired SEC issuer ownership", async ({ page }) => {
  const { unexpected } = await registryApi(page, { identityOverrides: { security_form: "common_stock", listing_verification: syntheticListingVerification, verification_state: "verification_expired", proof_expiry: { listing: { state: "verified" }, issuer_linkage: { state: "verification_expired", source: "SEC issuer-symbol directory", observed_on: "2026-10-18", expires_at: "2026-10-19T00:00:00Z", reason: "A recent listing refresh does not renew SEC issuer linkage." } } } });
  await page.goto("/stocks/GOOGL?instrument_id=fixture-alphabet-a&listing_id=fixture-xnas-googl");
  await expect(page.locator(".company-listing-verification")).toContainText("Verified active listing");
  const coverage = page.getByRole("region", { name: "Company analysis coverage", exact: true });
  await expect(coverage.getByTestId("issuer-linkage-verification")).toContainText("Issuer linkage verification expired");
  await expect(coverage).toContainText("A recent listing refresh does not renew SEC issuer linkage");
  await expect(coverage).not.toContainText("Listing verification expired");
  await fitsViewport(page);
  expect(unexpected).toEqual([]);
});
