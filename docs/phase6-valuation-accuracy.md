# Phase 6 — Financial completeness, valuation safeguards and diagnostics

Verification date: 2026-10-18 (Asia/Kuala_Lumpur).

This report records implementation and offline verification before the separately
authorized Phase 6 Git commit. Git-state statements below refer to that verification
snapshot; the later commit packages these reviewed files on the same branch.

## Outcome and scope

Phase 6 adds verified financial scopes, tighter source/period checks, conservative
valuation-quality diagnostics and an expandable completeness dashboard. It does
not change the eleven financial model equations, substitute missing company
inputs, or relax the protected AI validators.

The dated regression evidence still supports only Forward P/E for AAPL and MSFT.
Their exact base values remain **214.2302568301956** and **619.5604742486083
USD/share**, respectively: illustrative policy estimates with low confidence.
NVDA and ORCL retain unavailable valuations. Additional mapped financial fields
do not establish another independent default model for these issuers.

The work began with the [internal architecture/source audit](phase6-internal-audit.md),
before implementation. The Phase 6 branch initially pointed to Phase 3. It was
fast-forwarded to the already completed Phase 5.1 commit
`4a4eb874abd0a0a45bc83d6b1cfb6ddc9236f516`, preserving the current branch
`feature/phase-6-valuation-accuracy`. That is the comparison baseline. The
implementation and verification stage created no new commit or push.

**Verification is offline.** Existing local SEC/FMP caches were inspected
read-only, and small dated public excerpts were retained for deterministic tests.
No fresh SEC, FMP, Treasury or OpenAI request was made. The application database,
environment files, cached provider payloads and historical snapshots were not
deleted or refreshed by this work.

## Source audit and reproducible dates

Two evidence sets have distinct purposes:

- The same-source normalization audit compares committed v3 and new v4 against
  the same cached raw SEC payloads. Its field counts below cover the selected
  annual period in those caches; they are not completeness scores.
- The valuation regression combines the maintained Phase 3/4.5 statement,
  quote and automatic-evidence fixtures with only compatible additional Phase 6
  observations. Original non-null facts remain unchanged except the explicitly
  quarantined debt fields. New facts retain their own retrieval timestamps.

| Company | Selected annual duration | Raw SEC cache retrieved (UTC) | Available normalized fields v3 → v4 |
| --- | --- | --- | --- |
| AAPL | 2024-09-29–2025-09-27 | 2026-10-15T06:29:26.628752Z | 33 → 48 |
| MSFT | 2025-07-01–2026-06-30 | 2026-10-16T05:52:41.999839Z | 32 → 43 |
| NVDA | 2025-01-27–2026-01-25 | 2026-10-15T06:30:03.729542Z | 35 → 43 |
| ORCL | 2025-06-01–2026-05-31 | 2026-10-15T06:30:17.742780Z | 31 → 42 |

