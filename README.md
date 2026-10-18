# Fairworth — Phase 6

A React/JavaScript stock research dashboard with a FastAPI financial data and Python valuation service, PostgreSQL persistence, SEC EDGAR ingestion, and an optional credentialed market data adapter. Provider mode calculates all valuations in Python; Demo mode preserves the existing JavaScript formulas and fictional data. The Phase 1 landing page is preserved, and API failures never silently fall back to demonstrations.

The [Phase 6 implementation and verification report](docs/phase6-valuation-accuracy.md) documents verified financial scope mappings, complete-debt safeguards, fiscal forecast alignment, versioned evidence, coverage/quality/confidence diagnostics and the expandable data-completeness dashboard. The [internal audit](docs/phase6-internal-audit.md) records the evidence and priorities established before implementation. Four-company results use explicitly dated public fixtures: additional fields improve inspection while AAPL/MSFT retain single-model policy estimates and NVDA/ORCL retain legitimate blockers. No fresh provider or OpenAI requests are part of Phase 6 verification.

The [Phase 4.5 implementation and verification report](docs/phase45-automatic-valuation.md) documents automatic historical valuation benchmarks, split-compatible forecasts, dated discount-rate inputs, source quality, classifications, four-company results, tests and remaining limitations. AAPL and MSFT now support automatic single-model, policy-based illustrative P/E estimates with the verified source snapshots. NVDA and ORCL retain explicit evidence blockers. The [initial diagnostic matrix](docs/phase45-diagnostic-audit.md) explains all 44 company/model combinations; the [Phase 4 report](docs/phase4-valuation-engine.md) preserves the original model architecture and mathematical verification.

The [Phase 5 AI research implementation and verification report](docs/phase5-ai-research.md) documents the source-grounded report/chat architecture, strict claim checks, SEC text coverage, usage limits and mocked versus live verification. AI generation is disabled by default and requires an explicitly configured OpenAI model and server-only API key.

The [MSFT research repair report](docs/phase5-msft-research-fixes.md) records evidence-bound numerical prose, grouped historical diagnostics, the shares/debt audit and bounded live-chat failures followed by deterministic category checks. It preserves the illustrative valuation and documents the remaining live-verification limitation.

The [category and uncertainty repair](docs/phase5-category-validation.md) documents the subsequent captured `interpretation` / `documented` failure, complete allowed classification matrix, schema enforcement, offline regressions and remaining semantic-validation limits.

The [typed evidence binding repair](docs/phase5-binding-validation.md) documents the retained v6 MSFT binding failures, prompt v7's request-scoped eligible-ID schema, server-owned rendering and strict offline regressions. No live AI request is part of that repair.

The [citation coverage repair](docs/phase5-citation-coverage.md) documents prompt v8's server-derived citations for explicitly selected, eligible typed references. The exact retained v7 failure now passes offline with complete provenance; independent financial and privacy checks remain strict.

The [Phase 5.1 presentation report](docs/phase5-1-presentation.md) documents prompt v9, safe typed-segment spacing, display-only financial rounding, explicit quote observation dates and clearer findings/source/limitation disclosures. The exact successful v8 MSFT response is retained and replayed offline without new OpenAI requests.

## Run locally

Use Node.js 22.12 or newer and npm. This implementation was verified with Node.js 26.3.0.

```bash
npm install
npm run dev
```

Open the URL printed by Vite, normally `http://localhost:5173`. Visit `/dashboard` for Microsoft or `/stocks/AAPL` for another company. Demonstration datasets are MSFT, AAPL, NVDA, GOOG, AMZN, TSLA, ORCL, JPM, KO, and O. The frontend runs independently in demonstration mode; the backend setup below enables provider mode.

```bash
npm run lint
npm run build
npm run preview
```

The production build is written to `dist/`. React Router uses browser history; a future host must serve `index.html` for application routes.

## Tests and verification

```bash
npx playwright install chromium
npm test
```

`npm test` runs calculation and provider-compatibility tests using Node's built-in test runner, followed by Playwright tests across desktop Chromium and Chromium with mobile viewport/touch emulation. They can also be run separately with `npm run test:unit` and `npm run test:e2e`. Provider browser tests mock API responses and need no financial credentials.

