# Phase 3 live financial data integration and verification

Verification date: 2026-10-14 (Asia/Kuala_Lumpur).

**Status: live SEC retrieval, entitled FMP endpoints, PostgreSQL persistence, and desktop/mobile Provider mode are verified. ORCL market endpoints are restricted by the configured FMP subscription and remain explicitly unavailable.**

## Configuration and connections

The saved `backend/.env` now loads successfully from the exact configured path. SEC identification and FMP authentication are configured, `MARKET_DATA_PROVIDER=fmp`, and the configured PostgreSQL connection is healthy on port 5440. FastAPI was restarted after the environment change. No credential values, identifying email address, or credentialed URLs are included in this report.

| Connection | Actual live result |
| --- | --- |
| SEC EDGAR | Ticker directory, submissions, and companyfacts requests succeeded for all four companies |
| FMP | Profiles succeeded for all four; quotes, history, and dividends succeeded for AAPL/MSFT/NVDA; ORCL market requests returned HTTP 402 |
| PostgreSQL | Connected; migration `0001_financial_data` applied; Alembic reports no schema drift |
| FastAPI | Running at `http://127.0.0.1:8000`; health returns HTTP 200 with database ready |
| React | Running at `http://127.0.0.1:5173`; actual API-backed Provider mode verified |

SEC requests used the configured identifying User-Agent and the shared request limiter. FMP request logs suppress credentialed URLs. The environment file and local verification artifacts are ignored by Git.

## Company and provider results

| Ticker | CIK | Latest annual period | Latest quarter | SEC periods (annual / quarterly) | FMP profile / quote / history / dividends |
| --- | --- | --- | --- | --- | --- |
| AAPL | 0000320193 | FY2025: 2024-09-29 to 2025-09-27 | FY2026 Q3, ended 2026-06-27 | 17 / 71 | All succeeded |
| MSFT | 0000789019 | FY2026: 2025-07-01 to 2026-06-30 | FY2026 Q4, ended 2026-06-30 | 17 / 69 | All succeeded |
| NVDA | 0001045810 | FY2026: 2025-01-27 to 2026-01-25 | FY2027 Q2, ended 2026-07-26 | 17 / 71 | All succeeded |
| ORCL | 0001341439 | FY2026: 2025-06-01 to 2026-05-31 | FY2027 Q1, ended 2026-08-31 | 17 / 69 | Profile succeeded; quote/history/dividends HTTP 402 |

The three entitled historical-price API responses returned 365 observations each through FastAPI. Direct dividend probes returned ten observations each. Dividend records retain declaration, record, and payment dates; announced future dividends are not represented as already-paid cash flows.

Latest available quote observations were timestamped 2026-10-13: AAPL and MSFT at 20:00:01 UTC, NVDA at 23:59:57 UTC. These are provider observation times, separate from API retrieval times; this report does not claim real-time quotes. FMP market capitalization was supplied for the three quoted stocks. The verified quote responses did not supply current shares outstanding; those values remain null, while SEC period-end and diluted weighted shares remain available for their proper reporting dates.

## Financial samples and accuracy

Amounts below are USD billions, rounded for this report. API totals retain absolute USD; EPS retains USD/share and shares retain shares. The frontend converts monetary totals and share counts to millions once.

