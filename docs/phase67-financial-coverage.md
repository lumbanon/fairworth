# Phase 6.7 — Financial evidence and model coverage

Status: the implemented changes and approved SEC acquisition are verified.
Financial
statement coverage expanded, but the main multi-model/default-valuation coverage
objective has **not** been achieved. Dated retained and newly acquired samples
are measured separately below; neither establishes current market-wide valuation
coverage. Audit prepared on 20 October 2026.

## 1. Executive summary

The implementation improves evidence inspection and safely connects future
complete financial histories to the existing eleven-model engine. It does not
turn incomplete financial statements into additional price targets.

- Normalization v5 distinguishes total and common-only cash dividends, keeps
  narrow PP&E depreciation separate from company-wide D&A, and checks effective
  reporting intervals before deriving metrics.
- Replaying five retained SEC caches preserves all **435 annual/quarterly
  periods**, with **zero changed existing metric values**, while exposing **407
  additional explicitly scoped dividend observations** plus **30 directly
  reported diluted-common-income observations**. These 437 added values retain
  distinct metric scopes. Dividend observations are
  not dividends per share or proof of sustainable dividends.
- A guarded forecast boundary requires code-reviewed economic scope, exact raw
  observations, issuer ownership, units, periods and filing contexts. Its
  production scope allowlist is deliberately empty; synthetic contract tests
  do not admit unreviewed real observations.
- The valuation API adds categorized model blockers, candidate-input provenance,
  period inventories and independent coverage stages. The dashboard exposes
  these assessments without calculating new financial values in JavaScript.
- The 30-security retained replay still produces **two default estimates**:
  AAPL and MSFT, each Forward P/E only and classified as policy-based. No other
  default model or security becomes eligible. All eleven equations and the
  historical AAPL/MSFT numerical regressions remain unchanged.
- A separately approved audit acquired exactly eight SEC companyfacts documents
  (all HTTP 200; 36,961,056 bytes). AMZN, Alphabet, O and PGR add four reporting
  issuers with actual financial evidence. Across the eight acquired issuers,
  normalization exposes 129 annual and 531 quarterly periods. This expands
  evidence rather than manufacturing eligibility.
- A maintained 886-observation excerpt replays eight issuers as nine separately
  gated securities, including GOOG and GOOGL. All have annual financial evidence,
  but none can publish a current default estimate: issuer/listing verification
  is dated beyond the existing TTL, and independent financial/share/quote/model
  blockers remain.

All eight authorized requests have been spent. No FMP, Treasury, listing refresh
or OpenAI request was made. No application financial rows or caches were
refreshed, and no numerical valuation equation was changed. The remaining
multi-model coverage objective is reported as blocked, without claiming that a
successful download alone produces a defensible price target.

## 2. Starting Git commit and baseline

Branch `feature/phase-6-7-valuation-coverage` initially pointed to Phase 3
`2e93fd467c06e535b940bb501c94fcf62e0fd3f0`. The user explicitly approved the
fast-forward to completed Phase 6.6
`d3d0dab0e445481f406f8dda25b092b75ec965a4`. No new commit or branch was created.
The tracked tree and index were clean before implementation.

Before code changes, an HTTP-blocked replay of the dated 30-security public
listing fixture and retained financial evidence reproduced AAPL
`214.2302568301956` and MSFT `619.5604742486083`, each Forward P/E only. Other
sampled securities had no default estimate. The frozen baseline is local and
ignored, with its original financial inputs and all eleven model results.

The replay clock is **2026-10-19T11:56:54.533345+00:00**, inherited from the
maintained Phase 6.6 listing sample. It intentionally does not replace source
observation dates with the date this report was written. Source listing
observations are dated 19 October; retained financial/quote observations have
their own earlier clocks.

Read-only development database inspection reports 14,637 issuer reference rows,
17,060 instruments and listings, 23,710 immutable listing observations,
5 company records, 165,486 financial facts, 9 financial snapshots, 14 market
snapshots and 64 cache entries. An issuer reference row is not necessarily a
verified CIK-linked security. These database inventory counts are separate from
the 30-security financial sample and do not establish financial eligibility for
the registry population.

## 3. Financial source and permission audit

Existing documented adapters: SEC companyfacts
`https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`, FMP stable
profile/quote, historical prices/splits, shares-float and annual balance-sheet/
cash-flow statements, and the Treasury annual XML par-yield feed. Documentation
references are retained in the adapters and Phase 6.6 source audit. No new
documentation or provider requests were made for this audit.

Retained audited evidence cannot establish complete AAPL/MSFT/NVDA debt, complete
MSFT/ORCL D&A, noncash operating working capital, complete financing flows,
enterprise bridges, or every selected-security/common-equity scope. A narrow
depreciation or long-term debt concept cannot substitute for complete scope.
FMP 402/401/403/429 restrictions remain authoritative; keys do not establish
endpoint entitlements or public redistribution rights.

| Existing provider surface | Inputs supported by the adapter | Permission and interpretation limits |
| --- | --- | --- |
| SEC `data.sec.gov/api/xbrl/companyfacts/CIK##########.json` | Original issuer concepts/units/filings, with bounded normalization and source evidence | No key required; identifying User-Agent/fair access apply. Endpoint existence does not supply missing taxonomy scope, share ownership or current quote evidence. The exact eight-request authorization below was executed once and is exhausted. |
| FMP `financialmodelingprep.com/stable/profile` and `/quote` | Profile/beta estimates and separately observed quote metadata | Key/endpoint access required; a profile price never bypasses a denied quote endpoint. No entitlement probe performed. |
| FMP `/historical-price-eod/full`, `/splits`, `/dividends`, `/shares-float` | Dated price/split/dividend/share observations, subject to identity and economic-basis checks | Account-specific permissions and full source-date semantics remain required; unavailable splits are not “no splits,” and a processing date is not a share observation date. No new call authorized. |
| FMP `/balance-sheet-statement` and `/cash-flow-statement` | Annual supplemental statement requests bounded to at most ten periods by the adapter | Key presence does not establish subscription access or complete economic scope. These endpoints are excluded from the proposed SEC-only acquisition. |
| Treasury `home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml` | Published ten-year nominal par-yield observations from the official daily-yield feed | A dated USD convention rather than an exact maturity-matched zero-coupon curve. Existing cached observations remain dated; no refresh authorized. |