Independent Python model tests verify all 11 models, financial contracts, source/period compatibility, assumptions, weighting, scenarios, sensitivity, reverse DCF, missing inputs, and API persistence boundaries. JavaScript tests preserve Demo formulas and verify Provider transport/presentation without independent Provider arithmetic. Browser tests cover the existing landing/dashboard functionality plus Python authority, resets, manual prices, failures, stale-response protection, and desktop/mobile layout. Browser concurrency is bounded to two workers.

Responsive checks cover widths of 320, 390, 768, 1024, and 1440 pixels. Financial tables scroll within their containers. Desktop and mobile dashboard screenshots were visually reviewed, and sampled rendered text was checked for WCAG AA contrast. The shared text colors remain headings `#111111`, body `#333333`, labels `#444444`, and captions `#525252`.

Playwright builds fresh production assets and starts a dedicated Vite preview server at `http://127.0.0.1:4173` with a strict port. It never reuses or interrupts the development server on port 5173. This keeps backend changes and development hot reloads from resetting browser tests. Screenshots and failure traces are written to ignored `test-results/`. Mobile emulation does not verify Safari or physical iOS devices.

## Demonstration dashboard behavior

- Company overview, visible demo-data label, illustrative price, market capitalization, and update label.
- Weighted valuation, upside/downside, separately defined margin of safety, bear/bull range, and enabled/contributing method counts.
- Eleven methods with applicability rules, structured warnings, details, editable weights, enable/disable controls, and a horizontal comparison chart with market and weighted-value reference lines.
- Model-specific assumptions with explicit units, defaults, sliders, numeric inputs, validation, and reset. Reset affects all assumptions in the active scenario; model weights have their own reset.
- Independently editable bear, base, and bull assumptions. Model selection and weights are shared across scenarios; market price remains constant.
- FCFF WACC/terminal-growth and forward EPS/P/E sensitivity matrices. Their outlined centers use the edited **base** assumptions, regardless of the active scenario.
- Three annual financial statements for FY2023–FY2025, with no invented quarterly view. Historical values remain fixed when forward assumptions change.
- Separate reverse DCF diagnostic and clearly labeled static research commentary.

Changing tickers creates a fresh workspace. State is in memory and resets on page reload. Unsupported tickers show a clear unavailable-data message. Search accepts ticker or company names, suggestions, keyboard selection, and Enter; syntactically valid tickers are not verified against an exchange.

## Financial conventions and limitations

Monetary totals and diluted shares are both stored in **millions**, so their quotient is USD per share. Growth and discount rates are decimals internally; editors show percentages. Intermediate calculation values are not rounded for display.

| Method            | Demonstration calculation                                                                                                               |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| FCFF DCF          | Project annual FCFF, discount at WACC, add a Gordon terminal value, subtract debt and other claims, add cash, divide by diluted shares. |
| FCFE DCF          | Project equity cash flows and discount at cost of equity, including a Gordon terminal value. No second debt deduction.                  |
| Forward P/E       | Current net income / edited shares × (1 + EPS growth) × target P/E.                                                                     |
| EV/EBITDA         | Forecast revenue × explicit EBITDA margin × target multiple, then convert enterprise value to equity.                                   |
| EV/Revenue        | Forecast revenue × target multiple, then convert enterprise value to equity.                                                            |
| PEG               | Forward EPS × target PEG × EPS growth in percentage points; 12% growth uses 12, rather than 0.12.                                       |
| Graham            | Square root of 22.5 × positive current EPS × positive book value/share.                                                                 |
| Dividend discount | Next-year dividend/share / (cost of equity − dividend growth).                                                                          |
| Residual income   | Current book value/share plus discounted annual earnings less equity capital charges and a terminal residual-income value.              |
| Price-to-book     | Book equity / edited shares × target P/B.                                                                                               |
| REIT AFFO         | Current total AFFO / edited shares × target P/AFFO; only the REIT dataset is eligible.                                                  |

DCF uses annual end-of-year discounting and a constant growth rate over the explicit forecast period. Terminal growth must be below the discount rate. FCFE is a simplified operating cash flow minus capex proxy with zero net borrowing. FCFF adds interest expense × (1 − a fictional 21% tax rate). These proxies are not a full forecast of working capital, financing, or operating taxes.

Residual income assumes clean surplus: retained earnings increase book equity, ROE is constant within the explicit period, and there are no buybacks, new issuance, or other comprehensive income. Terminal residual income grows at the selected terminal rate after the final projected year. It does not forecast an indefinite constant ROE beyond that point.

