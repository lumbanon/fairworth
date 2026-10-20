# Fairworth Phase 4.5: automatic assumptions and verification

Verified 2026-10-15 (Asia/Kuala_Lumpur). Core model engine `1.0.0`; assumption methodology `automatic-assumptions-1`; historical methodology `historical-company-multiples-1`; forecast methodology `automatic-forward-forecasts-1`; API `0.4.5`; normalization `3`.

Provider mode now obtains defensible automatic P/E defaults for AAPL and MSFT. Both are single-model **Policy-based illustrative estimates**, because historical forward-growth caps materially affect the historical benchmark. NVDA and ORCL remain unavailable when their required evidence fails validation. No arbitrary target P/E, quote, beta, zero claim, current share conversion or missing financial component is invented.

## A. Root cause and diagnostic audit

The [initial diagnostic audit](phase45-diagnostic-audit.md) records all 44 company/model combinations before implementation, including required alternatives, available facts, missing fields, defensible derivations, external data, confirmation requirements and models that must remain unavailable.

- AAPL and MSFT already had compatible reported diluted EPS and historical forward EPS estimates. A supportable target P/E was the nearest missing input.
- NVDA had incompatible split-era EPS history and highly variable growth. Verified split events now support adjusted forecast history, but do not make its historical target multiple reliable.
- ORCL has unverified quoted-class and common-income scope plus restricted quote/history/split endpoints. A profile beta or profile price does not bypass those restrictions.
- All four lack a sufficiently complete enterprise bridge, operating-working-capital/financing forecasts, and/or common-book/dividend/AFFO suitability. MSFT complete debt and aggregate D&A remain unavailable.

## B. Assumption methods, hierarchy and limits

Explicit user overrides take precedence. Validated observations and compatible reported history precede independently sourced/derived estimates; disclosed policy is separate, and unsupported values remain unavailable. Each metadata record carries value, unit, category, provider, source description, observation date, financial period, formula, quality/warnings, evidence type, editability, reset default and identifiers. Unknown dates stay unknown. Historical facts retain original observations.

### Publication-aligned historical multiples

1. Reconstruct native annual SEC vintages from the earliest qualifying original 10-K accession for each fiscal year. Later comparative/restated filings cannot leak into an earlier historical price observation. The original normalized facts remain unchanged.
2. Require original publication within 180 days after the annual end, compatible currency, finite positive denominators, verified quoted-class EPS scope and a known split basis. Pair each annual with the first permitted trading close strictly after publication and within seven calendar days.
3. Adjust EPS using a complete verified split calendar to the same split basis as the price series. Dividend-adjusted total-return prices are not interchangeable with split-adjusted share prices.
4. For historical P/E, estimate one-year forward EPS from that date's reported EPS and three-year EPS CAGR using only information published by that historical date. Apply disclosed forecast limits. Compute historical forward-proxy P/E = paired price / that forward EPS proxy. Preserve the separate historical trailing P/E statistic. No current quote determines the target.
5. Use one observation per fiscal year, a five-year default window, and at least three independent valid years. With four or more observations, apply disclosed inclusive-quartile Tukey fences (Q1/Q3 plus/minus 1.5 IQR). Expose retained and excluded observations, median, range and rejection reasons. Require recent evidence and reject a material profitability regime change.
6. Historical EV/revenue and EV/EBITDA use aligned period-end common shares, debt, cash, explicit complete preferred/NCI/other-asset scope, and compatible revenue or EBIT plus D&A. Weighted-average diluted shares cannot masquerade as historical market shares. The trailing enterprise benchmark is labeled a forward-target estimate and dated capital-value approximation. Incomplete bridge inputs keep these methods unavailable.

The five fiscal-year P/E samples produce 24.3651441001x for AAPL and 29.4012324785x for MSFT in the captured evidence. Both contain capped historical growth forecasts, so the weighted estimate is illustrative policy-based rather than verified fair value. Historical pricing is a benchmark, not proof of intrinsic value or persistent economic relevance.