| Ticker | Revenue | Net income | Operating income | Operating cash flow | Capex | Free cash flow | Assets | Liabilities | Parent equity | Total debt | Source |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| AAPL | 416.161 | 112.010 | 133.050 | 111.482 | 12.715 | 98.767 | 359.241 | 285.508 | 73.733 | 98.657 | [SEC companyfacts](https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json) |
| MSFT | 331.839 | 133.749 | 155.237 | 182.935 | 115.948 | 66.987 | 758.376 | 315.989 | 442.387 | Unavailable | [SEC companyfacts](https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json) |
| NVDA | 215.938 | 120.067 | 130.387 | 102.718 | 6.042 | 96.676 | 206.803 | 49.510 | 157.293 | 8.468 | [SEC companyfacts](https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json) |
| ORCL | 67.357 | 17.087 | 20.606 | 31.977 | 55.663 | -23.686 | 261.759 | 218.703 | 42.508 | 129.541 | [SEC companyfacts](https://data.sec.gov/api/xbrl/companyfacts/CIK0001341439.json) |

495 selected-field and derived-value checks across each latest annual period and its four latest quarters found **zero discrepancies** against the downloaded original SEC observations and their arithmetic coefficients. Checks matched concept, taxonomy, unit, start/end dates, accession, and reported value. Free cash flow was independently recomputed as operating cash flow minus the sourced capex amount. Quarterly derived values were checked against aligned YTD source intervals; EPS and weighted shares were not differenced.

Annual revenue growth was verified on aligned fiscal periods: AAPL 6.4255%, MSFT 17.7887%, NVDA 65.4735%, ORCL 17.3487%. Negative ORCL free cash flow was preserved. Balance-sheet derivations use compatible dates/accessions and consolidated equity when noncontrolling interests are present.

## Confirmed defects fixed

1. **NVIDIA capex:** its reported `PaymentsToAcquireProductiveAssets` concept was previously unmapped, leaving capex and FCF unavailable. The verified concept covers property/equipment, software, and other intangible assets. It now maps with an explicit scope warning; FY2026 capex is $6.042B and FCF is $96.676B.
2. **Debt mappings:** added the observed `CommercialPaper` alternative and the explicit `DebtLongtermAndShorttermCombinedAmount` total. Explicit totals take precedence; current debt is not added twice. AAPL and ORCL total debt are now available. MSFT complete total debt remains unavailable because a compatible short-term amount is not reported by the mapped facts; missing borrowing is not assumed to be zero.
3. **Oracle liabilities:** its standard facts lacked a direct `Liabilities` amount. Compatible `LiabilitiesAndStockholdersEquity` less `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` now yields $218.703B. Parent equity is preserved separately; using it for the subtraction would overstate liabilities by the noncontrolling interest.
4. **Oracle fiscal year:** the June-August 2026 quarter carried source `fy=2026`. Its preceding completed fiscal year ended May 31, 2026, so the aligned new quarter is labeled FY2027 Q1. The source FY remains unchanged in provenance, with a mismatch notice. This fixes quarter comparison labels without modifying financial values.
5. **Derivation provenance:** composed signed coefficients now preserve YTD subtraction and capex/equity subtraction, allowing derived amounts to be reproduced from original observations. Normalized caches are versioned so old mappings do not remain fresh after a normalization update.
6. **Subscription handling:** upstream HTTP 402 now produces the safe code `provider_subscription_required`. Nonretryable access failures are cached per endpoint and symbol for one hour in the provider instance, so ORCL restrictions do not disable AAPL/MSFT/NVDA and repeated dashboard requests do not repeatedly contact blocked endpoints. Optional profile failure no longer discards otherwise-entitled history or dividends.
7. **Earnings compatibility:** the former 1% EPS tolerance accepted ORCL net income / diluted weighted shares of approximately $5.86376 against reported EPS of $5.83. The adapter now retains only the two-cent absolute rounding tolerance, leaving materially incompatible earnings models unavailable. Core valuation formulas are unchanged.
8. **Mobile source notices:** expanded long SEC concept names caused page overflow. Scoped word wrapping fixes the source-notice text without changing layouts, spacing, font families, or colors. A browser regression covers the expanded notice.

## FastAPI endpoint results

29 actual local HTTP checks used real provider-backed data: **28 HTTP 200 responses and one expected HTTP 503 restriction**.

| Endpoint | AAPL | MSFT | NVDA | ORCL |
| --- | --- | --- | --- | --- |
| `/api/health` | HTTP 200, database ready (shared health check) | Same service | Same service | Same service |
| `/api/stocks/search?q={ticker}` | 200 | 200 | 200 | 200 |
| `/api/stocks/{ticker}` | 200; quote present | 200; quote present | 200; quote present | 200; SEC/profile present, quote null with subscription warning |
| `/financials?period=annual` | 200 | 200 | 200 | 200 |
| `/financials?period=quarterly` | 200 | 200 | 200 | 200 |
| `/metrics` | 200 | 200 | 200 | 200 |
| `/prices` | 200; 365 prices | 200; 365 prices | 200; 365 prices | 503; `provider_subscription_required` |
| `/data-status` | 200 | 200 | 200 | 200; restricted market status/warnings |

Financial responses report partial quality when historical fields/restatements/ambiguous contexts have notices; HTTP 200 does not mean every field is complete. Latest required annual fields are available for AAPL, NVDA, and ORCL. MSFT lists complete total debt as missing. Market share-count notices remain explicit. Initial full-history ingestion took roughly 10-12 seconds per company in this local run; subsequent cached financial/metric requests were substantially faster. These are local measurements, not a production benchmark.

## PostgreSQL persistence and credentials

Actual application records after ingestion and duplicate verification:

| Ticker | Financial facts | Financial snapshots | Market snapshots |
| --- | ---: | ---: | ---: |
| AAPL | 25,135 | 1 | 1 |
| MSFT | 32,671 | 1 | 1 |
| NVDA | 27,281 | 1 | 1 |
| ORCL | 26,350 | 1 | 0 |

Four company records, 111,437 financial facts, four financial snapshots, and three market snapshots were stored, with persisted cache records. ORCL has no fabricated market snapshot. Reingesting the same actual AAPL facts and normalized snapshot left all row counts unchanged. Stored original source/accession data and a UTC retrieval-timestamp sample were verified. An application cache scan found no FMP key, configured SEC User-Agent, or identifying contact email in its payloads.

Actual PostgreSQL integration tests also passed migration upgrade/check/downgrade, JSONB/Numeric storage, history, duplicate prevention, and stale-cache behavior in the dedicated disposable test database. That test uses synthetic records and is separate from the real application ingestion above.

## Actual frontend Provider-mode verification

Live search selected AAPL through the real backend directory. At 390px and 1440px, the dashboard displayed actual company identity, provider price/market capitalization, sourced statements and metrics, timestamps, and source notices. Annual and quarterly statement controls worked for real periods, including Oracle FY2027 Q1.

Forward inputs initially stayed blank. Explicit QA assumptions of 10% EPS growth and target P/E 15 produced the independently expected AAPL $123.17 estimate using reported net income and diluted weighted shares. This is a verification scenario, not a recommended valuation or a new default. The comparison chart updated, and bear/base/bull inputs remained independent. The P/E sensitivity matrix populated from the edited base case. Unsupported cash-flow/enterprise models remained unavailable instead of borrowing demonstration proxies.

ORCL displayed financial statements and profile information with its restricted quote unavailable. Its unverified multiple listed share-class basis and earnings mismatch keep affected valuations unavailable. Expanded source warnings remained inside the mobile viewport after the wrapping fix. No browser runtime exceptions or final page overflow were observed. No demonstration data was silently substituted.

## Automated checks versus live checks

| Check | Result | Scope |
| --- | --- | --- |
| Backend pytest | 125 passed | Mocked providers/synthetic financial fixtures plus actual dedicated PostgreSQL integration |
| Frontend unit tests | 31 passed | Deterministic formulas and mocked API/compatibility boundary |
| Browser regression suite | 46 passed | Desktop/mobile Chromium, mocked provider success/failure data |
| ESLint | Passed | Source analysis |
| Production build | Passed | Vite build |
| Alembic schema comparison | Passed | Actual configured application database |
| Four-company SEC/FMP probes | Completed with documented ORCL restrictions | Actual external requests using configured credentials |
| Four-company API and persistence | Passed with one expected restricted prices response | Actual local FastAPI, provider data, and PostgreSQL |
| Provider dashboard verification | Passed at 390px and 1440px | Actual backend/provider data, without route mocks |

An upstream Starlette TestClient/httpx deprecation warning remains in test output. No final checks failed. Earlier diagnostic attempts exposed a QA selector error and the source-notice overflow; both were corrected before the successful final checks.

## Remaining limits and boundaries

- ORCL quote, history, and dividend entitlement returns HTTP 402 under this key. Its SEC data and FMP profile remain available. Confirm the symbol-specific entitlement with FMP if these market features are needed; no purchase or provider switch was made. [Official FMP access guidance](https://site.financialmodelingprep.com/developer/docs/quickstart).
- Current shares outstanding were not supplied in the verified quote responses. SEC share counts retain their own reporting dates and are not replaced by market-cap/price inference.
- Complete MSFT debt remains missing rather than inferred from a missing zero short-term component. Other specialized/unmapped/custom concepts and uncertain historical periods remain explicit quality notices.
- FCFF, FCFE, AFFO, other claims, dividend stability, and business/share-class assumptions are not fabricated. Phase 3 continues to use the existing JavaScript engine where facts and user assumptions are compatible; there is no production Python valuation engine.
- Market data can be delayed/last-close and cache freshness is bounded by configured TTLs. Historical warnings do not become invented zero values. Physical mobile devices and Safari were not tested.

Five core valuation modules retain their preserved hashes. The Phase 1 landing page, shared text styles, and footer remain unchanged. No TypeScript, OpenAI integration, or Phase 4 implementation was introduced.