Applicable methods depend on company characteristics and available positive financial metrics. The bank uses book-equity/dividend approaches; the REIT uses AFFO; the loss-making, negative-cash-flow example uses EV/Revenue. Graham is restricted to datasets explicitly marked suitable. These are demonstration rules, not universal suitability recommendations.

Only enabled, valid estimates with positive raw weights contribute. Weights normalize to one across those methods. Invalid enabled methods are excluded with a visible warning; zero weights, negative weights, and no enabled methods have explicit unavailable states. Missing values are represented as `null`, never substituted with zero.

```text
Upside/downside (%) = (fair value / market price − 1) × 100
Margin of safety (%) = (fair value − market price) / fair value × 100
```

Bear and bull cases change growth, profitability, discount rates, and multiples. The resulting range is not a statistical confidence interval. Some fixed heuristics, such as Graham, do not vary with scenario growth assumptions.

Reverse DCF uses the same FCFF projections and equity bridge, solving by bisection within −50% to +100% annual growth. Signed equity values at the search endpoints are allowed; a positive market-price solution must be bracketed. Invalid inputs or an unbracketed solution show warnings. Reverse DCF never contributes to the weighted fair value.

Formula references: [Damodaran's valuation materials](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/lectures/val.html), [FCFE materials](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/lectures/fcfe.html), and [CFA Institute's residual income overview](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/residual-income-valuation). The implementation deliberately simplifies these frameworks for a frontend demonstration.

## Routes

| Route                                          | Purpose                                               |
| ---------------------------------------------- | ----------------------------------------------------- |
| `/`                                            | Preserved landing page                                |
| `/dashboard`                                   | Microsoft demonstration dashboard                     |
| `/stocks/:ticker`                              | Ticker-specific dashboard or unavailable-data message |
| `/signin`                                      | Account placeholder                                   |
| `/methodology`, `/about`, `/privacy`, `/terms` | Existing information/placeholder pages                |
| Other paths                                    | Friendly page-not-found view                          |

## Phase 2 files

| Created                                                                         | Responsibility                                                        |
| ------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `src/components/dashboard/AnalysisWorkspace.jsx`                                | Dashboard composition and selected model                              |
| `src/components/dashboard/DashboardLayout.jsx`                                  | Research navbar, desktop sidebar, and mobile section navigation       |
| `src/components/dashboard/CompanyHeader.jsx`, `ValuationSummary.jsx`            | Company metadata and derived summary                                  |
| `src/components/dashboard/ModelComparison.jsx`, `ComparisonChart.jsx`           | Model controls, details, and lazy-loaded chart                        |
| `src/components/dashboard/AssumptionEditor.jsx`, `ScenarioAnalysis.jsx`         | Assumption edits and independent scenarios                            |
| `src/components/dashboard/SensitivityTable.jsx`, `ReverseDCF.jsx`               | Formula-based diagnostics                                             |
| `src/components/dashboard/FinancialStatements.jsx`, `ResearchInsights.jsx`      | Annual statements and static commentary                               |
| `src/pages/Dashboard.jsx`, `StockAnalysis.jsx`                                  | Route entry points, replacing the former dashboard/stock placeholders |
| `src/data/mockFinancials.js`, `modelDefinitions.js`, `assumptionDefinitions.js` | Distinct datasets, model metadata, and assumption ranges/units        |
| `src/valuation/`                                                                | Pure formula modules, validation, selection, scenarios, and weighting |
| `src/hooks/useValuation.js`                                                     | Source state and memoized derived calculations                        |
| `src/lib/stockRepository.js`, `financialFormatting.js`                          | Data access boundary and finite-safe financial formatting             |
| `src/dashboard.css`                                                             | Scoped dashboard styles reusing existing shared tokens                |
| `tests/unit/valuation.test.js`, `tests/dashboard.spec.js`                       | Calculation and dashboard browser tests                               |

| Modified                                 | Purpose                                                                 |
| ---------------------------------------- | ----------------------------------------------------------------------- |
| `src/App.jsx`, `src/main.jsx`            | Connect dashboard routes/navbar and import scoped styles                |
| `src/components/landing/StockSearch.jsx` | Reuse search in the dashboard while retaining landing behavior          |
| `src/data/mockStocks.js`                 | Add JPM, KO, and O suggestions                                          |
| `tests/landing.spec.js`                  | Verify existing landing behavior against the completed dashboard routes |
| `playwright.config.js`, `package.json`   | Separate browser specs from unit tests and run both suites              |
| `README.md`                              | Phase 2 run instructions, architecture, and formula conventions         |