Public source locations are the SEC Company Facts endpoints for
[AAPL](https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json),
[MSFT](https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json),
[NVDA](https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json) and
[ORCL](https://data.sec.gov/api/xbrl/companyfacts/CIK0001341439.json). These links
identify the source; they were not refreshed for this audit. The fixture retains
concept definitions, absolute units, fiscal durations, accession numbers, filing
dates and original signed observations.

| Company | Original financial fixture retrieved (UTC) | Dated FMP quote used in valuation regression | Quote retrieved (UTC) |
| --- | --- | --- | --- |
| AAPL | 2026-10-14T07:21:57.841327Z | $341.27 observed 2026-10-13T20:00:01Z | 2026-10-14T07:21:56.753208Z |
| MSFT | 2026-10-14T07:22:10.253403Z | $543.45 observed 2026-10-13T20:00:01Z | 2026-10-14T07:22:09.658985Z |
| NVDA | 2026-10-14T07:22:25.299047Z | $228.52 observed 2026-10-13T23:59:57Z | 2026-10-14T07:22:24.873108Z |
| ORCL | 2026-10-14T07:22:38.305172Z | Unavailable; permitted quote/history restrictions retained | Unavailable |

These are historical comparison prices, not current-price claims. The retained
successful Phase 5 v8 MSFT capture uses a different $539.44 quote observed on
2026-10-15; that independent fixture is not substituted into the company matrix.
Annual diluted EPS, dated common shares, quote observation and retrieval dates
retain their separate meanings.

## Mappings and derivation safeguards

Normalization v4 exposes the following scopes separately:

- Stock-based compensation (`ShareBasedCompensation`). Annual amounts are
  $12.863B AAPL, $12.405B MSFT, $6.386B NVDA and $4.811B ORCL.
- Long-term investments and noncurrent marketable securities. MSFT's $36.348B
  `LongTermInvestments` is not an alias for AAPL's $77.723B noncurrent marketable
  securities or automatically a complete nonoperating-asset adjustment.
- Long-term debt including current maturities, noncurrent long-term debt,
  current maturities, commercial paper, lease-inclusive current debt and gross
  debt instrument carrying amounts.
- Finance and operating leases, with separate current/noncurrent components.
  Compatible components may establish a lease total, never conventional debt.
- Distinct long-term debt proceeds/repayments, total debt repayments, repayments
  of debt maturing beyond three months and net commercial-paper financing.
- Reported receivable, inventory and payable cash-flow changes. These partial
  lines do not establish complete operating working capital.

Derived lease and long-term aggregates require compatible dates, units,
accessions, complete components and reconciliation to any reported aggregate.
Reported totals take precedence and remain inspectable when components conflict.
Signed component coefficients are retained. Annual/quarterly selection,
amendments, equivalent aliases and restatement safeguards continue to apply;
instant lease balances are never differenced as cash-flow durations. No TTM
annualization or generic issuer-extension mapping was invented.

The principal data correction is **debt scope**, not a changed valuation formula:

| Company | Historical interpretation | Corrected interpretation |
| --- | --- | --- |
| AAPL | $7.979B commercial paper treated as complete short-term debt; derived $98.657B total | Commercial paper remains $7.979B under its exact scope; complete short-term and conventional total debt are unavailable |
| MSFT | Complete conventional debt unavailable | Still unavailable; $40.294B long-term debt including maturities and $46.136B gross carrying amount remain distinct |
| NVDA | $0.999B lease-inclusive current debt fed a derived $8.468B total | Original current-debt scope remains visible; complete conventional aggregate is unavailable |
| ORCL | $7.199B lease-inclusive current debt treated as short-term borrowing | Partial short-term classification removed; explicitly reported $129.541B combined debt remains unchanged |

`DebtCurrent` can include capital leases. `CommercialPaper` covers only part of
short-term borrowing. Neither proves complete conventional debt. `LongTermDebt`
already includes current maturities, so current maturities must not be counted
again. A complete direct reported combined amount, or compatible complete
components, is required. The valuation-input boundary also rejects unsupported
legacy derived totals, preventing an old fixture/cache interpretation from
reentering through automatic inputs.

Other quantities are unchanged. D&A is deliberately not reconstructed by adding
separately scoped lines: NVDA's reported $2.843B aggregate differs from $2.4B
depreciation plus $0.488B amortization. MSFT's separate $34.3B/$4.7B lines do not
establish a verified aggregate either. Partial financing flows, inventory gaps,
nonredeemable preferred zeroes and parent equity are not promoted into complete
net borrowing, operating NWC, preferred claims or common equity.

## Automatic assumptions and model reliability

The existing growth, profitability, historical-multiple, capital-intensity and
discount-rate policies were reviewed. No unsupported sector benchmark, ERP,
beta, target multiple, current share count or future growth rate was added.
Historical EPS/split/price compatibility and unstable-multiple exclusion remain
strict. Existing `fill_only` precedence is preserved, so the newly reviewed
forecast adapter does not silently replace the assumptions that produced the
retained P/E estimates.

New safeguards require:

- Exact selected fiscal-base alignment before forward historical forecasts.
- NWC/financing windows ending at the selected base **after** per-fact scope,
  publication and currency checks. An invalid latest row cannot license an
  older usable window.
- Compatible observation periods, original source identity and full duration
  for supplemental annual amounts. Non-SEC conventional debt additionally
  requires explicit complete scope. Explicit unknown and verified zero remain
  different states.
- Dated shares no later than an explicitly frozen evidence snapshot; annual
  diluted EPS is not relabeled as current common shares.
- Sourced WACC equity/debt market observations within seven calendar days.
  An explicitly permitted book-debt proxy must precede market equity by no more
  than 550 days. These are disclosed compatibility policies, not universal
  financial laws or independently sourced interest rates.
- Visible sensitivity warnings for discount/terminal-growth spreads of at most
  one percentage point. Invalid/nonpositive spreads remain invalid; positive
  narrow spreads preserve their exact formula output and receive low-quality
  warnings. No arbitrary replacement perpetuity or clipped equity value is used.

Independent 45-digit Decimal benchmarks verify faded FCFF, explicit revenue and
terminal reinvestment paths (including negative, zero and positive NWC ratios),
complete enterprise-to-common-equity bridges, and FCFE loss/recovery paths that
do not deduct net debt again. Existing tests cover the remaining model equations,
negative earnings, invalid denominators, units, nonfinite values and economic
applicability.

## Before/after company results

| Company | Newly exposed source data | Contributing models before → after | Base USD/share before → after | Classification / confidence after |
| --- | --- | --- | --- | --- |
| AAPL | Compensation, securities, leases, debt/financing scopes and operating changes | 1 → 1 (Forward P/E) | 214.2302568301956 → same | Policy-based / low |
| MSFT | Compensation, investments, leases, debt scopes and operating changes | 1 → 1 (Forward P/E) | 619.5604742486083 → same | Policy-based / low |
| NVDA | Compensation, leases, debt/financing scopes and operating changes | 0 → 0 | Unavailable → unavailable | Unavailable |
| ORCL | Compensation, leases, distinct debt/financing and operating changes | 0 → 0 | Unavailable → unavailable | Unavailable |

No new default model became eligible. The method-family counts are 1/1/0/0,
respectively. None supports two meaningfully independent valuations. The source
classification of the available estimates is unchanged; improved diagnostics
do not upgrade either estimate's confidence. All 44 model eligibility statuses
are unchanged, with more precise debt blockers and all alternative input paths
now exposed. Detailed matrices appear below.

AAPL/MSFT P/E remains an historical research-policy benchmark rather than a
reported fact or an independent intrinsic-value determination. NVDA retains its
unstable historical P/E target blocker. ORCL retains provider restrictions,
unverified share/common-earnings scope and absent forecasts/targets. No profile
price, missing-zero assumption or valuation-input substitution bypasses these
restrictions.

## Aggregation, data quality and confidence

The existing family-budget weight preferences and normalized weighted-mean
arithmetic are preserved. User weights, including zeroes, remain explicit and
available models with no positive enabled weight are identified separately from
financially unavailable models. Unavailable fair values remain null.

Additive scenario/base diagnostics disclose eligible/applicable/contributing
counts, contributors, method families, exclusions, default/user/mixed weight
origins, shared inputs and family weights. A min/max range is shown only with at
least two contributing estimates. It is not a confidence interval. Dispersion is
`(maximum - minimum) / largest absolute contributing estimate`; above 0.5 it
flags material disagreement without silently removing an outlier. Nonpositive
estimates and ranges crossing zero remain visible.

Three concepts remain separate:

- **Data quality** describes source/fiscal freshness, compatibility and share
  scope. `review_required` is not a certification that every financial field is
  complete or economically suitable.
- **Coverage** describes actual model status and contribution. Family grouping
  identifies related frameworks; it does not prove independent evidence.
- **Valuation confidence** is a conservative heuristic. It assesses the inputs
  actually used by contributing models, rather than penalizing unused policy
  defaults or counting an inapplicable REIT model as missing evidence.

Confidence is limited by single-family support, contributing policy dependence,
weight concentration above 60%, old/future annual periods, explicit stale-cache
status, relevant source conflicts, low source quality, material dispersion,
nonpositive estimates, terminal dependence above 80% and narrow discount spreads.
Retained snapshots are assessed at their frozen date while explicit stale-on-error
cache warnings independently cap confidence. Thresholds are disclosed review
policies, not calibrated probabilities. No statistical accuracy or high-confidence
claim is introduced.

## Dashboard and API presentation

Provider mode remains authoritative to Python. JavaScript/JSX adapters preserve
exact server values, classification, weights and diagnostics; they do not
recalculate coverage or confidence.

- The overview shows the actual quote observation date, low-confidence/policy
  limitations and contributors. Retrieval dates are labeled separately.
- The model table/details show source quality, weight origin, shared assumptions,
  actual input records and **all** alternative input paths, including the real
  nested backend response shape.
- New quality/coverage/aggregation panels explain range, dispersion and exclusions.
- The completeness panel groups available, missing, stale, incompatible,
  restricted, derived, policy and user inputs. Counts overlap and are not a
  completeness percentage. Groups and provenance are collapsed by default.
- Expanded records retain exact stored values, units, periods, observation and
  retrieval timestamps, source identifiers, derivations, warnings and safe links.
  Policy descriptions alone do not turn a constant into a derived input.
- A manual comparison price is attributed to **User**, with no provider
  observation/retrieval timestamp. The original provider quote remains a separate
  inspectable record. Rejected stored source amounts remain inspectable while
  their effective input stays unavailable.
- Failed calculations clear prior diagnostics. Old/partial API responses remain
  supported and missing counts are displayed as unavailable instead of zero.

Layouts, typography, financial formulas, source warnings, assumption editing and
reset behavior remain intact. Tests cover desktop and mobile Chromium emulation;
physical devices and Safari are not verified.

## Versions, persistence and cache history

| Layer | Previous | Current |
| --- | --- | --- |
| FastAPI package metadata | 0.5.0 | 0.6.0 |
| SEC normalization | 3 | 4 |
| Automatic evidence interpretation | 1.0.0 | 2.0.0 |
| Raw optional-provider cache contract | 1.0.0 | 1.0.0 (preserved) |
| Valuation engine | 1.0.0 | 1.1.0 |
| Assumption provenance | automatic-assumptions-1 | automatic-assumptions-2 |
| Forward forecasts | automatic-forward-forecasts-1 | automatic-forward-forecasts-2 |
| Quality diagnostics | Original unversioned factors | valuation-quality-2 |
| Aggregation arithmetic | Existing family weighted mean | family-weighted-mean-1 (same arithmetic, explicit diagnostic version) |
| Completeness inventory | Absent | financial-completeness-1 |
| AI evidence adapter | Original adapter | financial-evidence-2 |
| AI prompt / typed-binding contract | fairworth-research-9 | Unchanged |

No Alembic migration or extra database is needed. Existing JSONB normalized
snapshots already retain arbitrary fields, provenance and interpretation versions.
Normalized cache keys use v4; native annual-publication keys include evidence v2
and normalization v4. Dated raw SEC, split, Treasury and supplemental statement
cache contracts remain reusable. Old cache keys are retained.

Content-hashed snapshots append a new v4 interpretation without overwriting v3.
Fact identity excludes interpretation-only mapping labels; original SQL
`FinancialFact` rows, IDs, values, source payloads and retrieval timestamps are
unchanged on reingestion. New snapshots supply the authoritative interpretation;
old raw mapping labels are not silently rewritten. Both SQLite and the dedicated
PostgreSQL migration/persistence contract test this behavior and idempotency.

The existing dedicated `fairworth_test` database is used for upgrade, schema
comparison and downgrade. Production/development database contents are not reset.
Valuations remain transient; engine/policy version and exact evidence contribute
to research snapshot identities. Only explicitly identified audit clocks are
excluded from identity; substantive quality, source values and real observation
dates remain significant.

## Phase 5 integrity and bounded evidence

New source facts retain exact units, fiscal periods, accession/filing provenance,
source classifications and warnings. Deterministic model/family counts and
contributor-range endpoints are registered as exact scalar evidence. Range
endpoints retain the contributing estimate classification, including policy or
user dependence. Manual comparison prices carry no provider retrieval timestamp
in the AI registry. Structured
diagnostics are citation-only: numbers inside an object do not become numeric
bindings. Null, incompatible, unknown and nonfinite records remain ineligible.

The evidence adapter version participates in report cache identity. Prompt v9,
dynamic typed-reference enums, category/uncertainty combinations, per-finding
derived citation coverage, numerical validation, private-data filtering and
server-owned presentation are unchanged. OpenAI cannot supply missing inputs or
calculate new fair values.

The default context budget can omit complete lower-priority diagnostic/history
records. This is disclosed and records are never clipped to fit. In an offline
four-company request probe, full structured diagnostics fit for NVDA but were
omitted for AAPL/MSFT/ORCL; protected displayed valuation/count/model evidence
remained intact. Request-scoped binding catalogs are rebuilt after omission.

The exact MSFT question, "Why is MSFT's valuation available or unavailable?", is
tested through the mocked SDK generation contract, all independent validators,
server rendering, public response schema and every returned evidence lookup.
The exact successful v8 retained response also continues through its existing
mocked SDK/FastAPI and desktop/mobile regressions with seven traceable sources.
That capture and earlier failure fixtures are unchanged. No live AI response is
claimed for Phase 6.

## Verification and remaining limitations

Final command results and the file inventory are recorded below. Backend runs
deny real synchronous/asynchronous HTTP transports while permitting MockTransport
and ASGITransport. Private configuration is used only internally for the existing
local test database; diagnostic output is redacted and ignored. Frontend provider
and AI browser routes are mocked.

Remaining blockers and accuracy risks:

1. Selected Company Facts concepts do not establish all issuer extensions,
   contractual definitions or complete common-equity/enterprise bridges.
2. Complete conventional debt remains unavailable for AAPL/MSFT/NVDA under the
   stricter scope contract; lease/gross amounts are not replacements.
3. MSFT/ORCL aggregate D&A, complete operating NWC and financing projections are
   not recovered from incomplete line items.
4. Preferred claims, NCI, nonoperating assets, common-book suitability, clean
   surplus and sustainable dividend/AFFO basis need independent verification
   where models require them.
5. FMP subscription/permission failures remain restrictions. ORCL quote/history
   is unavailable in these fixtures. No endpoint access is bypassed.
6. Historical multiples, growth estimates and weighting preferences remain
   research policies, not reliable forecasts or proof of intrinsic value.
7. The four-company evidence is dated, not a new live data audit. No second
   independent default model was established and no accuracy improvement is
   inferred from field counts.
8. Browser verification uses Chromium desktop/mobile emulation. Production
   deployment and fresh source coverage are outside this offline verification.
9. Full lower-priority diagnostics may not fit AI request budgets; omitted
   evidence cannot be cited or inferred by the model.

Further fresh SEC/FMP/Treasury audits require explicit approval. Live/paid OpenAI
verification requires separate authorization of the precise evidence export and
request limits. No live request, commit, push or deployment was performed during
the implementation and verification stage.

## Reproduce the company comparison

From the repository root, with backend dependencies installed:

```powershell
backend/.venv/Scripts/python.exe backend/tests/phase6_company_helpers.py
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_phase6_four_company.py -q
```

The helper exports the committed baseline source into ignored `.phase6.local/`,
blocks real HTTP in baseline/current processes and writes the full 44-row
before/after JSON report there. Maintained inputs are the original statement and
automatic-evidence fixtures plus `phase6_provider_excerpts.json` (66 dated public
observations, 54,989 bytes). The overlay rejects mismatched fiscal duration,
currency and conflicting amounts; absent excerpt fields never erase old facts.


## Detailed company/model matrices

The tables report exact default eligibility before and after. Missing fields
are the nearest sufficient input path plus required compatibility flags;
the API and expanded UI retain every alternative path. No blocked output is
shown as zero. Exact underlying assumptions, evidence IDs and source metadata
are retained in the reproducible JSON audit.

### AAPL

| Model | Eligibility before → after | Current exact blocker / estimate basis |
| --- | --- | --- |
| Discounted Cash Flow (FCFF) | unavailable → unavailable | `debt`, `minority_interest`, `nwc_ratio`, `other_nonoperating_assets`, `preferred_equity`, `wacc` |
| Discounted Cash Flow (FCFE) | unavailable → unavailable | `fcfe` |
| Forward P/E | eligible → eligible | Policy-based Forward P/E; 214.2302568301956 USD/share; effective weight 100% |
| EV/EBITDA | unavailable → unavailable | `debt`, `minority_interest`, `other_nonoperating_assets`, `preferred_equity`, `target_ev_ebitda` |
| EV/Revenue | unavailable → unavailable | `debt`, `minority_interest`, `other_nonoperating_assets`, `preferred_equity`, `target_ev_revenue` |
| PEG-Based Valuation | unavailable → unavailable | `target_peg` |
| Graham Number | unavailable → unavailable | `book_value_meaningful`, `common_equity_basis_confirmed` |
| Dividend Discount Model | unavailable → unavailable | `projected_dividends`, `stable_dividend_confirmed` |
| Residual Income Model | unavailable → unavailable | `book_value_meaningful`, `clean_surplus_confirmed`, `common_equity_basis_confirmed` |
| Price-to-Book | unavailable → unavailable | `book_value_meaningful`, `common_equity_basis_confirmed`, `target_pb` |
| REIT AFFO Valuation | ineligible → ineligible | Non-REIT: economically inapplicable; no AFFO or REIT scope is inferred. |

### MSFT

| Model | Eligibility before → after | Current exact blocker / estimate basis |
| --- | --- | --- |
| Discounted Cash Flow (FCFF) | unavailable → unavailable | `debt`, `fcff`, `minority_interest`, `other_nonoperating_assets`, `preferred_equity`, `wacc` |
| Discounted Cash Flow (FCFE) | unavailable → unavailable | `fcfe` |
| Forward P/E | eligible → eligible | Policy-based Forward P/E; 619.5604742486083 USD/share; effective weight 100% |
| EV/EBITDA | unavailable → unavailable | `debt`, `ebitda_margin`, `minority_interest`, `other_nonoperating_assets`, `preferred_equity`, `target_ev_ebitda` |
| EV/Revenue | unavailable → unavailable | `debt`, `minority_interest`, `other_nonoperating_assets`, `preferred_equity`, `target_ev_revenue` |
| PEG-Based Valuation | unavailable → unavailable | `target_peg` |
| Graham Number | unavailable → unavailable | `book_value_meaningful`, `common_equity_basis_confirmed` |
| Dividend Discount Model | unavailable → unavailable | `projected_dividends`, `stable_dividend_confirmed` |
| Residual Income Model | unavailable → unavailable | `book_value_meaningful`, `clean_surplus_confirmed`, `common_equity_basis_confirmed` |
| Price-to-Book | unavailable → unavailable | `book_value_meaningful`, `common_equity_basis_confirmed`, `target_pb` |
| REIT AFFO Valuation | ineligible → ineligible | Non-REIT: economically inapplicable; no AFFO or REIT scope is inferred. |

### NVDA

| Model | Eligibility before → after | Current exact blocker / estimate basis |
| --- | --- | --- |
| Discounted Cash Flow (FCFF) | unavailable → unavailable | `debt`, `minority_interest`, `nwc_ratio`, `other_nonoperating_assets`, `preferred_equity`, `wacc` |
| Discounted Cash Flow (FCFE) | unavailable → unavailable | `projected_fcfe` |
| Forward P/E | unavailable → unavailable | `target_pe` |
| EV/EBITDA | unavailable → unavailable | `debt`, `minority_interest`, `other_nonoperating_assets`, `preferred_equity`, `target_ev_ebitda` |
| EV/Revenue | unavailable → unavailable | `debt`, `minority_interest`, `other_nonoperating_assets`, `preferred_equity`, `target_ev_revenue` |
| PEG-Based Valuation | unavailable → unavailable | `target_peg` |
| Graham Number | unavailable → unavailable | `book_value_meaningful`, `common_equity_basis_confirmed` |
| Dividend Discount Model | unavailable → unavailable | `projected_dividends`, `stable_dividend_confirmed` |
| Residual Income Model | unavailable → unavailable | `book_value_meaningful`, `clean_surplus_confirmed`, `common_equity_basis_confirmed` |
| Price-to-Book | unavailable → unavailable | `book_value_meaningful`, `common_equity_basis_confirmed`, `target_pb` |
| REIT AFFO Valuation | ineligible → ineligible | Non-REIT: economically inapplicable; no AFFO or REIT scope is inferred. |

### ORCL

| Model | Eligibility before → after | Current exact blocker / estimate basis |
| --- | --- | --- |
| Discounted Cash Flow (FCFF) | unavailable → unavailable | `minority_interest`, `other_nonoperating_assets`, `preferred_equity`, `projected_fcff`, `share_basis_confirmed`, `shares`, `wacc` |
| Discounted Cash Flow (FCFE) | unavailable → unavailable | `common_equity_earnings_basis`, `projected_fcfe`, `share_basis_confirmed`, `shares` |
| Forward P/E | unavailable → unavailable | `forward_eps`, `share_basis_confirmed`, `target_pe` |
| EV/EBITDA | unavailable → unavailable | `ebitda_margin`, `minority_interest`, `other_nonoperating_assets`, `preferred_equity`, `share_basis_confirmed`, `shares`, `target_ev_ebitda` |
| EV/Revenue | unavailable → unavailable | `minority_interest`, `other_nonoperating_assets`, `preferred_equity`, `share_basis_confirmed`, `shares`, `target_ev_revenue` |
| PEG-Based Valuation | unavailable → unavailable | `earnings_growth`, `forward_eps`, `share_basis_confirmed`, `target_peg` |
| Graham Number | unavailable → unavailable | `book_value_meaningful`, `common_equity_basis_confirmed`, `share_basis_confirmed`, `shares`, `trailing_eps` |
| Dividend Discount Model | unavailable → unavailable | `projected_dividends`, `share_basis_confirmed`, `stable_dividend_confirmed` |
| Residual Income Model | unavailable → unavailable | `book_value_meaningful`, `clean_surplus_confirmed`, `common_equity_basis_confirmed`, `payout_ratio`, `return_on_equity`, `share_basis_confirmed`, `shares` |
| Price-to-Book | unavailable → unavailable | `book_value_meaningful`, `common_equity_basis_confirmed`, `share_basis_confirmed`, `shares`, `target_pb` |
| REIT AFFO Valuation | ineligible → ineligible | Non-REIT: economically inapplicable; no AFFO or REIT scope is inferred. |

### What would legitimately improve model coverage

| Model/path | Additional verified evidence or explicit research work required |
| --- | --- |
| FCFF | Complete unlevered forecasts or compatible operating/reinvestment/NWC history; sourced discount rate; complete financial-debt and enterprise-to-common-equity bridge; usable shares |
| FCFE | Complete common-equity cash-flow forecasts or NI/D&A/capex/NWC and complete financing scope; equity discount rate and compatible shares |
| P/E | Stable, split-compatible historical benchmark and supported forward/common EPS; NVDA instability and ORCL source/share restrictions cannot be waived |
| EV/EBITDA | Defensible target multiple, compatible EBITDA forecast, complete enterprise bridge and shares; EBITDA margin does not establish EBITDA itself |
| EV/Revenue | Defensible target multiple, compatible revenue forecast, complete enterprise bridge and shares |
| PEG | Justified PEG policy and compatible positive growth/common EPS; no arbitrary sector constant |
| Graham / P/B | Economically meaningful common book value and common-claim/share confirmations; P/B also needs a justified target |
| Dividend discount | Verified sustainable common per-share dividends or explicit dated projection, stability confirmation and equity discount rate |
| Residual income | Common book/scope suitability, clean surplus, compatible ROE/payout path, shares and equity discount rate |
| AFFO | A verified REIT business and AFFO/share basis; these four issuers must remain ineligible |

## Final verification results

| Check | Result |
| --- | --- |
| Final complete backend suite | **1,232 passed**, including the dedicated PostgreSQL contract; no skipped tests |
| PostgreSQL contract after container restart | 1 passed: upgrade, JSONB/Numeric persistence, immutable v3/v4 history, idempotency, cache behavior, schema comparison and downgrade |
| Final focused AI compatibility recheck | **61 passed**, including the exact MSFT question, four-company request budgets, typed evidence and retained v8 replay |
| Real HTTP deny guard | Zero real provider/OpenAI transport attempts in the final complete and focused runs |
| Frontend unit suite | **57 passed** |
| Complete production browser suite | **120 passed** (60 desktop + 60 mobile) |
| Final diagnostics browser recheck | **14 passed**, after the final wording/provenance presentation correction |
| ESLint | Passed |
| Production Vite build | Passed, including fresh production builds for browser checks |
| Python dependency check | `pip check`: no broken requirements |
| Four-company regression | 8 tests passed; committed baseline/current comparison generated with HTTP denied |
| Source/diff/privacy checks | Exact source fixtures retained; configured secrets/contact values absent from newly introduced content; ignored sensitive/artifact paths preserved |

Commands used were the repository's backend pytest suite, dedicated
`backend/tests/test_postgres.py`, `npm run test:unit`, `npm run test:e2e`,
`npm run lint`, production Vite builds and `backend/.venv/Scripts/python.exe -m
pip check`. The offline backend wrapper reads local configuration internally,
sets only the existing loopback `fairworth_test` target and denies concrete real
HTTP transports. Logs/XML and baseline exports remain ignored in `.phase6.local/`.

The initial full 1,221-test backend run (before the final additional regressions)
also passed PostgreSQL. An intermediate run passed 1,230 non-PostgreSQL tests but
encountered a connection timeout because the existing local container had
stopped. Restarting that same container preserved its volume; its dedicated
contract and the final full **1,232-test** run then passed. No application
database reset or new database was used.

The backend emits one upstream Starlette TestClient/httpx deprecation warning.
Browser processes emit the existing FORCE_COLOR/NO_COLOR warning. Neither is a
test failure. Windows sandbox process/temp-directory limitations required local
escalated test launches; they did not authorize or cause provider API traffic.

## Files added and modified

The following intended source, test and documentation files comprised the
uncommitted change set at the end of implementation and verification.
There are no dependency changes, migrations or real environment/configuration
secrets in this change. Original Phase 5 captures and prior financial fixtures
are unchanged.

### Added

- `backend/app/valuation/completeness.py`
- `backend/tests/fixtures/valuation/phase6_provider_excerpts.json`
- `backend/tests/phase6_company_helpers.py`
- `backend/tests/test_phase6_ai_evidence.py`
- `backend/tests/test_phase6_benchmarks.py`
- `backend/tests/test_phase6_cache_versions.py`
- `backend/tests/test_phase6_completeness.py`
- `backend/tests/test_phase6_engine.py`
- `backend/tests/test_phase6_four_company.py`
- `backend/tests/test_phase6_normalization.py`
- `backend/tests/test_phase6_persistence.py`
- `docs/phase6-internal-audit.md`
- `docs/phase6-valuation-accuracy.md`
- `src/components/dashboard/ProviderDataCompleteness.jsx`
- `src/components/dashboard/ProviderModelInputPaths.jsx`
- `src/components/dashboard/ProviderValuationDiagnostics.jsx`
- `src/lib/providerDiagnostics.js`
- `tests/helpers/providerDiagnosticsFixture.js`
- `tests/provider-diagnostics.spec.js`
- `tests/unit/providerDiagnostics.test.js`

### Modified

- `README.md`
- `backend/app/ai/context.py`
- `backend/app/ai/report_service.py`
- `backend/app/main.py`
- `backend/app/services/automatic_inputs_service.py`
- `backend/app/services/normalization.py`
- `backend/app/valuation/assumptions.py`
- `backend/app/valuation/automatic.py`
- `backend/app/valuation/confidence.py`
- `backend/app/valuation/eligibility.py`
- `backend/app/valuation/engine.py`
- `backend/app/valuation/forecasts.py`
- `backend/app/valuation/inputs.py`
- `backend/app/valuation/provenance.py`
- `backend/app/valuation/schemas.py`
- `backend/app/valuation/weighting.py`
- `backend/tests/test_automatic_source_latency.py`
- `backend/tests/test_automatic_treasury_cache_fallback.py`
- `backend/tests/test_normalization.py`
- `backend/tests/test_postgres.py`
- `backend/tests/test_valuation_api.py`
- `backend/tests/test_valuation_automatic_integration.py`
- `backend/tests/test_valuation_engine.py`
- `eslint.config.js`
- `src/components/dashboard/AnalysisWorkspace.jsx`
- `src/components/dashboard/ModelComparison.jsx`
- `src/components/dashboard/ProviderValuationStatus.jsx`
- `src/components/dashboard/ValuationSummary.jsx`
- `src/dashboard.css`
- `src/hooks/useProviderValuation.js`
- `src/lib/providerValuation.js`

### Preserved local exclusions

`backend/.env`, `.phase5.local/`, `.phase6.local/`, provider cache/database
contents, virtual environments, dependencies, `dist/`, `test-results/`,
Playwright reports, `__pycache__/` and pytest caches remain excluded. The
ESLint configuration now also ignores `**/*.local/**`, preventing preserved
generated baseline-export bundles from being linted as source.

The implementation branch is `feature/phase-6-valuation-accuracy`, based on
`4a4eb874abd0a0a45bc83d6b1cfb6ddc9236f516`. At the verification snapshot, no
files had been staged, committed or pushed. The subsequent authorized packaging
uses `feat: improve financial data completeness and valuation safeguards`.
The implementation remains within the requested Phase 6 scope.
