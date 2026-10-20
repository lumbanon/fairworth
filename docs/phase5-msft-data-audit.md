# Phase 5 MSFT share and debt evidence audit

Reviewed on 2026-10-15 against the existing local SEC/FMP snapshots. No OpenAI
call or additional financial-provider request was needed for this audit. The
retained SEC companyfacts cache was retrieved at
2026-10-15T06:29:45.656013+00:00. Values below describe that dated snapshot, not
an assertion of current-day financial or market data.

## Shares are available on a dated filing basis

The quote endpoint did not return a usable `sharesOutstanding`, so the quote's
current-share field correctly remains unavailable. This does not mean SEC share
evidence is missing. The existing automatic engine already uses the valid dated
common-share observation, retaining its date and share-class limitation.

| Source concept | Exact shares | Observation period | Interpretation |
| --- | ---: | --- | --- |
| `dei:EntityCommonStockSharesOutstanding` | 7,425,545,491 | 2026-07-23 | Latest valid filing-cover common shares; not a live quote count |
| `us-gaap:CommonStockSharesOutstanding` | 7,427,000,000 | 2026-06-30 | Annual period-end common shares |
| `us-gaap:WeightedAverageNumberOfSharesOutstandingBasic` | 7,429,000,000 | FY2026, 2025-07-01–2026-06-30 | Annual weighted basic denominator |
| `us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding` | 7,453,000,000 | FY2026, 2025-07-01–2026-06-30 | Annual weighted diluted denominator; retain for reported EPS |

All four observations use `shares` units and SEC accession
`0001193125-26-323660`, filed 2026-07-29. MSFT is identified as a single listed
common-share class in the existing company snapshot. The automatic valuation
denominator is 7,425,545,491 with observation date 2026-07-23; replacing annual
weighted diluted shares when reconciling reported historical EPS would be wrong.

The existing permitted FMP `shares-float` audit returned HTTP 200 with
`outstandingShares=7425550000`, processing timestamp `2026-10-13 21:32:45`, and
the same July 10-K as its source. This number differs from the precise SEC cover
count by 4,509 shares and appears rounded. The processing timestamp does not
independently establish the share-observation date. Promoting it to a verified
current-day count, or dividing market capitalization by price to invent a share
count, is therefore unjustified. No provider entitlement restriction prevents
reading this endpoint, but access alone does not resolve its dating semantics.

## Available long-term components do not establish complete debt

The same FY2026 accession reports the following instant USD facts at 2026-06-30:

| SEC concept | USD | Scope |
| --- | ---: | --- |
| `LongTermDebtCurrent` | 9,227,000,000 | Current maturities of long-term debt |
| `LongTermDebtNoncurrent` | 31,067,000,000 | Long-term debt excluding current maturities |
| `LongTermDebt` | 40,294,000,000 | Includes the two preceding components; excludes capital leases |
| `DebtInstrumentCarryingAmount` | 46,136,000,000 | Gross instrument amount before discounts/premiums and issuance costs |
| `FinanceLeaseLiability` | 66,594,000,000 | Separately scoped finance-lease liability |
| `OperatingLeaseLiability` | 21,925,000,000 | Separately scoped operating-lease liability |

The current/noncurrent sum reconciles to `LongTermDebt`; adding current
maturities to that aggregate again would double count them. That reconciliation
does not verify that all short-term borrowing categories are absent. The full
retained companyfacts inventory shows:

- `DebtCurrent` is absent.
- `ShortTermBorrowings` was last reported for 2018-06-30 (zero).
- `CommercialPaper` was last reported for 2025-06-30 (zero).
- `DebtLongtermAndShorttermCombinedAmount` was last reported for 2015-03-31.

Old explicit zeros cannot supply missing FY2026 balances. Gross instrument
amounts, net long-term debt, lease liabilities and long-term-debt fair value are
different bases; substituting or summing them without compatible, complete scope
would manufacture a total. Available-for-sale *debt securities* are assets and
must not be mistaken for the issuer's financing liabilities. Supplemental FMP
annual balance-sheet and cash-flow endpoints were HTTP 402 in the existing
permitted-source audit and provided no reconciliation evidence.

The existing normalization gate is appropriate: `total_debt` remains `None`
while original unmapped facts remain available in source provenance. A defensible
future correction needs a dated statement or debt-note reconciliation proving
short-term coverage and a consistent lease policy, with matching units, currency,
period and accession. It should not infer a zero from absent tags.

## Valuation and verification

No provider, normalization, model formula, input value or eligibility rule was
changed by this audit. The retained-snapshot base Forward P/E result remains
`619.5604742486083` USD (displayed `$619.56`) with only `pe` contributing at
weight 1 and `policy_based` classification. Its low-quality and single-model
warnings must remain. Missing complete debt is only one of several independent
enterprise-valuation gates; filling it alone would not establish valid FCFF or
EV multiple models.

The small maintained fixture
`backend/tests/fixtures/valuation/msft_shares_debt_excerpts.json` retains exact
selected SEC observations, original concept definitions, accession/dates/units,
the public FMP share-float excerpt, and full-cache concept-presence audit
metadata. It is explicitly an excerpt, not a replacement full companyfacts
dataset. Four deterministic regressions in `backend/tests/test_msft_source_audit.py`
check distinct share denominators, missing short-term scope, preserved debt/lease
facts, and the unchanged single-model valuation. Full raw provider data remains
only in the ignored local verification directory.

Sources: [SEC companyfacts](https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json),
[original filing](https://www.sec.gov/Archives/edgar/data/789019/000119312526323660/msft-20260630.htm).
Both links identify the retained snapshot's provenance; this audit used the
local snapshots and did not claim an independent live filing fetch.
