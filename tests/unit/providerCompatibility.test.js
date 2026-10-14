import test from "node:test";
import assert from "node:assert/strict";
import { adaptProviderStock } from "../../src/lib/providerCompatibility.js";
import { fetchJson, loadStock, ApiError } from "../../src/services/api.js";
import { providerFixture } from "../helpers/providerFixture.js";

test("provider compatibility preserves financial units, native EPS, dates and original observations", () => {
  const company = adaptProviderStock(providerFixture());
  assert.equal(company.latest.revenue, 1400);
  assert.equal(company.latest.netIncome, 120);
  assert.equal(company.latest.shares, 12);
  assert.equal(company.latest.eps, 10);
  assert.equal(company.latest.freeCashFlow, 100);
  assert.equal(company.latest.periodEnd, "2025-12-31");
  assert.equal(company.latest.provenance.revenue[0].reported_value, 1400000000);
  assert.equal(company.latest.revenueGrowth, (1 / 6) * 100);
  assert.equal(company.marketCap, 1200);
  assert.equal(company.quarterlyFinancials[0].eps, 2.5);
});

test("provider financial presentation contains no invented forward assumptions or cash flow proxies", () => {
  const company = adaptProviderStock(providerFixture());
  assert.equal(company.latest.fcff, null);
  assert.equal(company.latest.fcfe, null);
  assert.equal(company.latest.ebitda, null);
  assert.equal(company.otherClaims, null);
  assert.equal(company.forwardEPS, undefined);
});

test("missing and incompatible earnings shares cannot be replaced by market shares", () => {
  const data = providerFixture();
  data.annual.periods[0].metrics.weighted_average_diluted_shares = null;
  const company = adaptProviderStock(data);
  assert.equal(company.latest.shares, null);
  assert.match(company.modelCompatibility.pe, /same-period/);
  data.annual.periods[0].metrics.weighted_average_diluted_shares = 12000000;
  data.annual.periods[0].metrics.diluted_eps = 8;
  const incompatible = adaptProviderStock(data);
  assert.match(incompatible.modelCompatibility.pe, /does not reconcile/);
  assert.ok(
    incompatible.warnings.some(
      (warning) => warning.code === "incompatible_earnings_basis",
    ),
  );
});

test("reported EPS rounding is allowed while materially different common earnings stay unavailable", () => {
  const data = providerFixture();
  data.annual.periods[0].metrics.net_income = 17087000000;
  data.annual.periods[0].metrics.weighted_average_diluted_shares = 2914000000;
  data.annual.periods[0].metrics.diluted_eps = 5.83;
  const incompatible = adaptProviderStock(data);
  assert.ok(incompatible.modelCompatibility.pe);
  data.annual.periods[0].metrics.diluted_eps = 5.86;
  assert.equal(adaptProviderStock(data).modelCompatibility.pe, undefined);
});

test("missing market prices, unknown classifications and currency incompatibility remain explicit", () => {
  const data = providerFixture();
  data.profile.market = null;
  const company = adaptProviderStock(data);
  assert.equal(company.price, null);
  assert.equal(company.marketCap, null);
  data.profile.company.is_bank = null;
  assert.equal(adaptProviderStock(data).isBank, null);
  data.annual.currency = "EUR";
  assert.equal(adaptProviderStock(data).currency, "EUR");
  assert.ok(adaptProviderStock(data).modelCompatibility.all);
  for (const period of data.annual.periods)
    for (const sources of Object.values(period.provenance ?? {}))
      for (const source of sources)
        if (source.unit?.startsWith("USD")) source.unit = source.unit.replace("USD", "EUR");
  assert.equal(adaptProviderStock(data).modelCompatibility.all, undefined);
});