This is an audit of existing adapters, retained evidence and the explicitly
approved SEC snapshots, not a fresh online documentation/entitlement check.
Source links and launch-rights caveats are in Section 15. Additional provider
permission must be reviewed before any new use.

### Approved bounded acquisition — completed within the exact bounds

The user explicitly approved this exact eight-issuer SEC-only plan after the
initial offline checks. The bounds below were unchanged during execution.
Section 16 records every result. The approval did not authorize FMP, Treasury,
OpenAI, quote/listing refreshes, imports or development DB writes.

First stage: **at most eight SEC companyfacts GETs**, one for each issuer below.
No FMP, Treasury, submissions, directory refresh or OpenAI request is included.

| Security | SEC CIK | Why the request is needed |
| --- | --- | --- |
| MSFT | 0000789019 | Recheck debt components, broad D&A, annual periods and share observations |
| NVDA | 0001045810 | Recheck debt scope and fiscal/split-compatible financial history |
| ORCL | 0001341439 | Recheck common earnings/share scope, D&A and financing evidence |
| JPM | 0000019617 | Inspect common equity, earnings and bank-appropriate inputs |
| AMZN | 0001018724 | Expand retained operating-company statement evidence |
| GOOGL | 0001652044 | Inspect issuer facts while retaining distinct GOOG/GOOGL class gates |
| O | 0000726728 | Inspect reported REIT facts; do not manufacture AFFO |
| PGR | 0000080661 | Inspect insurance equity/earnings with enterprise-model exclusions |

Expected approximately 2–10 MB per document, **hard cap 12 MB each / 96 MB total**.
Requests are sequential, at least one second apart, with a 30-second total timeout
per request, zero retries and redirects. Stop on an access/rate denial rather
than trying alternative endpoints. Existing identifying SEC User-Agent is sent
only to SEC; its configured contact address is not logged. Public company CIKs
and the request path are transmitted, with no chat history, assumptions or keys.
SEC has no known per-request fee; access policies and availability still apply.

Raw JSON and the public-only acquisition manifest stayed in ignored
`.phase67.local/`. Normalization/reconciliation ran offline first; only the
audited limited regression excerpt is maintained for source control. No
development database write, financial cache refresh or current default valuation
publication was authorized or performed.
The bounded audit does not authorize market-wide ingestion. Publication rights
remain unresolved; approved acquisition would not establish redistribution rights.
Fresh quotes, price/split histories, Treasury observations or FMP supplementation
would need a separately bounded proposal and approval based on actual blockers.

## 4. Implemented code changes

| Area | Implementation and boundary |
| --- | --- |
| SEC normalization | `backend/app/services/normalization.py`: normalization version 5, dividend scopes, separate PP&E D&A, exact effective-period compatibility |
| Existing financial input boundary | `backend/app/valuation/inputs.py`: rejects legacy PP&E-only depreciation as aggregate D&A while retaining the original reported observation |
| Scoped automatic histories | `backend/app/services/automatic_inputs_service.py`: bounded annual reconciliation against the exact original SEC snapshot; no new endpoint or scheduler |
| Forecast isolation | `backend/app/valuation/forecasts.py`: requires selected issuer/instrument/listing identity before consuming scoped working-capital or financing histories |
| Coverage explanation | `backend/app/valuation/coverage.py`: additive diagnostics, 13 independent stages, period inventories and candidate sources; no input substitution |
| API contract | `backend/app/services/valuation_service.py` and `backend/app/valuation/schemas.py`: publish `financial_coverage`, per-scenario blockers and completeness assessments |
| Reproducible audit | `backend/scripts/replay_financial_model_coverage.py`: HTTP-blocked, in-memory replay of all 330 security/model combinations |
| Dashboard | Structured blockers, period evidence, separate compatibility/freshness assessments and explicit single-model limitations |
| Regression fixtures/tests | A small explicitly synthetic scope fixture; normalization, ownership, malformed-source, negative eligibility, API serialization and desktop/mobile coverage tests |

The automatic interpretation cache version changes to `2.1.0`; raw provider
cache contracts retain version `1.0.0`. This separates changed interpretations
without fetching new source data or rewriting retained raw responses. No new
dependency, migration, authentication flow or financial equation is introduced.

The existing on-demand workflow remains: resolve the selected stable identity,
apply listing/security gates, reuse scoped cached evidence, fetch only through
permitted configured provider paths, validate and normalize, calculate eligible
models in Python, and publish exact provenance or unavailable reasons. This
implementation does not prefetch the registry, enable an ingestion scheduler,
override provider restrictions or imply approval for new financial requests.

## 5. Normalization improvements

### Period and economic scope

The period compatibility check now compares complete effective intervals before
accepting a shared filing context. A common accession can contain annual,
quarterly and comparative facts; it does not by itself establish a common
duration. Signed cumulative terms used for a derived quarter must describe the
same effective interval as a directly reported quarter. Equivalent duplicate
observations do not multiply a duration. Instant and duration facts remain
distinct; malformed, overlapping or economically incompatible support fails
closed.

`total_dividends_paid` selects `PaymentsOfDividends` only;
`common_dividends_paid` selects `PaymentsOfDividendsCommonStock` only. The
compatibility `dividends_paid` field preserves its previous concept preference
and value, with an explicit `economic_scope` on each source record and a warning
when the scope is common-only. Total cash dividends are not automatically common
dividends, per-share distributions or a sustainable DDM input.

`DepreciationDepletionAndAmortizationPropertyPlantAndEquipment` is retained as
`depreciation_depletion_amortization_ppe`, rather than accepted as company-wide
D&A. Broader original concepts remain eligible for their existing scope. A
narrow PP&E observation, or the presence of separate depreciation/amortization
fields, does not authorize an unverified sum or unlock EBITDA.

Source concepts, original values, units, start/end dates, accession numbers,
filing dates, fiscal identifiers, amendment/restatement handling and raw
observations remain inspectable. Missing values remain unavailable; an observed
zero retains its source proof. No new fallback manufactures debt, EBITDA,
enterprise claims, noncash working capital, net borrowing or AFFO.

### Read-only retained-cache comparison

Normalization v4 at the starting commit was compared with v5 over the same five
retained raw SEC snapshots. Their raw hashes and retrieval timestamps are
retained locally; no snapshot was refreshed or written to the development DB.