No verified peer set or comparable-company financial dataset is available under this integration; no peers or peer metrics are invented. Existing fundamental justified P/E/P/B remains conditional on reviewed sustainable payout/ROE, meaningful common book and clean-surplus assumptions. It is not automatically applied to high-growth low-payout companies. No arbitrary policy multiple is enabled.

### Forward forecasts

Existing Phase 4 historical defaults remain intact when supported; additional validated evidence fills missing estimates. The new fallback growth rule compares the selected-window CAGR, three-year CAGR, latest YoY and median recent YoY, then uses the conservative minimum within configurable bounds. The original history, volatility, periods, policy clamp and deceleration rule remain visible. This fallback does not silently replace an already-supported legacy growth estimate.

Native split-verified EPS history now permits NVDA's additional earnings/revenue forecast: 20% initial growth under the disclosed cap and one-year EPS 5.88 in this snapshot. Its historical P/E windows remain too unstable. AAPL retains the existing 17.8617803% five-year EPS forecast growth and forward EPS 8.7924888090; MSFT retains 17.3961122% and forward EPS 21.0726021333. The pure additional candidate forecaster may return a different conservative AAPL candidate; it is not substituted for the effective default. Effective assumptions and their actual sources are returned separately.

Comparable historical margins use three aligned annual observations where available. EBITDA requires actual compatible EBIT and D&A. NWC requires complete noncash operating-current-asset/liability scope; financing requires actual complete proceeds/repayment flows. Ordinary OCF-capex is never FCFF or FCFE, and a change in book debt is not invented net borrowing.

Year-by-year revenue follows Revenue[t] = Revenue[t-1] x (1 + growth[t]); the disclosed default fades growth linearly toward terminal growth. Explicit `projected_revenue` accepts one positive absolute revenue per forecast year. The unchanged FCFF/FCFE equations use that path only with all operating, tax, reinvestment, financing and bridge inputs complete. Incremental NWC and terminal reinvestment are recomputed. Clearing a growth/margin dependency clears its derived forecasts; explicit analyst forecasts remain independent overrides.

### Discount rates and additional financial inputs

The public US Treasury XML adapter reads dated nominal ten-year par yields, converts percentage points to fractions, validates finite values/dates, and identifies the ten-year maturity as a modeling convention for long-lived USD equity. It is not an exact maturity-matched zero-coupon curve. FMP profile beta is a provider estimate; retrieval date and unavailable provider regression details are disclosed. No beta=1 is supplied.

ERP requires a configured value, source, publication date, US market and methodology. It is explicitly a research-policy estimate, not a live observation. With complete source records, Ke = Rf + beta x ERP. Without them the existing labeled 10% cost-of-equity policy remains; WACC stays unavailable without defensible capital values, debt cost and tax treatment. The live configured environment has no ERP source, so CAPM is not claimed.

The final Treasury cache check reused 5.21%, observed 2026-10-13, originally retrieved 2026-10-14T14:31:41.235649+00:00, with status **stale** after the current-day refresh exceeded its time budget. Original dates and the failure warning are preserved; no new Treasury observation is fabricated.

Historical cost of debt uses reported annual interest expense divided by the average of compatible complete beginning/ending debt balances. Its calendar, units, scope and source dates are validated. It is a historical financing-cost proxy, not a precise current borrowing yield. Automatic WACC does not silently use that proxy or book equity. Explicit book-debt opt-in from Phase 4 remains separately warned.

Additional SEC mappings distinguish basic weighted shares, dated DEI common shares, direct NCI, nonoperating interest, nonredeemable preferred carrying value, nominal/stated preferred value, and separate depreciation/intangible-amortization components. Partial debt or separate D&A components are not silently converted into complete aggregates. A verified zero nonredeemable preferred amount is not proof that all preferred/redeemable claims are zero. Claims require explicit complete scope.

Current-day/common, dated filing-cover/period-end, annual basic/diluted weighted and class-specific share counts remain distinct. Dated DEI shares are used only with compatible class scope and retain their observation date. They never rescale historical EPS or change the original common-income compatibility check. ORCL remains unverified.

### Weights, classification, scenarios and sensitivity