test("API service handles safe structured errors, invalid JSON and network failures without fallback", async () => {
  await assert.rejects(
    fetchJson("/stocks/ACME", {
      fetcher: async () =>
        new Response(
          JSON.stringify({
            error: { code: "unknown_ticker", message: "Unknown ticker." },
          }),
          { status: 404 },
        ),
    }),
    (error) =>
      error instanceof ApiError &&
      error.status === 404 &&
      error.code === "unknown_ticker",
  );
  await assert.rejects(
    fetchJson("/stocks/ACME", {
      fetcher: async () => new Response("not json"),
    }),
    /unreadable response/,
  );
  await assert.rejects(
    fetchJson("/stocks/ACME", {
      fetcher: async () => {
        throw new Error("internal network detail");
      },
    }),
    /could not be reached/,
  );
  await assert.rejects(
    fetchJson("/stocks/ACME", {
      timeoutMs: 5,
      fetcher: (_url, { signal }) =>
        new Promise((_resolve, reject) =>
          signal.addEventListener("abort", () =>
            reject(new DOMException("Aborted", "AbortError")),
          ),
        ),
    }),
    (error) => error.code === "request_timeout",
  );
});

test("API loader preserves annual request failures and flags optional endpoint failures", async () => {
  const fixture = providerFixture("ACME");
  const fetcher = async (url) => {
    const suffix = new URL(url).pathname + new URL(url).search;
    const payload = suffix.endsWith("?period=annual")
      ? fixture.annual
      : suffix.endsWith("?period=quarterly")
        ? fixture.quarterly
        : suffix.endsWith("/data-status")
          ? fixture.dataStatus
          : fixture.profile;
    if (suffix.endsWith("/metrics"))
      return new Response(JSON.stringify({ detail: "Metrics unavailable." }), {
        status: 503,
      });
    return new Response(JSON.stringify(payload));
  };
  const loaded = await loadStock("ACME", { fetcher });
  assert.equal(loaded.metrics, null);
  assert.equal(loaded.requestWarnings[0].field, "metrics");
  assert.equal(loaded.profile.company.name, "API Fixture Corporation");
  await assert.rejects(
    loadStock("ACME", {
      fetcher: async () =>
        new Response(JSON.stringify({ detail: "Provider timeout." }), {
          status: 503,
        }),
    }),
    /Provider timeout/,
  );
});

test("API loader accepts canonical share-class aliases and rejects other company identities", async () => {
  const fixture = providerFixture("BRK-B");
  const fetcher = async (url) =>
    new Response(
      JSON.stringify(
        url.endsWith("?period=annual")
          ? fixture.annual
          : url.endsWith("?period=quarterly")
            ? fixture.quarterly
            : url.endsWith("/metrics")
              ? fixture.metrics
              : url.endsWith("/data-status")
                ? fixture.dataStatus
                : fixture.profile,
      ),
    );
  assert.equal(
    (await loadStock("BRK.B", { fetcher })).profile.company.ticker,
    "BRK-B",
  );
  await assert.rejects(
    loadStock("MSFT", { fetcher }),
    /does not match the requested company/,
  );
});

test("known multiple share classes and unverified class suffixes cannot use issuer-wide per-share valuations", () => {
  for (const [ticker, multiple] of [
    ["BRK-B", true],
    ["GOOG", true],
    ["BRK-B", null],
  ]) {
    const fixture = providerFixture(ticker);
    fixture.profile.company.has_multiple_share_classes = multiple;
    const company = adaptProviderStock(fixture);
    assert.equal(company.latest.eps, 10);
    assert.equal(company.latest.netIncome / company.latest.shares, 10);
    assert.ok(company.modelCompatibility.all);
    assert.ok(
      company.warnings.some(
        (warning) => warning.code === "unverified_share_class_basis",
      ),
    );
  }
});

test("noncontrolling equity scope excludes book-value models and duplicate fiscal-year bases exclude all valuations", () => {
  const fixture = providerFixture("JPM");
  fixture.profile.company.is_bank = true;
  fixture.annual.periods[0].provenance.shareholders_equity = [
    {
      concept:
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
      unit: "USD",
      value: 500000000,
    },
  ];
  const company = adaptProviderStock(fixture);
  for (const id of ["pb", "residual"])
    assert.ok(company.modelCompatibility[id]);
  fixture.profile.company.is_bank = false;
  fixture.annual.periods.push({
    ...fixture.annual.periods[0],
    start_date: "2024-12-30",
  });
  const ambiguous = adaptProviderStock(fixture);
  assert.ok(
    ambiguous.warnings.some(
      (warning) => warning.code === "ambiguous_annual_basis",
    ),
  );
  assert.ok(ambiguous.modelCompatibility.all);
});