| Issuer | Annual periods before / after | Quarterly periods before / after | Existing metric changes | Added scoped dividend values |
| --- | --- | --- | --- | --- |
| AAPL | 17 / 17 | 71 / 71 | 0 | 71 total + 11 common |
| MSFT | 17 / 17 | 69 / 69 | 0 | 85 common |
| NVDA | 17 / 17 | 71 / 71 | 0 | 69 total |
| ORCL | 17 / 17 | 69 / 69 | 0 | 85 common |
| JPM | 17 / 17 | 70 / 70 | 0 | 86 total |
| Total | 85 / 85 | 350 / 350 | 0 | 407 |

The final normalization comparison also exposes 30 previously retained,
directly reported `common_net_income_diluted` observations: seven ORCL and
23 JPM observations. Together with the 407 dividend values,
**437 additional scoped metric values**
are exposed without changing any pre-existing value or any of the 435 periods.

These are additional metric names and scope disclosures over already retained
public facts. They are not additional issuers, new financial periods, new live
coverage or automatically usable valuation inputs. The five raw caches
and the small maintained valuation sample contain different historical windows;
the 435-period normalization denominator must not be substituted for the
30-security valuation denominator.

### Reported common-income reconciliation

The approved snapshots independently confirm why consolidated net income cannot
always reproduce diluted common EPS. The exact
`NetIncomeLossAvailableToCommonStockholdersDiluted` concept is normalized as
`common_net_income_diluted`, with `common_diluted_eps_numerator` economic scope;
it does not replace consolidated `net_income`.

For Oracle's latest retained annual period, the explicit diluted-common numerator
is USD 16,984,000,000 versus consolidated net income of USD 17,087,000,000.
JPMorgan's is USD 55,681,000,000 versus consolidated net income of
USD 57,048,000,000. A native EPS reconciliation can use the common numerator only
when concept, period, units, original value, accession, annual form and filing
date match the reported diluted EPS and weighted diluted shares. A present but
invalid common numerator cannot fall back to consolidated income to obtain a
passing reconciliation.

The distinct `reported_common_eps_basis_verified` diagnostic reports that narrow
native publication reconciliation. It does not establish the selected quoted
class, later splits, current listing ownership or a consolidated FCFE earnings
basis. It does not rescale consolidated income, change FCFE margins or bypass
the existing selected-security eligibility rules. The automatic interpretation
version is `2.1.0`; normalization is version 5 and raw cache version is `1.0.0`.

Diluted-common income is **non-additive** because dilution eligibility is tested
for each reporting period. YTD numerators are not subtracted to synthesize a
quarter or Q4. Explicitly reported standalone quarterly observations remain
available, including directly reported Q4; absent quarterly observations remain
unavailable. The 30-observation count excludes every such synthetic subtraction.

## 6. Share and currency reconciliation

Existing class, issuer, foreign-reporting, ADR and currency gates are retained.
Consolidated equity is not divided by an unverified class-specific share count.

The retained replay has three compatible selected-security share/currency bases:
AAPL, MSFT and NVDA. Their dated common-share observations remain separate from
the annual diluted weighted-average denominators used to reconcile historical
EPS. They are not represented as current live diluted share counts. ORCL and
JPM do not acquire a verified common earnings/share basis merely because some
issuer statements exist.
The new explicitly reported diluted-common-income reconciliation in Section 5
is a separate native EPS diagnostic; it does not change this FCFE/consolidated
income or selected-security limitation.

GOOG and GOOGL retain different instrument/listing identities. No issuer-wide
price target is copied between them. BABA remains subject to ADR ratio and
per-depositary-security checks; TSM lacks an explicit security-form proof in
this directory excerpt. NVO's source description says common stock, which
neither proves US domestic reporting nor an ADR ratio, accounting conversion or
currency/share compatibility. No foreign conversion is inferred from a familiar
ticker or company name.

New scoped forecast histories carry the exact reporting CIK, issuer, instrument
and listing. Matching scope flags, financial values or ticker text cannot bypass
those identities. The service checks the original raw snapshot's issuer and
matches each proposed observation to its exact taxonomy, concept, unit, value,
start/end, accession, filing date, form and fiscal context. A conflict in raw
values cannot be resolved by cherry-picking a preferred normalized amount.

Share compatibility, currency compatibility, accounting evidence, provider quote
freshness and sector applicability are reported separately. A manual comparison
price does not become a provider observation, change the official quote date or
make the underlying share or accounting basis verified. A valid fresh provider
quote also retains its own assessment when a separate manual comparison is used.

## 7. Sector-specific model eligibility

Bank/insurance enterprise-value exclusions, REIT earnings/AFFO restrictions and
common-equity/clean-surplus checks remain authoritative.

| Issuer/security category | Retained policy |
| --- | --- |
| Operating common stock | Cash-flow and multiple methods require complete applicable inputs, selected-security basis and a defensible enterprise-to-equity bridge |
| Banks/diversified financial institutions | Industrial FCFF/EV/EBITDA/EV/revenue frameworks are excluded where the existing financial-institution policy applies; suitable earnings or common-equity methods still need their own evidence |
| Insurance | Industrial enterprise methods remain excluded; reserve-sensitive equity and earnings are not treated as automatically comparable operating-company inputs |
| REIT | GAAP earnings P/E/PEG/Graham exclusions remain; AFFO requires an independently defensible recurring adjustment scope and forecast, never ordinary FCF relabeled as AFFO |
| ADR/ADS/foreign issuer | Explicit accounting, currency, class/ownership economics and applicable conversion proof are required; unsupported non-unit ADR conversions remain unavailable |
| ETF/preferred/warrant and other unsupported forms | Ordinary common-stock valuation is inapplicable even if the listing or issuer identity is known |
| Unknown form/business category | The relevant model-specific classification gate remains unresolved; a missing classification is not replaced with an operating-company default |

The new coverage layer explains these decisions; it does not replace the
engine's authoritative eligibility or relax economic applicability.

## 8. Before/after eligibility for all eleven models

### Required inputs, history and provenance

Every method requires the selected-security identity, applicable financial
framework and compatible units. A complete alternative input path is required;
fields from unrelated paths cannot be combined to hide missing components.
An explicit forecast can have a different history requirement from a
history-derived default. The engine does not impose an invented universal
minimum number of annual periods on all eleven equations.