Model classifications are `evidence_supported`, `policy_based`, `user_defined` and `unavailable`. Classification follows inputs actually consumed by the model, recursively including forecast/rate dependencies. Unused global discount policies do not make a P/E estimate policy-based. Explicit forecasts replace their unused growth dependencies. Weighted composition includes each contributing category, model IDs and effective weight.

Existing family budgets prevent P/E/PEG or enterprise multiples from becoming independent evidence merely by adding another method. Automatic source quality adds disclosed preference factors: low 0.60, moderate 0.85, supported 1.00, alongside existing suitability warnings. These are weighting policies, not probabilities. User weights remain configurable; invalid/disabled models do not contribute. A single model is clearly labeled and remains low-confidence.

Bear/base/bull rerun adjusted operating assumptions and multiples through the actual Python formulas. Sensitivity uses the same eligibility/model code and fresh dependent forecasts. Case-specific edits/reset remain independent; inherited base edits have a working reset only in Base. Manual prices affect comparisons/reverse DCF without replacing stored provider quotes or official facts.

## C. Before versus after availability

| Company | Phase 4 untouched defaults | Phase 4.5 valid default models | Still unavailable or inappropriate |
| --- | --- | --- | --- |
| AAPL | No weighted estimate | Forward P/E (one model) | FCFF/FCFE/EV missing complete inputs; PEG/book/dividend frameworks unsupported; AFFO inappropriate for non-REIT. |
| MSFT | No weighted estimate | Forward P/E (one model) | FCFF/FCFE/EV missing complete inputs; PEG/book/dividend frameworks unsupported; AFFO inappropriate for non-REIT. |
| NVDA | No weighted estimate | None | Unstable historical P/E; FCFF/FCFE/EV missing complete inputs; PEG/book/dividend frameworks unsupported; AFFO inappropriate for non-REIT. |
| ORCL | No weighted estimate | None | Missing target P/E/class scope; FCFF/FCFE/EV missing complete inputs; PEG/book/dividend frameworks unsupported; AFFO inappropriate for non-REIT. |

## D. Actual company results

These are outputs of the configured research methodology using actual permitted SEC/FMP observations, not recommendations or independently verified fair prices. Source observations are dated; market prices are not labeled real time.

| Company | Weighted estimate | Classification | Provider comparison price | Upside | Margin of safety | Bear / bull |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| AAPL | $214.23 | Single-model policy-based illustrative estimate | $342.96 | -37.53% | -60.09% | $189.54 / $239.65 |
| MSFT | $619.56 | Single-model policy-based illustrative estimate | $533.69 | 16.09% | 13.86% | $548.10 / $693.13 |
| NVDA | Unavailable | Unavailable | $221.30 | Unavailable | Unavailable | Unavailable / Unavailable |
| ORCL | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable / Unavailable |

FMP price timestamps: AAPL/MSFT 2026-10-14T20:00:01Z; NVDA 2026-10-14T20:00:00Z. ORCL has no provider price/timestamp. Upside = (fair value / market price - 1) x 100; margin of safety = (fair value - market price) / positive fair value x 100. Signed values are preserved.

| Company | Financial period / key source dates | Available improvements | Remaining blockers / quality |
| --- | --- | --- | --- |
| AAPL | Annual ended 2025-09-27; latest EPS filed 2025-10-31; historical target last sample 2025-11-03; five FY samples 2021-2025 | Compatible EPS, dated shares, permitted history/splits/profile beta, historical target P/E | Single-model policy dependence; no complete EV claims, NWC/financing, sourced ERP/WACC or confirmed book/dividend scope |
| MSFT | Annual ended 2026-06-30; EPS filed 2026-07-29; target last sample 2026-07-30; five FY samples 2022-2026 | EPS forecast, dated shares, historical P/E, separate depreciation/amortization, nonoperating interest | Complete debt remains unknown; aggregate D&A not fabricated; statement endpoints restricted; other bridge/discount/book/dividend gaps remain |
| NVDA | Annual ended 2026-01-25; native annual publication 2026-02-25; verified 2024-06-10 split | Split-compatible EPS forecast and bounded growth; dated shares; explicit nonredeemable preferred zero | All five historical growth windows fail stability checks for target P/E; complete preferred/other claims still unknown; no default weighted value |
| ORCL | Annual ended 2026-05-31; annual filing 2026-06-22; dated shares remain class-unverified | Statements/profile beta, raw stated-value/direct NCI evidence shown without aggregate-scope promotion | Quote/history/splits remain restricted; class/common-earnings scope unverified; preferred aggregate/NWC/financing missing; no default valuation or comparison |