The landing page, shared `src/index.css`, footer, fonts, and brand components retain the Phase 1 design. Existing JavaScript shadcn/ui buttons and inputs are reused. No Phase 2 dependencies were added; exact dependency versions remain in `package-lock.json`. All authored frontend code is `.js` or `.jsx`, with no TypeScript configuration. The Phase 3 backend is Python.

Demonstration data access remains isolated in `getStockData()`. Provider data uses the centralized API service and an explicit compatibility adapter. Financial calculations live outside presentation components and return structured results; React's built-in state keeps derived values out of duplicated state.

## Phase 3 architecture

The backend is a modular monolith. Routes validate inputs and apply Pydantic v2 response schemas. Services coordinate shared asynchronous HTTP providers, normalization, derived financial metrics, a persistent TTL cache, and SQLAlchemy repositories. PostgreSQL stores companies, original financial observations, normalized snapshots, market observations, and cache entries. Alembic owns schema changes; application startup does not create tables.

| Files | Responsibility |
| --- | --- |
| `backend/app/main.py`, `core/`, `api/` | Application lifecycle, settings, connection pool, CORS, safe errors, and REST routes |
| `backend/app/providers/` | Replaceable SEC and market interfaces; fixed-host HTTP requests, throttling, bounded retries, and timeouts |
| `backend/app/services/normalization.py`, `metrics.py` | Fiscal-period selection, unit validation, source preservation, quarterly derivations, financial ratios, and warnings |
| `backend/app/services/company_service.py`, `financial_service.py`, `cache_service.py` | Provider coordination, freshness, and cached fallback handling |
| `backend/app/models/`, `repositories/`, `schemas/` | PostgreSQL persistence, duplicate prevention, historical snapshots, and API schemas |
| `backend/alembic/`, `alembic.ini` | Versioned database migration |
| `backend/tests/` | Offline provider, normalization, cache, API, database, and optional PostgreSQL tests |
| `src/services/api.js`, `src/lib/providerCompatibility.js` | Backend-only fetch boundary and absolute-unit to Phase 2 compatibility conversion |
| `src/context/`, `StockDataWorkspace.jsx`, `DataModeControl.jsx`, `DataQualityNotice.jsx` | Explicit data mode, asynchronous loading/errors, and source/freshness notices |
| `docker-compose.yml`, `.env.example`, `backend/.env.example`, `requirements*.txt` | Local database, configuration examples, and backend dependency versions |

Existing dashboard components now accept missing reported fields, show annual/quarterly periods when available, and distinguish provider data from fictional research commentary. No frontend dependency was added.

## Backend installation and PostgreSQL

Use Python 3.12 or newer, Docker with Compose, and the existing Node/npm frontend. The local implementation was verified on Python 3.12.10 and PostgreSQL 16. Install `backend/requirements.lock.txt` to reproduce the tested Python environment; `backend/requirements.txt` contains the supported dependency ranges. The stack includes FastAPI, Uvicorn, Pydantic v2/settings, SQLAlchemy 2.x, Alembic, psycopg, httpx, pandas, NumPy, pytest, and pytest-asyncio.

From the repository root, prepare the environment files and database. Keep any existing local configuration rather than overwriting it.

Windows PowerShell:

```powershell
Copy-Item .env.example .env
Copy-Item backend/.env.example backend/.env
python -m venv backend/.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.lock.txt
docker compose up -d postgres
python -m alembic -c backend/alembic.ini upgrade head
python -m alembic -c backend/alembic.ini check
python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

If PowerShell activation is unavailable, use `.\backend\.venv\Scripts\python.exe` in place of `python` after creating the environment; changing the system execution policy is unnecessary.

macOS/Linux:

```bash
cp .env.example .env
cp backend/.env.example backend/.env
python3 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r backend/requirements.lock.txt
docker compose up -d postgres
python -m alembic -c backend/alembic.ini upgrade head
python -m alembic -c backend/alembic.ini check
python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