| Model | Required financial path and applicability | Minimum evidence/history and assumption provenance |
| --- | --- | --- |
| FCFF DCF | Complete projected FCFF; or a defensible FCFF base; or EBIT/tax/D&A/capex/change-NWC; or complete operating-driver history; plus WACC, terminal growth/horizon, shares and full enterprise bridge. Industrial framework only where appropriate. | Explicit projections must retain their user/source classification. Automatic growth needs aligned fiscal history; complete noncash operating balances must match the selected base period. WACC needs supported rate/capital inputs or an explicit disclosed assumption; missing debt/claims are not zero. |
| FCFE DCF | Projected FCFE, a defensible FCFE base, or common-equity earnings/D&A/capex/change-NWC/net borrowing; plus cost of equity, growth/horizon and compatible shares. No second debt deduction. | Common earnings scope is checked for component forecasts. Complete debt cash flows are needed for automatic borrowing; changes in debt balances are not financing cash flows. Direct projections retain their provenance. |
| Forward P/E | Supported forward EPS and target P/E, or compatible trailing EPS with earnings growth and target P/E; applicable earnings framework. | Historical EPS growth requires aligned positive observations and compatible diluted shares/splits. A retained median multiple needs filing-date-aligned prices; an allowed policy multiple remains policy-based and illustrative. |
| EV/EBITDA | Forecast EBITDA, or forecast revenue and independently supported EBITDA margin, plus target multiple, shares and complete enterprise bridge. | EBITDA cannot be inferred from narrow PP&E depreciation. Forecast margin/history and the target multiple retain their sources; industrial EV frameworks remain excluded for applicable financial institutions. |
| EV/Revenue | Forecast revenue or revenue plus forward growth, target EV/revenue, shares and complete enterprise bridge. | Revenue history must be coherent annual evidence; the multiple requires sourced history or an explicit assumption. Missing profitability/reinvestment evidence remains a disclosed limitation. |
| PEG | Forward EPS or trailing EPS/growth, positive supported earnings growth and target PEG. | EPS/share history and growth conventions are verified; the target PEG is not invented. Shares assumptions with P/E and cannot double-count an independent earnings family. |
| Graham | Positive reported EPS and meaningful, appropriately scoped common book equity per compatible share. | One aligned positive earnings/book basis can satisfy the equation; no numerical forward forecast assumption is required. Common claims and economic book value still require confirmation. Historical screen classification is retained. |
| Dividend discount | Verified per-share dividend basis and sustainable growth/required return, or a supported projected-dividend path with terminal assumptions. | Total or common cash dividends alone do not establish per-share distributions or sustainability. The required return, growth and any explicit forecast remain separately classified. |
| Residual income | Beginning common equity, compatible shares, ROE, payout, cost of equity, terminal growth and horizon; clean-surplus confirmation. | A suitable beginning book basis and explicit future assumptions are required. OCI, repurchases and issuance are not silently assumed away. Assumptions are distinguished from reported equity. |
| Price/book | Meaningful common-equity book value per compatible share and supported target P/B. | Positive/scoped book basis and a sourced or explicit target are required. A bank label does not establish common-equity scope; noncontrolling interests remain excluded unless reconciled. |
| REIT AFFO | Independently supported forecast AFFO, compatible shares, target P/AFFO and confirmed REIT/AFFO scope. | Reported adjustments and recurring definitions must be traceable. No generic XBRL or FCF proxy manufactures AFFO; a company-specific adjusted disclosure may remain necessary. |

Historical default growth uses the existing aligned 3/5/10-year windows, each
requiring the corresponding number of consecutive annual observations plus one
starting observation. Historical facts and forward growth/margin policies remain
different records. Treasury par-yield observations, beta estimates, ERP policy,
discount-rate derivations and editable overrides retain their existing source
categories and dates; the coverage code supplies none of these values.

### Default eligible outputs in the 30-security retained sample

| Model | Before: valid / 30 | After: valid / 30 | Result |
| --- | --- | --- | --- |
| FCFF DCF | 0 / 30 | 0 / 30 | Required cash-flow/bridge/discount inputs remain incomplete |
| FCFE DCF | 0 / 30 | 0 / 30 | A complete applicable cash-flow path remains unavailable |
| Forward P/E | 2 / 30 | 2 / 30 | AAPL and MSFT only; both policy-based, single-model estimates |
| EV/EBITDA | 0 / 30 | 0 / 30 | EBITDA/multiple/bridge and applicability gates remain |
| EV/Revenue | 0 / 30 | 0 / 30 | Supported multiple/bridge and applicability gates remain |
| PEG | 0 / 30 | 0 / 30 | No supported default target PEG |
| Graham | 0 / 30 | 0 / 30 | Common-equity/economic-book and selected-security gates remain |
| Dividend discount | 0 / 30 | 0 / 30 | Per-share sustainable distribution basis remains unverified |
| Residual income | 0 / 30 | 0 / 30 | Common-equity, clean-surplus and required forecasts remain incomplete |
| Price/book | 0 / 30 | 0 / 30 | Common-equity/economic-book and supported target gates remain |
| REIT AFFO | 0 / 30 | 0 / 30 | No verified complete AFFO forecast/multiple path |

AAPL's exact default estimate remains `214.2302568301956`; MSFT's remains
`619.5604742486083`. They are dated policy-based outputs, not independently
verified current intrinsic values. NVDA, ORCL and JPM remain unavailable under
defaults. Optional manual inputs do not count as new default evidence coverage.
The before/after comparison verifies all 330 security/model combinations:
**zero changed model decisions and zero changed default fair values**.

For every model, the API retains the engine result/status, eligibility status,
all categorized blockers, alternative input paths and candidate-input sources.
Candidate provenance includes the original reported record separately from an
effective assumption or override. A candidate's presence is not a claim that the
engine consumed every alternative field. Calculation details identify the used
projection. An unused cash-flow alternative does not generate a false missing
NWC/borrowing blocker when the selected direct path fails for another reason.

## 9. Representative security audit

The dated Phase 6.6 fixture contains 30 securities, including the requested
operating companies, banks, insurance, REITs, foreign issuers, separate Alphabet
classes, an ETF and a preferred-share exclusion control. No coverage is inferred
for the rest of the registry.

The following table summarizes retained evidence and decisive limitations. Every
row was evaluated across all eleven methods. The reproducible audit command
below emits all **330** rows with exact blocker categories and required inputs;
the concise table does not replace those model-specific records.