Actual API checks covered original defaults, independent scenario edits, exact P/E arithmetic, sensitivity centers, dependency clearing, reset/no persistence, absent debt and ORCL quote restrictions. An explicitly supplied ORCL per-share forecast/multiple plus manual comparison price enabled the user-defined test path while the official quote remained absent; those analyst assertions are not default values. Initial default requests took approximately 12-17 seconds including existing Phase 3 ingestion; optional assumption sources are independently bounded to three seconds and do not block a usable P/E.

## E. Technical changes and configuration

New services separate raw observations, native historical analytics, derived assumptions and final calculations. Existing SEC/FMP cache keys are reused; native-vintage analytics and method versions have their own cache identity. Input snapshots cache derived records/analytics for the existing process-local TTL. Provider adjustments do not persist user assumptions as official facts. No SQL schema migration or new dependency/lockfile is required.

All optional price/split/Treasury/profile/supplemental loaders run in one parallel phase with a total per-operation deadline of min(3 seconds, configured provider timeout). HTTP 402/429, timeouts and invalid data retain safe source-specific warnings. Negative optional results cache for five minutes; usable stale records retain original source dates/status. Treasury can reuse a valid cached observation from the preceding seven days when the current-day refresh is unavailable; stale records and negative entries remain intact.

The six valuation endpoints are unchanged. Responses add assumption methodology/snapshot IDs, automatic source observations/analytics, complete assumption provenance, per-model classifications and weighted composition. `projected_revenue` is an optional bounded JavaScript/JSON array; no TypeScript or client financial engine was added. Original engine version remains 1.0.0 because existing primitive formulas/expected results are preserved; API and assumption/normalization versions distinguish the new orchestration.

`backend/.env.example` documents automatic inputs/Treasury flags, cache TTL, growth limits/dispersion, historical window/minimum samples, and optional ERP source fields. ERP is blank by default. Real `.env` is unchanged and ignored. The existing provider timeout, model timeout, forecast horizon, terminal growth and required-return policy remain configurable.

Frontend changes add source/method/date/quality and classification disclosures to existing Provider components, expose read-only sourced assumptions, retain explicit edits and resets, and provide an edit action for missing inputs. Existing landing layout, Demo calculations, typography, spacing and chart formulas are preserved.

## F. Verification

| Check | Result |
| --- | --- |
| Backend, including dedicated PostgreSQL migrations/persistence/cache/downgrade | 490 passed; no skips or failures |
| Frontend unit tests | 39 passed |
| Desktop/mobile browser regression | 72 passed |
| Actual API without financial-provider mocks | Four companies passed |
| Actual Provider UI | Eight company/viewport combinations passed at 1440px and 390px, no runtime errors or page overflow |
| ESLint / production Vite build | Passed |
| Alembic / Python dependency check | No new migration operations; no broken requirements |

The preserved Phase 4 suite is included. One regression test hardcoded normalization cache version 2; it now uses `NORMALIZATION_VERSION` so the same stale-cache behavior is exercised under version 3. No old financial expected values were adjusted to force passing tests. New independent examples verify historical price/publication/split alignment, negative/unknown data, exact EV bridges, robust outliers, explicit revenue/NWC math, provenance/classification, reset behavior, optional-source deadlines and stale-source retention.

An upstream Starlette TestClient/httpx deprecation warning remains. Physical mobile devices and Safari were not tested. Generated screenshots, browser traces, test outputs and full verification snapshots remain ignored local artifacts; small deterministic native-vintage/price/split excerpts and tests are maintained in the repository.

## G. Remaining limitations and phase boundary