Compose binds PostgreSQL to `127.0.0.1:5440` and persists it in the `fairworth_postgres` volume. Defaults are database/user `fairworth` and development password `fairworth_local`. These are local development defaults. If you change `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, or `POSTGRES_PORT` in the root `.env`, update `DATABASE_URL` in `backend/.env` to match. Existing PostgreSQL volumes retain their original credentials. Stop the service with `docker compose stop postgres`; retain the volume to preserve data.

In another terminal, run `npm install` and `npm run dev`. The backend serves interactive API documentation at `http://127.0.0.1:8000/docs` and its OpenAPI schema at `/openapi.json`. Backend settings always load `backend/.env`, regardless of the launch directory.

## Configuration and data providers

Root `.env` contains public frontend settings and Compose configuration. `VITE_API_BASE_URL=http://127.0.0.1:8000` sets the backend URL. `VITE_DATA_MODE=demo` is the initial mode; use `provider` to opt into provider mode by default. The dashboard selector remembers an explicit choice for the current browser tab. Restart Vite after changing environment settings. Every `VITE_` variable is public: provider credentials belong only in `backend/.env`.

| Backend setting | Default / purpose |
| --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://fairworth:fairworth_local@127.0.0.1:5440/fairworth` |
| `SEC_USER_AGENT` | Empty; configure an identifying product/organization and your monitored email address before requesting SEC data |
| `SEC_MIN_INTERVAL_SECONDS` | `0.2`; minimum interval between SEC requests |
| `PROVIDER_TIMEOUT_SECONDS`, `PROVIDER_RETRIES` | `20`, `2`; bounded request timeout and retries |
| `MARKET_DATA_PROVIDER`, `FMP_API_KEY` | `disabled`, empty; select `fmp` only with your own authorized API key |
| `CORS_ORIGINS` | JSON list of the two local Vite origins; explicit origins only |
| `COMPANY_CACHE_TTL_SECONDS` | `86400`; identifiers and metadata |
| `SEC_CACHE_TTL_SECONDS` | `21600`; normalized SEC data and its persisted source facts |
| `MARKET_CACHE_TTL_SECONDS` | `300`; latest available quotes, with the original price timestamp |
| `HISTORICAL_CACHE_TTL_SECONDS` | `3600`; market history |
| `MARKET_MAX_AGE_SECONDS` | `172800`; warning threshold for old market observations |
| `API_HISTORY_LIMIT` | `365`; configured maximum historical price observations, adjustable up to 2000 |