| Security | Retained annual periods in valuation replay | Eligible default models / 11 | Principal limitations in this audited bundle |
| --- | --- | --- | --- |
| AAPL | 6 | 1, Forward P/E | FCFF debt/enterprise claims/NWC/WACC missing; no complete FCFE base; other target multiples and common-equity/dividend confirmations missing |
| MSFT | 6 | 1, Forward P/E | Complete debt, enterprise claims, FCFF/FCFE and WACC missing; additional multiples/book/dividend scope unverified |
| NVDA | 6 | 0 | Forward P/E target unavailable under current policy; cash-flow bridge/NWC/WACC and other method inputs missing |
| ORCL | 6 | 0 | Share/common earnings basis unverified; forward EPS/multiple unavailable; quote/history access restricted; cash-flow path/claims/WACC incomplete |
| JPM | 1 | 0 | Common equity/earnings/share basis incomplete; bank-appropriate model inputs missing; industrial enterprise frameworks remain excluded |
| AMZN | 0 | 0 | `financial_statements_missing`, share/currency basis and required inputs/targets absent in the retained bundle |
| GOOG | 0 | 0 | Explicit security-form proof unresolved; no retained financial history; class-specific economics remain separate from GOOGL |
| GOOGL | 0 | 0 | No retained financial history or verified class-specific share/currency basis; no GOOG target is copied |
| META | 0 | 0 | Financial statements, share/currency basis and required model inputs absent in the retained bundle |
| TSLA | 0 | 0 | Financial statements, share/currency basis and required model inputs absent in the retained bundle |
| AMD | 0 | 0 | Financial statements, share/currency basis and required model inputs absent in the retained bundle |
| PLTR | 0 | 0 | Financial statements, share/currency basis and required model inputs absent in the retained bundle |
| KO | 0 | 0 | Financial statements, share/currency basis and required model inputs absent in the retained bundle |
| PG | 0 | 0 | Financial statements and relevant issuer-business classification unresolved; share/currency/input gates remain |
| WMT | 0 | 0 | Financial statements, share/currency basis and required model inputs absent in the retained bundle |
| JNJ | 0 | 0 | Financial statements and relevant issuer-business classification unresolved; share/currency/input gates remain |
| BAC | 0 | 0 | No retained financial evidence; bank common-equity/earnings/share basis missing; industrial enterprise exclusions retained |
| GS | 0 | 0 | No retained financial evidence; relevant business classification and selected-security/financial inputs unresolved |
| PGR | 0 | 0 | No retained financial evidence; insurance equity/earnings basis missing; industrial enterprise exclusions retained |
| O | 0 | 0 | No retained financial evidence; verified AFFO adjustments/forecast/target absent; REIT earnings exclusions retained |
| PLD | 0 | 0 | No retained financial evidence or verified relevant business classification; AFFO and other financial bases unavailable |
| SOFI | 0 | 0 | No retained financial evidence/share basis; financial-sector exclusions and model-specific requirements remain |
| BRK.B | 0 | 0 | SEC `BRK-B` / directory `BRK.B` linkage remains reference-only; no mechanical alias merge or retained financial evidence |
| TSM | 0 | 0 | Security form unresolved in the directory excerpt; financial, currency and selected-security basis absent |
| BABA | 0 | 0 | ADR share/conversion basis unverified; financial evidence/currency/model inputs absent |
| NVO | 0 | 0 | Directory common-stock label does not verify foreign accounting/share/currency economics; no retained financial evidence |
| SPY | 0 | 0 | Explicit ETF exclusion control; venue mapping remains reference-only; ordinary-stock estimates are inapplicable |
| AGNCN | 0 | 0 | Explicit preferred-share exclusion control; ordinary common-stock estimates are inapplicable |
| CMT | 0 | 0 | SEC/directory venue mismatch remains reference-only; no retained financial evidence |
| CRWV | 0 | 0 | Verified dated listing, but no retained financial evidence or compatible financial/model basis |

“Missing” means absent or unusable in this specifically audited retained bundle.
It does not claim that no public statements exist for the company. An explicit
form/business gate is independent of financial access. Three reference-only
issuer linkages remain unresolved; the 27 verified security linkages represent
26 unique CIK issuers because the Alphabet classes share an issuer.

Reproduce from the repository root after installing backend test dependencies:

```powershell
New-Item -ItemType Directory -Force .phase67.local | Out-Null
backend/.venv/Scripts/python.exe backend/scripts/replay_financial_model_coverage.py --output .phase67.local/model-coverage-after.json --matrix-output .phase67.local/model-coverage-after.md
```

The script reads maintained small public excerpts, blocks concrete HTTP
transports, builds an in-memory SQLite registry and uses the frozen sample
clock. It does not load application credentials, connect to the development
database or acquire source data. Output files remain ignored.

### Separately acquired financial sample: eight issuers, nine securities

The approved acquisition expands the local audit evidence with AMZN, Alphabet,
O and PGR, while refreshing MSFT, NVDA, ORCL and JPM companyfacts. It does not
import these documents into the website's development database or claim that
the production on-demand paths have independently acquired them.

| Issuer | Annual periods in full acquired document | Standalone quarterly periods | Latest normalized annual period | Important source/financial limits |
| --- | --- | --- | --- | --- |
| MSFT | 17 | 69 | 2025-07-01 to 2026-06-30 | Complete conventional debt remains unavailable despite current/noncurrent long-term observations; aggregate D&A is not supplied by separate depreciation/amortization fields |
| NVDA | 17 | 71 | 2025-01-27 to 2026-01-25 | Complete debt/enterprise claims remain unverified; no new split history, target multiple or quote was acquired |
| ORCL | 17 | 69 | 2025-06-01 to 2026-05-31 | Explicit diluted-common numerator supports its own EPS diagnostic; selected-security share basis, aggregate D&A, cash-flow/enterprise claims and current market evidence remain incomplete |
| JPM | 17 | 70 | 2025-01-01 to 2025-12-31 | Explicit diluted-common numerator is separate from consolidated net income; suitable common-equity/class scope remains necessary; industrial enterprise methods remain inappropriate |
| AMZN | 17 | 70 | 2025-01-01 to 2025-12-31 | Current-plus-noncurrent debt differs from the combined long-term concept by USD 440 million; total debt remains unavailable instead of choosing a convenient scope |
| GOOGL / GOOG | 11 | 46 | 2025-01-01 to 2025-12-31 | Debt representations differ by USD 542 million, consistent with a scope/gross-net reconciliation issue that is not resolved automatically; class ownership/splits remain separate, and GOOG form remains unresolved |
| O | 16 | 66 | 2025-01-01 to 2025-12-31 | No independently mapped complete AFFO/forecast/target; common dividends and broad D&A do not manufacture REIT AFFO or eligible ordinary earnings methods |
| PGR | 17 | 70 | 2025-01-01 to 2025-12-31 | Restricted-cash scope is not unrestricted cash and equivalents; insurance equity/earnings require their own basis; no industrial EV shortcut |
| Total | 129 | 531 | Eight separately owned reporting issuers | Financial source coverage, not eight eligible valuations |