- Historical valuation benchmarks can reflect historical mispricing. The forward proxy uses disclosed research rules rather than verified analyst consensus; benchmark and forecast error can be substantial.
- AAPL/MSFT are single-model estimates and both depend on policy. Their weighted output is not independent multi-model agreement or verified fair value.
- NVDA volatility and ORCL entitlement/class scope remain meaningful blockers; future data could legitimately change availability.
- Preferred stock stated/par value, verified nonredeemable zero and NCI carrying amounts do not establish a complete enterprise bridge. Unknown claims remain unavailable.
- MSFT complete debt and aggregate D&A are still missing. No paid subscription, unofficial scrape or provider restriction bypass was used.
- No verified comparable-company service, independent ERP feed, market debt yields, rolling TTM, FX adapter or full foreign/custom taxonomy ingestion was added.
- Treasury refreshes can fail; stale fallback is labeled and age-limited. FMP beta estimation lookback/frequency is not published in this adapter. No company-specific CAPM is claimed without ERP.
- Existing SEC/FMP ingestion before the optional-source phase retains its Phase 3 network timings. Distributed ingestion/rate limiting and later deployment work remain separate.
- No OpenAI, Phase 5, accounts, payments or unrelated redesign was implemented. Commits require an explicit repository-review request; no automatic push is performed.

## Primary methodology and provider references

- [NYU: P/E fundamentals and growth/risk/payout limitations](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/lectures/pe.html).
- [NYU: stable terminal growth constraints](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/stablegrowthrate.htm).
- [SEC EDGAR data APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).
- [FMP historical price endpoint](https://site.financialmodelingprep.com/developer/docs/stable/historical-price-eod-full) and [official adjustment-convention guide](https://site.financialmodelingprep.com/how-to/fmp-historical-price-apis-from-light-charts-to-dividendadjusted-analysis).
- [US Treasury public XML feed documentation](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed).

The selection windows, caps, outlier thresholds, convergence rule and preference factors above are Fairworth research policies, not numerical facts attributed to these sources.

## File inventory

Created:

```text
backend/app/providers/treasury.py
backend/app/services/automatic_inputs_service.py
backend/app/valuation/automatic.py
backend/app/valuation/classification.py
backend/app/valuation/forecasts.py
backend/app/valuation/historical_multiples.py
backend/app/valuation/provenance.py
backend/tests/fixtures/valuation/automatic_evidence_excerpts.json
backend/tests/test_automatic_evidence_fixture.py
backend/tests/test_automatic_provider_evidence.py
backend/tests/test_automatic_source_latency.py
backend/tests/test_automatic_treasury_cache_fallback.py
backend/tests/test_valuation_automatic_integration.py
backend/tests/test_valuation_forecasts.py
backend/tests/test_valuation_historical_multiples.py
docs/phase45-automatic-valuation.md
docs/phase45-diagnostic-audit.md
src/components/dashboard/ProviderAssumptionSource.jsx
tests/provider-automatic-assumptions.spec.js
```

Modified:

```text
README.md
backend/.env.example
backend/app/core/config.py
backend/app/main.py
backend/app/providers/base.py
backend/app/providers/market_data.py
backend/app/providers/sec_edgar.py
backend/app/services/cache_service.py
backend/app/services/normalization.py
backend/app/services/valuation_service.py
backend/app/valuation/assumptions.py
backend/app/valuation/confidence.py
backend/app/valuation/engine.py
backend/app/valuation/models/__init__.py
backend/app/valuation/models/common.py
backend/app/valuation/scenarios.py
backend/app/valuation/schemas.py
backend/app/valuation/weighting.py
backend/tests/fixtures/valuation/README.md
backend/tests/test_api.py
src/components/dashboard/ModelComparison.jsx
src/components/dashboard/ProviderAssumptionEditor.jsx
src/components/dashboard/ProviderValuationStatus.jsx
src/components/dashboard/ValuationSummary.jsx
src/dashboard.css
src/hooks/useProviderValuation.js
src/lib/providerValuation.js
tests/helpers/providerValuationFixture.js
tests/unit/providerValuation.test.js
```