SEC EDGAR is the free primary financial statement source and does not require an API key. The adapter uses the official ticker directory, zero-padded CIK submissions, and companyfacts endpoints. SEC requires fair access and limits each operator to 10 requests/second across machines; keep the local backend to one worker so its in-process request limiter applies consistently. Deployments with multiple workers would need shared rate coordination. See the [official SEC API guide](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) and [developer access guidance](https://www.sec.gov/about/developer-resources).

The optional FMP stable API adapter supports company profiles, quotes, historical prices, and dividend observations through a replaceable market interface. FMP requires an API key, and available endpoints, access, and redistribution depend on the subscription and licensing rights. Configure your own authorized account; see the [FMP quickstart and access guidance](https://site.financialmodelingprep.com/developer/docs/quickstart). The application does not scrape market websites. Dividend observations are exposed at the provider abstraction for later use; they are not used to infer stable dividends or populate valuation inputs.

With providers unconfigured, the backend still starts and reports database health. SEC requests return a structured configuration error. A configured SEC source can supply financial statements even when market data is unavailable; missing prices remain `null`. Provider mode displays failures and offers an explicit demonstration-mode choice.

## Normalization, provenance, and freshness

API financial amounts retain absolute `USD`, per-share figures use `USD/shares`, and share counts use `shares`. Ratios are decimal fractions. The frontend compatibility layer converts monetary totals and share counts to millions once; EPS remains USD/share. No exchange-rate conversion is invented. Non-USD or incompatible units are excluded with warnings.

Annual selection uses exact duration dates and native fiscal filing contexts. Comparative observations retain their actual reporting dates rather than inheriting the later filing's fiscal year. Later unambiguous observations for an already identified period can revise the selected value with a restatement notice. Each normalized field preserves original concepts, taxonomy, units, dates, filing form, accession, reported value, and available frame. Conflicting values remain unavailable.

Quarterly statements use native standalone quarters, or differences of aligned year-to-date intervals with compatible source contexts. Q4 requires an aligned annual and nine-month basis. EPS and weighted shares are never subtracted. Incompatible amendments, missing preceding intervals, and unusual calendars produce warnings rather than fabricated standalone values. Missing capex or operating cash flow leaves free cash flow unavailable. Complete compatible debt components are required, and current maturities are not counted twice. Negative earnings, equity, operating cash flow, and free cash flow can be legitimate.

Metrics use matching fiscal periods; quarterly growth compares the same fiscal quarter in the previous year. Annual ROE uses compatible beginning and ending equity. Missing/nonpositive denominators, large changes, absent shares, currency mismatches, and balance-sheet discrepancies produce structured quality notices.

Original observations and changed normalized snapshots are preserved with foreign keys and content-based uniqueness. Refreshing identical provider data avoids duplicate financial records. Cache expiry triggers provider refresh, so newly published filings become eligible on the next request after the configured TTL. There is no filing webhook or background ingestion scheduler in Phase 3. On a provider failure, an expired cache is returned only with `status: "stale"`, its original retrieval/price timestamps, and a visible failure warning; uncached failures return a safe structured error.

Raw SEC facts are cached by CIK, while normalized persistence is tracked per ticker. Two listed classes of the same issuer reuse one upstream facts request and each retain database snapshots. Derived cache entries preserve the upstream retrieval time and cannot promote stale raw facts to fresh data.

## Provider valuation compatibility

Reported facts and forward assumptions are separate. Provider mode retrieves Python defaults with historical estimates, clearly labeled configurable benchmarks, and explicit unavailable inputs. Unsourced target multiples require user input. Annual diluted weighted shares retain their reporting period and are not labeled current market shares. Missing classifications, common-equity scope, and incompatible earnings bases leave affected methods unavailable; explicit user forecasts and confirmations are identified as assumptions.

Automatic P/E benchmarks use original SEC filing vintages, prices strictly after publication, verified split compatibility, and at least three independent fiscal-year samples. Their historical forward EPS proxies and growth limits are disclosed. They never use today's quote to choose a fair-value target. Default values are classified as evidence-supported, policy-based illustrative, user-defined, or unavailable, with weighted composition and single-model warnings. Dated SEC common shares remain separate from annual weighted shares; verified zero claims remain separate from unknown aggregate scope.

Multiple listed share classes produce an explicit unverified-share-basis warning. Issuer-wide earnings and shares cannot be assumed to match a specific class's quote. Historical per-share valuations require compatible class evidence or explicit user confirmation; an explicit quoted-class forward forecast remains a labeled user assumption. Ambiguous annual periods and equity including noncontrolling interests are also excluded from affected valuation inputs. Parent-specific net income and equity are not replaced by consolidated NCI-inclusive concepts.

SEC operating cash flow minus capex is displayed as sourced free cash flow and is never automatically treated as FCFF or FCFE. Python models require complete components, explicit defensible forecasts, and validated enterprise/common-equity bridges. Missing claims, net borrowing, AFFO and dividend stability are not assumed. Manual comparison prices do not overwrite provider quotes or stored snapshots. Existing JavaScript formulas remain unchanged and are used only in Demo mode.

Financial and market observation dates are displayed separately; a current quote and the latest annual statements are not presented as the same reporting date. A provider price is never labeled live merely because it was recently fetched. Provider mode research insights show data-availability notices instead of fictional commentary.

## API endpoints

| Method/path | Response |
| --- | --- |
| `GET /api/health` | Backend status and database/schema readiness; HTTP 503 if unavailable |
| `GET /api/stocks/search?q=MSFT&limit=10` | Relevant ticker/name matches, CIK, and exchange; maximum 50 |
| `GET /api/stocks/{ticker}` | SEC company identity, optional market profile/quote, observation timestamps, source references, and warnings |
| `GET /api/stocks/{ticker}/financials?period=annual&limit=10` | Annual or quarterly normalized periods with field-level provenance; maximum 20 |
| `GET /api/stocks/{ticker}/metrics?period=annual&limit=10` | Period-aligned ratios and historical growth; maximum 20 |
| `GET /api/stocks/{ticker}/prices?limit=365` | Available market history with provider and retrieval metadata; request maximum 2000, further capped by `API_HISTORY_LIMIT` (365 by default) |
| `GET /api/stocks/{ticker}/data-status` | Available periods, missing fields, financial/price updates, provider status, and quality warnings |

Tickers are validated before any provider request. Share-class dot/hyphen aliases resolve through the SEC mapping. Envelopes expose `status` and structured `warnings`; errors use `{ "error": { "code": "...", "message": "..." } }`. Invalid requests return 422, unsupported symbols 404, and unavailable providers/databases generally 503. Unexpected failures do not expose internal traces. CORS is configurable and rejects wildcard origins. Queries are parameterized, provider hosts are fixed, and HTTP client request URLs are not logged at INFO level because market API URLs carry credentials.

## Backend tests and integration verification

The subsequent [live verification report](docs/live-data-verification.md) records successful SEC checks for AAPL, MSFT, NVDA, and ORCL; actual PostgreSQL persistence; and desktop/mobile Provider-mode verification. FMP profiles work for all four, while quotes/history/dividends work for AAPL/MSFT/NVDA and return subscription restrictions for ORCL. The original Phase 3 verification notes below describe the earlier mocked run.

The default suite uses synthetic SEC fixtures, mocked HTTP transports, and isolated SQLite persistence. It never calls external financial APIs and needs no credentials.

```bash
python -m pytest backend/tests -q
python -m alembic -c backend/alembic.ini check
npm test
npm run lint
npm run build
```

The optional PostgreSQL test exercises the actual PostgreSQL migration, JSONB/Numeric storage, deduplication, provenance, history, cache fallback, schema comparison, and downgrade. It requires a dedicated empty database whose name ends in `_test`; it never runs against the application database. Create it with `docker compose exec postgres createdb -U fairworth fairworth_test`, then run:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://fairworth:fairworth_local@127.0.0.1:5440/fairworth_test'
python -m pytest backend/tests/test_postgres.py -q
Remove-Item Env:TEST_DATABASE_URL
```

```bash
TEST_DATABASE_URL=postgresql+psycopg://fairworth:fairworth_local@127.0.0.1:5440/fairworth_test python -m pytest backend/tests/test_postgres.py -q
```

Actual local PostgreSQL migration/schema checks and mocked provider integration are verified for this implementation. Live SEC and FMP requests were not verified: the project owner selected mocked verification and no identifying SEC contact or licensed market key was configured. No real financial data is seeded into the application database by tests.

Final checks passed: 118 backend tests including the PostgreSQL integration, 30 JavaScript unit tests, 44 desktop/mobile browser tests, ESLint, and the Vite production build. A local HTTP integration check connected the production frontend to a synthetic-provider FastAPI service at widths 320, 390, 768, 1024, and 1440 pixels, with no runtime exceptions or page overflow; explicit 10% EPS growth and a target P/E of 15 produced the independently expected $165 estimate. PostgreSQL schema comparison reported no pending migration changes. The backend test dependency emitted one upstream Starlette TestClient/httpx deprecation warning; no checks failed.

## Known Phase 3 limitations

- Normalization supports selected US GAAP/DEI concepts in USD. SEC companyfacts omits custom extensions and segmented contexts; unsupported concepts, IFRS, specialized industry statements, foreign currencies, and unusual transition periods require additional adapters or mapping work. Missing data remains explicit.
- The latest usable annual period drives valuations. Quarterly data is a historical statement view; no rolling TTM valuation or inferred annualization is introduced.
- Filings refresh on demand after cache expiry. There is no global distributed rate limiter or production ingestion scheduler.
- Market data requires configured licensed access. Quotes may be delayed or last-close values, and market share counts need not match diluted weighted financial shares. Differences and timestamps are shown.
- There is no currency conversion, inferred dividend stability, or sourced AFFO calculation. Python supports complete FCFF/FCFE models, but incomplete provider components still require explicit analyst forecasts or remain unavailable.
- Mobile checks use Chromium emulation; physical devices and Safari were not verified. Information-policy pages remain placeholders.

## Phase boundary

Phase 6 improves financial-data interpretation, deterministic valuation safeguards and diagnostic presentation around the existing source-grounded AI research service. It does not implement authentication, watchlists, payments, subscriptions or portfolios. AI research remains optional; data and valuation tests use mocked OpenAI responses. Changes are not automatically committed or pushed. Fresh provider audits and any live AI verification require separate explicit authorization.