The four previously unrepresented acquired issuers contribute **61 annual and
252 quarterly** periods in their full raw documents. The raw documents stay
ignored. The maintained
`backend/tests/fixtures/valuation/phase67_sec_financial_excerpts_2026_10_20.json`
is a **464,114-byte, 886-original-observation** deterministic excerpt, not a full
provider document. It retains revenue/earnings/EPS/shares for four annual
intervals per issuer and other mapped metrics for the latest annual interval
only, including native and comparative candidates for those selected fields.
Missing fields in the excerpt cannot prove that the full issuer document lacks
them. Full-document normalization counts above must not be attributed to the
limited fixture.

Replay this distinct source mode without making another provider request:

```powershell
backend/.venv/Scripts/python.exe backend/scripts/replay_financial_model_coverage.py --approved-excerpts --output .phase67.local/approved-model-coverage.json --matrix-output .phase67.local/approved-model-coverage.md
```

The acquisition clock is **2026-10-20T12:02:07.066938+00:00**. Eight reporting
issuers produce nine sampled securities because GOOG and GOOGL retain separate
instrument/listing identities. Each has four curated annual periods, giving
financial evidence to all nine sampled securities without transferring a
per-class price target. All nine currently produce **zero eligible and zero
published default estimates** across all eleven models. Section 11 separates
the current proof/freshness result from the dated 30-security baseline.

## 10. Real versus fixture-based evidence

Listing excerpts are real dated public observations; financial evidence is
separately retained and dated. Mocked/synthetic pipeline tests never count as
new live financial coverage. The retained 30-security and newly approved
nine-security results have separate source modes, audit clocks and denominators.

| Evidence mode | What was evaluated | What may be claimed |
| --- | --- | --- |
| Retained public listing evidence | 30 actual dated directory excerpts, with original source/record hashes and SEC linkage evidence | Dated observed membership/form/linkage, within the documented identity limits |
| Retained public financial evidence | Small maintained evidence windows for AAPL, MSFT, NVDA, ORCL and JPM | Exact reproduced dated financial values and current default eligibility for this replay only |
| Read-only retained raw-cache replay | Five previously acquired SEC companyfacts snapshots, 435 normalized periods | Normalization preservation and added explicit dividend scopes; no fresh acquisition claim |
| Newly approved live financial evidence | Eight actual approved SEC snapshots; nine separately gated securities in the limited maintained replay | Actual audited financial availability and precise current blockers; no current default valuations or website-database ingestion claimed |
| Mocked transport | FastAPI/provider-denial/browser fixtures | Request boundaries, serialization, error handling, rendering and identity isolation |
| Synthetic financial scope fixture | Three annual reviewed-contract examples installed only by tests | Scope-validation behavior and guarded NWC/borrowing forecast wiring; no real issuer/model-coverage claim |

The scope fixture has a clearly labeled synthetic taxonomy and original-value
examples. Positive tests install a test-only reviewed mapping with `monkeypatch`.
Production keeps `REVIEWED_FORECAST_SCOPE_CONCEPTS = {}`. Provider annotations,
configuration, `scope_complete=true`, a source label or a forged concept name
cannot replace a code-reviewed economic contract or exact raw-observation match.

AI verification uses retained/mocked responses only. Typed references,
server-owned citations, independent numeric/category/privacy validators, exact
provenance, evidence-change cache invalidation and selected-security isolation
remain active. No AI-generated financial calculation is introduced, and no
live AI response or new market coverage is claimed.

## 11. Coverage improvements and remaining limitations

The new 13-stage inventory exposes the actual bottlenecks independently. These
are the **after-implementation** counts in the same frozen 30-security sample;
the before/after numerical valuation comparison is in Section 8. Newly exposed
stage definitions were not retroactively presented as historical API outputs.

| Independent stage | Available / sampled | Meaning and limit |
| --- | --- | --- |
| Verified issuer/security identity | 27 / 30 | 26 unique verified CIK issuers; unresolved placeholder IDs do not count |
| Verified dated active listing | 30 / 30 | Dated directory evidence, not a live trading/halts guarantee |
| Security form | 28 / 30 | GOOG and TSM remain unresolved from these explicit descriptions |
| Eligible security/sector workflow | 23 / 30 | At least one applicable framework after identity/form gates; required financial inputs can still be missing |
| Financial statements | 5 / 30 | At least one finite validated annual fact, not an empty/quarantined period |
| All 18 inventory metrics complete | 0 / 30 | Explicit latest-period inventory; not a universal model prerequisite or confidence score |
| Sufficient historical periods | 4 / 30 | At least one supported three-year growth window, requiring four aligned annual observations |
| Compatible currency and share basis | 3 / 30 | Independently supported selected-security and comparison currency basis |
| Required valuation assumptions | 3 / 30 | An applicable model has a nonempty supported forecast/rate/multiple path, independently of its missing facts/compatibility; Graham is not counted merely for having no forecast assumptions |
| At least one eligible default model | 2 / 30 | AAPL/MSFT Forward P/E only |
| At least two independent model families | 0 / 30 | Explicitly **unverified**; counting method families does not establish independent financial evidence |
| Fresh provider quote | 0 / 30 | Requires valid compatible observed price, zoned nonfuture observation within two days, and explicit fresh provider status |
| Published dated estimate | 2 / 30 | Policy-based single-model outputs; not robust multi-model confirmation or current quote coverage |

The 18-metric inventory is revenue, net income, operating income, operating cash
flow, capex, FCF, cash, debt, interest expense, assets, liabilities, shareholder
equity, diluted/basic weighted shares, point-in-time shares, diluted EPS, cash
dividends and D&A. Canonical validated facts take precedence over raw amounts:
a quarantined canonical value cannot become “available” through a raw-metric
fallback. Original observations remain available for inspection.

The implementation improves reproducibility, normalization scope and explanation
quality. It does **not** increase default eligible models or financially covered
issuers in this sample. Complete enterprise claims, defensible NWC/borrowing,
current compatible quotes, sector-specific common-equity/AFFO evidence and
foreign accounting/share conversions remain unresolved where their evidence is
absent. The approved SEC audit expanded actual financial evidence and identified
specific numerator and debt-scope issues; it did not establish another eligible
default model. Its current, separately measured results follow.

### Current clock with approved financial excerpts

| Independent stage | Available / nine sampled securities | Interpretation |
| --- | --- | --- |
| Current verified issuer/security identity | 0 / 9 | Existing dated SEC issuer-symbol proof exceeds its original freshness policy; the financial CIK is still matched exactly |
| Current verified active listing | 0 / 9 | The 19 October listing evidence is beyond its existing 24-hour TTL at the 20 October acquisition clock |
| Security form | 8 / 9 | Original explicit descriptions remain; GOOG form is still unresolved |
| Eligible current security/sector workflow | 0 / 9 | Current identity/listing gates remain closed independently of new financial facts |
| Validated financial statements | 9 / 9 | Four selected annual periods for each security, covering eight actual reporting issuers |
| All 18 inventory metrics complete | 0 / 9 | Missing or scope-conflicted metrics remain unavailable |
| Sufficient historical periods | 9 / 9 | At least one supported three-year growth window; does not prove all model histories or splits |
| Compatible quote currency and selected share basis | 0 / 9 | No new quote, split or class-ownership proof; matching reporting currency alone is insufficient |
| Required current valuation assumption path | 0 / 9 | Current applicability/identity and remaining source-specific paths do not support publication |
| At least one eligible current default model | 0 / 9 | All eleven models remain gated per security |
| At least two independent model families | 0 / 9 | Explicitly unverified; no independence is manufactured |
| Fresh provider quote | 0 / 9 | No quote was acquired in this SEC-only audit |
| Published current default estimate | 0 / 9 | No price target is published from this audit |

These results do not mean the reporting issuers disappeared or their facts have
no identity. The financial snapshot's CIK is verified against the exact selected
issuer, while the proof required to publish a **current quoted-security**
valuation has expired. A companyfacts response does not renew a ticker/exchange
directory or active-listing observation. The replay applies the real 20 October
clock rather than freezing the listing clock to force an eligible result.

Actual financial-data expansion is therefore verified in the local audit, while
the central multi-model valuation objective remains open. No population-wide
financial coverage rate, new website database coverage or robust multi-model
consensus is claimed from these samples.

## 12. Database migrations and preservation

No new Alembic migration is introduced. This phase does not import observations,
refresh financial caches, edit user assumptions, write application financial
rows, reset a database or replace a volume. The Phase 6.6 issuer-ownership and
reused-ticker model remains authoritative.

The raw-cache normalization comparison runs in memory. The sample audit uses a
disposable in-memory SQLite registry. Tests requiring PostgreSQL use the
dedicated guarded local `_test` database; they are not permission to reset the
development database.

Read-only before/after inspection confirms identical registry counts and
identical content hashes for all five development financial tables: companies,
financial facts, financial snapshots, market snapshots and cache entries. Their
original values, timestamps and provenance remain unchanged. The comparisons
are retained in ignored local verification artifacts, separately from mocked
or disposable-database tests.
The post-acquisition read-only comparison also matches the original counts and
all financial-table hashes; downloaded source files and offline replay did not
refresh development financial rows or caches.

## 13. Frontend changes

The existing dashboard layout, typography system, editable assumptions, weights,
scenario selection, sensitivity and reverse DCF remain in place. Provider-mode
numbers remain Python outputs; the frontend makes no replacement estimates.

Model rows expose a compact count of structured blocking issues. Details and
the excluded-model panel show each category, explanation and affected fields
alongside existing financial-path/provenance records. Several causes remain
visible instead of collapsing to a generic unavailable label.

Data completeness adds a period table with fiscal identifiers, exact dates,
available/missing metric lists, original source identifiers and warnings.
Separate cards display server assessments of the selected-security share basis,
reporting/trading currency, accounting evidence and market-price freshness.
Missing additive metadata stays unassessed or absent; it is not interpreted as
compatible or eligible. Original exact values/provenance remain available in
existing disclosures.

A one-contributing-model result carries a prominent limited-coverage warning.
Unavailable estimates remain unavailable rather than zero or substituted demo
figures. Provider quote observation dates stay separate from financial retrieval
dates and optional manual comparison prices. Desktop/mobile tables scroll
within their section; compatibility cards stack on narrow screens. All new UI
code uses JavaScript/JSX.

## 14. Test results

All final checks passed, including the complete backend run after the final
non-additive diluted-common-income safeguard. The backend run passed 1,735 tests
in 237.66 seconds, with zero failures, errors, skipped tests or external HTTP
attempts. Focused runs are not added to this full-suite count.

| Check | Phase 6.7 result |
| --- | --- |
| Complete backend and PostgreSQL acceptance | 1,735 passed; zero external HTTP attempts |
| Frontend unit tests | 80 passed |
| Full desktop/mobile browser tests | 160 passed |
| ESLint | Passed |
| Frontend production build | Passed |
| Python dependency consistency (`pip check`) | Passed |
| Frontend dependency consistency (`npm ls --depth=0`) | Passed |
| All 330 retained security/model decisions and default values | Zero changes |
| Development financial table hashes and registry counts | Identical before/after |

The backend acceptance includes PostgreSQL migration/persistence/rollback,
concurrency and 10,000-listing scale tests. Concrete external HTTP is blocked in
the automated suite. One upstream Starlette/TestClient/httpx deprecation warning
was present in the final full run; no failing check was suppressed for it.

Added and retained verification covers:

- Exact interval support, direct versus signed-YTD quarters, instant/duration
  mismatch, dividend scopes, narrow PP&E depreciation and retained normalization
  preservation.
- Exact raw source identity/value/context, missing or forged scope, incompatible
  currencies, future dates, unknown versus verified-zero values, duplicate or
  conflicting observations, incomplete financing and working-capital histories.
- Issuer, listing and sibling-class isolation; source fields and provider
  annotations cannot install a production scope contract.
- All eleven model requirements, unchanged AAPL/MSFT defaults, negative
  missing-evidence coverage, no false cash-flow alternative blockers, independent
  freshness/compatibility, and API serialization of additive diagnostics.
- Existing PostgreSQL migrations, persistence, rollback limits and ticker-reuse
  safeguards; existing deterministic equations, scenario and sensitivity checks.
- Existing AI typed-reference/citation/numerical/category/privacy regressions and
  security/evidence isolation using offline fixtures.
- Frontend unavailable states, every server blocker, reporting periods, exact
  provenance, partial contracts, single-model warnings, and desktop/mobile
  overflow behavior.

Automated tests block concrete external HTTP. No live OpenAI/provider request,
automatic retry, fresh quote, source import or financial acquisition is part of
these checks. Final `git diff --check` is recorded by the root verification run.
The application version is `0.6.7`;
the deterministic valuation engine remains `1.1.0`.

## 15. Licensing and provider blockers

Public display/redistribution rights require confirmation. FMP entitlements,
foreign accounting/FX/ADR conversion and complete AFFO scope are not presumed.

The existing official-source documentation references and licensing discussion
remain in [the Phase 6.6 source audit](phase66-source-license-audit.md). SEC
fair-access identification, bounded traffic and endpoint availability remain
required. An FMP key does not establish plan access to every endpoint, and a
successful request would not establish a redistribution license. HTTP 402,
401/403 and 429 are preserved as restrictions/errors, not worked around.

No unauthorized paid endpoint is probed. No provider content is scraped to evade
an entitlement or license. Nasdaq/other public source display and redistribution
rights remain a launch blocker. Local engineering verification is not launch
authorization.

## 16. Approved provider requests executed

The separately approved plan executed **exactly eight sequential GETs**, each
returning **HTTP 200**, between 12:01:51 and 12:02:07 UTC on 20 October 2026.
Total transfer was **36,961,056 bytes**, below the 96,000,000-byte total limit.
Every response was below 12,000,000 bytes. Concurrency was one, requests were at
least one second apart, and each retained the 30-second total timeout with
**zero retries and zero redirects**. No additional provider request was made.

Each URL was exactly
`https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json`, using the CIK below.
The existing identifying SEC User-Agent was sent only to SEC; its configured
contact address is not reproduced. The bundle included no API key, user
financial override or chat history. No provider charge is known for these SEC
requests; acquisition does not establish public redistribution rights.

| Issuer | Exact CIK | Bytes | Retrieved at, UTC | Full-source SHA-256 |
| --- | --- | --- | --- | --- |
| MSFT | 0000789019 | 4,881,196 | 2026-10-20 12:01:53.080073 | `f8aae2965b20ad0df44bdf7ccbedf797d275b6b8dc030154a7a311361bb7246f` |
| NVDA | 0001045810 | 4,092,966 | 2026-10-20 12:01:54.794860 | `19ef503a5770f5660964b3c3aea6937579d9b359da344afe6a9adf59c63d26ff` |
| ORCL | 0001341439 | 3,962,105 | 2026-10-20 12:01:56.233414 | `65523545f040abaea1dfcf321da2a5aec85e7f34387244b0ffcb26e4c8707f7d` |
| JPM | 0000019617 | 7,988,348 | 2026-10-20 12:01:58.149637 | `284d6f3ce6364f94216dddb45172203a825475f0bd75b633a2036b903181e902` |
| AMZN | 0001018724 | 4,478,611 | 2026-10-20 12:02:00.087364 | `7549fb68446eee40e1f50a166fa06b2d2ee6349e07c8553a4828757e032d3cd4` |
| GOOGL | 0001652044 | 3,164,517 | 2026-10-20 12:02:02.690961 | `a017f26ee88cb4a639d1c1ddb06d53b4afe22f0ac89cabec7cd67c88919fe1c5` |
| O | 0000726728 | 3,235,550 | 2026-10-20 12:02:04.111396 | `676caac36e22f0d1087ec209f80728d2ab38536a1851d1f226daf27aaef44acb` |
| PGR | 0000080661 | 5,157,763 | 2026-10-20 12:02:07.064937 | `36a3229d38dd5d6c67968c481a413230070c351002f06350995a9cb113cf4d37` |

The raw snapshots and public-only acquisition manifest stay in ignored
`.phase67.local/`. A one-time guard prevents re-running the spent acquisition.
The maintained excerpt retains exact original rows, source hashes, URLs and
retrieval clocks rather than republishing complete downloaded histories.
Normalization, reconciliation and all subsequent replays run offline. No source
file was imported into the development database.

The branch fast-forward and earlier Phase 6.6 directory approvals are not fresh
authorization for additional access. This eight-request authorization is fully
spent. No FMP, Treasury, quote, submissions, directory refresh, OpenAI, automatic
retry, financial cache refresh, commit, push or deployment was performed. Any
additional source acquisition requires a separately scoped explicit approval.

`backend/.env`, keys/contact details, `.phase5.local/`, `.phase6.local/`,
`.phase65.local/`, `.phase66.local/`, `.phase67.local/`, provider caches,
databases, reports, screenshots, traces, virtual environments and installed
dependencies remain local/ignored. The intended deliverable contains source,
small labeled fixtures, automated tests and documentation. No raw provider cache
or generated private diagnostic is linked as a distributable artifact.

## 17. Proposed next-phase priorities

1. Resolve the documented current identity/listing-proof and source-specific
   financial blockers through separately reviewed work. The approved eight SEC
   acquisitions are complete; do not repeat them or promise model gains from
   another download without identifying an exact missing evidence contract.
2. Review economically exhaustive concept mappings for operating working
   capital and debt cash flows. Admit a mapping only with original filing scope,
   annual alignment and negative tests; generic scope annotations are insufficient.
3. Complete source-supported debt and enterprise-to-equity claims, common
   earnings/equity ownership and appropriate discount-rate capital inputs.
4. Seek separately authorized quote/split/multiple evidence only for the exact
   remaining blockers and permitted subscriptions; preserve dated retained
   estimates when freshness is not established.
5. Evaluate bank/insurance common-equity methods and company-specific REIT AFFO
   disclosures without importing industrial assumptions.
6. Resolve explicit class/venue mappings and independently verified foreign/ADR
   reporting, currency and ownership conversions, then confirm publication rights.

These are proposed priorities, not work started in Phase 6.8. Phase 6.7 remains
open on its main multi-model objective despite verified audit-only financial
evidence expansion. Current identity/listing renewal, compatible share/currency
and quote evidence, complete model-specific scopes and publication permissions
remain the precise handoff; some issuers may still support no additional model
after those issues are reviewed.

Approval to obtain a financial snapshot would not refresh listing proof, extend
its existing TTL, establish a fresh quote or authorize publishing a current
default estimate from dated evidence. Listing identity, financial filing,
quote observation, retrieval and calculation dates remain independent.
