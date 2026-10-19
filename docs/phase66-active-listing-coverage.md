# Phase 6.6 — Verified listings and financial coverage

Implementation audit date: 19 October 2026. Verification results below are updated
only after the corresponding checks complete. No live OpenAI request is permitted.

## 1. Executive summary

Phase 6.6 adds source-backed listing observations, conservative security-form
classification, independent issuer business categories, identity-safe cross-source
enrichment, reused-ticker financial ownership, ten independent coverage stages and
clearer search/company provenance. The eleven valuation equations remain unchanged.

The approved acquisition completed exactly two Nasdaq directory GETs and one SEC
ticker/exchange-directory GET, all on 19 October 2026, with zero retries. The
development registry now contains 17,060 listing records, including 13,248 dated
active listing observations and 6,661 recorded CIK-linked verified identities.
These are different capabilities and denominators, not a count of valuatable stocks.

The separate 30-security real listing audit establishes 30 active observations,
27 verified security identities and 28 recorded security forms. Five securities
have retained financial statements; three have a compatible share basis and two
retain an illustrative single-model policy valuation. No new financial histories
or live AI responses were acquired. Public redistribution rights remain unresolved.

## 2. Starting branch and commit

Branch: `feature/phase-6-6-active-listing-coverage`. Starting implementation commit:
`0506073d3fb4506281bf2cb9335a85ec9963fe8b` (completed Phase 6.5). The branch initially
pointed to Phase 6; the user expressly approved the dependency fast-forward. No
branch switch, merge commit, Phase 6.6 commit, push or deployment was performed.

## 3. Baseline limitations

The [pre-implementation baseline audit](phase66-baseline-audit.md) records 8,030
issuers and 10,444 reference-only, unknown-type/status listings. SEC CIK/ticker
references did not prove current listing, security form or financial share basis.
Five issuers had retained financial snapshots. The unique financial ticker index
blocked a second issuer reusing a ticker. Eight coverage cards conflated some
listing/classification/financial capabilities.

## 4. Listing sources evaluated

The [source/license audit](phase66-source-license-audit.md) evaluates official
Nasdaq Trader text directories, NYSE reference/security-master products, SEC
references/submissions/facts and documented FMP directory/profile/lifecycle APIs.
The local parser supports the two documented Nasdaq files; no downloader or
unattended scheduler is added to the application.

## 5. Access and licensing

The user approved two sequential Nasdaq file requests and a separately bounded
SEC reference-directory request. All three GETs returned HTTP 200 and stayed
within their 5 MB/file and 30-second bounds, without retries or redirects. Actual
transfer was 1,416,449 bytes in total. No FMP, Treasury, company-facts, submissions
or OpenAI requests were made. The SEC request used the existing identifying
User-Agent; credentials and contact details are excluded from public artifacts.
NYSE products and FMP account-specific access are not presumed licensed. Local
evaluation does not resolve public display/redistribution rights, which remain
launch blockers requiring operator confirmation.

## 6. Implementation files

- Registry: SQL models, `registry/{schemas,repository,service,importers}.py`, new
  `listing_sources.py`, `verification.py`, `coverage_audit.py` and administrative
  `scripts/audit_listing_coverage.py`.
- Reproducible offline audit: `scripts/replay_verified_coverage_sample.py` and
  `tests/phase66_coverage_helpers.py` replay the dated public listing fixture and
  separately retained financial evidence with HTTP blocked.
- Financial identity: company model/repository, SEC reporter-regime metadata,
  company service/schema, security identity/cache helper, coverage service/schema,
  valuation input compatibility and eligibility policy.
- AI: bounded listing identity/provenance, exact public source URL support,
  evidence-context priority, report cache identity and listing-aware instructions.
- Frontend: search/header, coverage panel, workspace identity adapter, source-link
  filters and scoped CSS. JavaScript/JSX only; existing design is preserved.
- Tests: listing imports, ownership/migrations, independent coverage aggregates,
  AI listing isolation, actual API serialization, existing registry-scale tests,
  frontend units and desktop/mobile browser scenarios.
- Documentation: this report, baseline/source audits and README operation notes.

No dependency or lockfile update is required. Existing small public SEC/financial
fixtures remain retained evidence. The new
`backend/tests/fixtures/registry/nasdaq_listing_sample_2026_10_19.json` is 82,451
bytes and contains 30 actual public listing excerpts plus dated SEC linkage
evidence. Synthetic rows remain explicitly test data. Raw provider files, logs,
screenshots and generated audit reports remain ignored.

## 7. Database migrations

`0003_listing_observations` adds immutable source assertions and additive
classification/verification fields. `0004_financial_issuer_ownership` maps every
existing company to an exact CIK-linked registry issuer, preserves company IDs,
and replaces global ticker uniqueness with `(ticker, issuer_id)` uniqueness.
Different share-class buckets belonging to one issuer remain separate.

Invalid/ambiguous legacy CIK mappings abort before DDL. New ticker reuse requires
an explicitly registered matching issuer; bare-symbol conflicts still fail closed.
No fact, quote or snapshot is reassigned. Downgrade refuses duplicate tickers
instead of merging/deleting financial history. Native PostgreSQL ALTER preserves
child rows. Populated SQLite with foreign keys enabled is deliberately refused
because parent-table rebuilding can cascade; PostgreSQL is the production target.

Both migrations were applied to the existing development PostgreSQL database
after offline and dedicated-test-database verification. Preservation hashes for
all original columns of five companies, 165,486 financial facts, nine financial
snapshots, 14 quotes and 64 cache entries matched before and after the upgrade
and approved registry imports. No database reset or source-data deletion occurred.
Equivalent zero-padded legacy CIK representations resolve through a bounded
indexed lookup; ambiguous normalized CIKs are rejected rather than creating a
second issuer or moving historical ownership.

## 8. Listing verification design

Each immutable observation retains listing/refresh IDs, source record key/hash,
original public row, source kind, observation/publication/retrieval clocks and
parser version. Derived verification identifies the source and confidence.
Directory membership is a dated listing observation, never a no-halt guarantee,
listing commencement date or verified share basis. Unknown publication timezone
stays unknown; the footer is never converted to invented UTC.

Issuer-symbol linkage has its own SEC source, observation date, snapshot version,
CIK, symbol and venue. A new exchange directory never refreshes that proof.
Missing, future, mismatched or expired issuer proof demotes the selected identity
to reference-only while preserving the independently verified listing observation.
An unavailable profile request cannot restore current ownership. Conversely, a
new SEC reference does not refresh an older exchange-listing observation. Both
proofs participate in scoped analysis and AI cache identity.

## 9. Classification mapping

Explicit descriptions and ETF flags distinguish common shares, ordinary shares,
ADR/ADS, ETF, closed-end fund, preferred, warrant, right and unit. Unknown remains
unknown; neither ticker suffix nor ETF=N establishes common stock. Financial-status
deficiencies are warnings, not suspensions. Security form and issuer business
category are separate. Exact issuer-scoped SEC SIC evidence can identify banks,
insurers and REITs; it does not change their quoted security form.

In the approved sample, GOOG's “Capital Stock” description and TSM's absent form
descriptor remain unknown. NVO's `common_stock` label records its directory
description only: it does not establish domestic issuer status, an ADR ratio or
compatible foreign per-security accounting. AGNCN is explicitly preferred and
SPY is explicitly an ETF; neither inherits common-stock intrinsic values.

## 10. Stable identity

Existing issuer/instrument/listing UUIDs survive a unique exact symbol or explicit
source alias plus venue/SEC issuer linkage. Names or CIK alone never merge
instruments. Separate GOOG/GOOGL classes remain separate. Source rows may establish
a listing without establishing its issuer; that remains reference-only for
financial ownership. Symbols are not permanent security IDs. Ambiguous/reused
source mappings require reconciliation; no rename/transfer relationship is invented.

## 11. Refresh, conflicts and retention

Imports validate fully and publish atomically under the existing administrative
database lock. Exact reimports are idempotent. Old observations remain auditable
without rolling current fields backwards. Listing-authority observations take
precedence over unknown SEC reference fields. Explicit disagreements remain
conflicted and inspectable. Large unexpected directory losses are quarantined;
omission never delists a security.

Refresh memory uses latest source observations rather than loading complete
historical payloads. History inspection is paginated. Retention is a bounded
dry-run review that protects referenced identity/source history and deletes nothing.
Long-term archive storage still needs an operator policy and capacity monitoring.

## 12. Financial integration

The workflow resolves stable identity, checks caches, retrieves only needed
authorized issuer data, normalizes source observations, reconciles share/currency
basis and evaluates existing models. Listing refresh does not refresh statements.
No allowlist or market-wide financial ingestion is introduced. SEC annual forms
distinguish reporter regime without asserting currency or accounting standard.
Foreign common shares cannot inherit domestic share/currency assumptions.

Debt completeness, period alignment, common-equity scope, enterprise bridges,
discount-rate provenance, model independence and low-quality/single-model warnings
remain enforced. Unsupported funds/specialized securities remain discoverable.
IFRS normalization, FX translation and non-unit ADR conversion remain unavailable.

## 13. Representative company audit

Two evidence sets are reported separately. The approved 30-security audit uses
actual 19 October 2026 Nasdaq listing observations and the separately approved
SEC reference snapshot, with existing dated financial excerpts replayed offline.
The earlier 25-security / 24-issuer sample remains a retained Phase 6.5 baseline.
Neither sample establishes current market capitalization, IPO dates or a complete
historical delisting/corporate-action record.

### Approved 30-security listing audit

As of `2026-10-19T11:56:54.533345Z`, all 30 securities have dated active listing
observations; 27 have verified issuer/security linkage and 28 have recorded
security forms. There are **26 unique CIK-linked issuers**, plus three unresolved
registry issuer IDs. The reproducible audit counts only linked issuers in
`issuer_denominator`; unresolved IDs remain inspectable in its evidence but do
not count as verified issuers. GOOG and GOOGL remain separate securities sharing
one verified issuer.

The sample has three compatible share bases; five retained statement,
normalization and AI-evidence sets; two securities with one contributing default
policy model each; and two excluded specialized forms (ETF/preferred). Profiles
are available for 22/30 in the retained bundle. No fresh statement, profile,
quote/history, FMP, Treasury or AI request was made. Missing evidence means absent
from this bounded audit, not that the company lacks public financial statements.

Three listing observations intentionally remain unlinked to a verified issuer:
BRK.B lacks an explicit source-proven BRK-B alias; CMT's SEC NYSE reference differs
from its Nasdaq directory NYSE American venue; and SPY's SEC NYSE reference differs
from its NYSE Arca listing. Neither name/CIK inference nor punctuation conversion
silently resolves those mismatches. O/PLD and the bank/insurance examples retain
their sourced issuer information without treating a directory common-share label
as proof of sector applicability or financial completeness.

The following matrix uses real dated listing observations. Every financial cell
is separately labeled retained evidence; the table is not a fresh financial audit.

Listing sample: 30 securities; listing observations: real_verified; financial evidence: retained_public; audited as of 2026-10-19T11:56:54.533345+00:00.

| Symbol | Issuer / CIK | Exchange | Instrument type | Listing status | Verification source/date | Financial-statement coverage | Compatible share basis | Valuation eligibility | Contributing model count | Confidence | Main blocker |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AAPL | 0000320193 | NASDAQ | common_stock | active | nasdaq-trader-nasdaqlisted / 2026-10-19 | available (retained_public) | available | available | 1 | low | stale_sources |
| AGNCN | 0001423689 | NASDAQ | preferred | active | nasdaq-trader-nasdaqlisted / 2026-10-19 | financially_inapplicable (retained_public) | missing_evidence | financially_inapplicable | 0 | unavailable | unsupported_instrument_type |
| AMD | 0000002488 | NASDAQ | common_stock | active | nasdaq-trader-nasdaqlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| AMZN | 0001018724 | NASDAQ | common_stock | active | nasdaq-trader-nasdaqlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| BABA | 0001577552 | NYSE | adr | active | nasdaq-trader-otherlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | adr_share_basis_unverified |
| BAC | 0000070858 | NYSE | common_stock | active | nasdaq-trader-otherlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| BRK.B | Unresolved | NYSE | common_stock | active | nasdaq-trader-otherlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | security_identity_unverified |
| CMT | Unresolved | NYSE American | common_stock | active | nasdaq-trader-otherlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | security_identity_unverified |
| CRWV | 0001769628 | NASDAQ | common_stock | active | nasdaq-trader-nasdaqlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| GOOG | 0001652044 | NASDAQ | unknown | active | nasdaq-trader-nasdaqlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| GOOGL | 0001652044 | NASDAQ | common_stock | active | nasdaq-trader-nasdaqlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| GS | 0000886982 | NYSE | common_stock | active | nasdaq-trader-otherlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| JNJ | 0000200406 | NYSE | common_stock | active | nasdaq-trader-otherlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| JPM | 0000019617 | NYSE | common_stock | active | nasdaq-trader-otherlisted / 2026-10-19 | available (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| KO | 0000021344 | NYSE | common_stock | active | nasdaq-trader-otherlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| META | 0001326801 | NASDAQ | common_stock | active | nasdaq-trader-nasdaqlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| MSFT | 0000789019 | NASDAQ | common_stock | active | nasdaq-trader-nasdaqlisted / 2026-10-19 | available (retained_public) | available | available | 1 | low | stale_sources |
| NVDA | 0001045810 | NASDAQ | common_stock | active | nasdaq-trader-nasdaqlisted / 2026-10-19 | available (retained_public) | available | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| NVO | 0000353278 | NYSE | common_stock | active | nasdaq-trader-otherlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| O | 0000726728 | NYSE | common_stock | active | nasdaq-trader-otherlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| ORCL | 0001341439 | NYSE | common_stock | active | nasdaq-trader-otherlisted / 2026-10-19 | available (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| PG | 0000080424 | NYSE | common_stock | active | nasdaq-trader-otherlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| PGR | 0000080661 | NYSE | common_stock | active | nasdaq-trader-otherlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| PLD | 0001045609 | NYSE | common_stock | active | nasdaq-trader-otherlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| PLTR | 0001321655 | NASDAQ | common_stock | active | nasdaq-trader-nasdaqlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| SOFI | 0001818874 | NASDAQ | common_stock | active | nasdaq-trader-nasdaqlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| SPY | Unresolved | NYSE Arca | etf | active | nasdaq-trader-otherlisted / 2026-10-19 | financially_inapplicable (retained_public) | missing_evidence | financially_inapplicable | 0 | unavailable | unsupported_instrument_type |
| TSLA | 0001318605 | NASDAQ | common_stock | active | nasdaq-trader-nasdaqlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |
| TSM | 0001046179 | NYSE | unknown | active | nasdaq-trader-otherlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| WMT | 0000104169 | NASDAQ | common_stock | active | nasdaq-trader-nasdaqlisted / 2026-10-19 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | Required evidence, assumptions or economic compatibility checks prevent a default fair-value estimate. |

### Retained sample replay

All rows below are retained public evidence, not new listing verification.
`missing_evidence` means unavailable in this audited bundle, not that a company
has no public statements. The five financial rows retain their historical periods
and source clocks. Separate legacy default values remain in section 16.

Financial sample: 25 securities; mode: retained_public; as of 2026-10-19T12:44:30.645386+08:00.

| Symbol | Issuer / CIK | Exchange | Instrument type | Listing status | Verification source/date | Financial-statement coverage | Compatible share basis | Valuation eligibility | Contributing model count | Confidence | Main blocker |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AAPL | 0000320193 | Nasdaq | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | available (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| AMD | 0000002488 | Nasdaq | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| AMZN | 0001018724 | Nasdaq | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| BABA | 0001577552 | NYSE | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| BAC | 0000070858 | NYSE | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| BRK-B | 0001067983 | NYSE | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| CMT | 0001026655 | NYSE | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| CRWV | 0001769628 | Nasdaq | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| GOOG | 0001652044 | Nasdaq | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| GOOGL | 0001652044 | Nasdaq | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| JPM | 0000019617 | NYSE | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | available (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| KO | 0000021344 | NYSE | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| META | 0001326801 | Nasdaq | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| MSFT | 0000789019 | Nasdaq | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | available (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| NVDA | 0001045810 | Nasdaq | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | available (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| NVO | 0000353278 | NYSE | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| O | 0000726728 | NYSE | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| ORCL | 0001341439 | NYSE | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | available (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| PGR | 0000080661 | NYSE | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| PLTR | 0001321655 | Nasdaq | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| SOFI | 0001818874 | Nasdaq | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| SPY | 0000884394 | NYSE | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| TSLA | 0001318605 | Nasdaq | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| TSM | 0001046179 | NYSE | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |
| WMT | 0000104169 | Nasdaq | unknown | unknown | Unverified; sec-edgar reference / 2026-10-18 | missing_evidence (retained_public) | missing_evidence | missing_evidence | 0 | unavailable | instrument_classification_unverified |

The replay resolves 25/25 symbols belonging to 24 issuers; 23/25 profiles,
5/25 statement/normalized/AI-evidence sets, 0/25 verified active/class/share-basis
mappings and 0/25 newly scoped contributing valuations. No AI report is generated.

## 14. Active-listing count and denominator

The approved development import, audited as of 19 October 2026, preserves all
10,444 original issuer/instrument/listing UUID associations and now contains
17,060 listing records with 23,710 immutable source observations. Of those listing
records, 13,248 have source-backed active observations, including 6,661 recorded
verified CIK-linked identities; 3,812 retain unknown listing status. The same
13,248 meet the configured one-calendar-day freshness policy on the audit date.
That policy is not a trading calendar or a guarantee of uninterrupted trading.

| Security form among dated verified active observations | Count / 13,248 |
| --- | --- |
| Common-share directory description | 5,351 |
| ADR/ADS | 324 |
| ETF | 5,780 |
| Closed-end fund | 33 |
| Preferred | 465 |
| Warrant | 432 |
| Right | 124 |
| Unit | 345 |
| Unknown | 394 |

The 7,179 fund/preferred/warrant/right/unit observations are excluded from ordinary
operating-company valuation. The common-share form does not independently prove
US-domestic reporting or class-compatible financial evidence. There are 4,188
unknown forms across all 17,060 records, zero recorded authoritative listing
conflicts and zero future-dated observations. No persistent source-backed REIT
business classification is claimed by this registry aggregate; sourced financial
profile/sector analysis is a separate stage.

The imports accepted 5,621 Nasdaq-listed rows and 7,646 other-listed rows. Nineteen
other-listed records carry an undocumented exchange code and remain unverified;
their venue is not guessed. The current SEC file contains 10,443 reference rows;
the original 10,444 registry identities remain intact, and absence does not imply
delisting. Registry/source counts never stand in for financial coverage.

## 15. Financial statement coverage

Five retained issuers have nine snapshots and 165,486 original facts, all preserved
unchanged. The approved 30-security audit includes five securities with those
dated statements and normalized research evidence: AAPL, MSFT, NVDA, ORCL and JPM.
Three of the 30 have compatible selected-security share bases in this retained
bundle. The SQL registry aggregate identifies five verified listings with retained
issuer snapshots, which does not independently establish class compatibility.
No financial coverage is inferred for the remaining 17,055 registry records.

## 16. Eligible valuation coverage

Within the approved 30-security audit, AAPL and MSFT each have one contributing
policy-based Forward P/E model using retained compatible inputs. Their exact
fair values remain `214.2302568301956` and `619.5604742486083`, respectively,
matching the original unscoped historical regressions. Both retain low confidence,
limited quality, stale-source and single-model warnings. NVDA and ORCL remain
unavailable by default. These are dated illustrative policy estimates, not current
quotes or independently verified market-wide intrinsic values.

Two of 30 sampled securities have an eligible default model; zero have multiple
contributing model families. The other 28 remain unavailable, including the two
financially inapplicable ETF/preferred securities. No eligible-model count is
extrapolated to all 17,060 registry records. Unknown/reference-only, stale,
conflicted, foreign/ADR and unresolved share-basis cases retain their exact gates.

## 17. Before/after capabilities

| Capability | Phase 6.5 retained baseline | Phase 6.6 implementation / observed result |
| --- | --- | --- |
| Reference discovery | 10,444 records | 17,060 retained listing records; original 10,444 UUID associations preserved |
| Real verified active listings | 0 independently established | 13,248 dated active observations / 17,060 listing records on 19 October 2026 |
| Verified issuer/security identity | 0/25 in retained sample | 6,661 recorded registry identities; 27/30 in approved sample |
| Classification | Unknown in real registry | 28/30 sampled forms known; 5,351 active common-share descriptions; unknowns retained |
| Financial ownership | Unique ticker; reuse refused | Stable issuer FK; reuse supported without moving history |
| Financial issuers | 5 retained | Same five retained issuers and unchanged original financial rows; no fresh financial requests |
| Compatible selected-security share basis | 0/25 in retained reference-only sample | 3/30 in approved listing audit using retained financial evidence |
| Scoped eligible defaults | 0/25 in retained reference-only sample | 2/30 (AAPL/MSFT), one policy P/E each, historical exact values unchanged |
| Coverage explanation | 8 stages | 10 independent capabilities plus freshness |
| AI safeguards | Strict typed/cited numerical evidence | Preserved, with listing-observation identity/cache isolation |

## 18. Provider permission limits

Existing endpoint-specific 401/403, 402, 404, 429 and timeout handling remains.
Quote denial does not imply SEC statement denial. Valid caches avoid unnecessary
requests. Per-provider request budgets and FMP subscriptions are not bypassed.
Local keys do not prove permission to redistribute data to public users.

## 19. Frontend

Search and company headers distinguish verified observations, reference-only,
stale, conflicted, suspended and unsupported securities. Display symbols retain
canonical routes and stable selection IDs. Ten capability cards keep issuer
identity, active listing, classification and financial compatibility separate.
Expandable details retain exact source clocks and diagnostics. Sparse workspaces
remain usable; missing financial values never become zero.

## 20. AI Research compatibility

Adapter `financial-evidence-4` and prompt `fairworth-research-10` add bounded
listing proof and explicit instructions against active/share-basis inference.
The exact successful v8 fixture is unchanged. All independent binding, numerical,
category, citation, privacy and deterministic rendering rules remain authoritative.
Changed listing proofs separate evidence IDs and report caches even when financial
values are unchanged. Mixed proof/issuer/class/listing records fail before generation.
No live OpenAI request occurs in this phase.

## 21. Performance

The existing guarded PostgreSQL 10,000-synthetic-record benchmark is extended with
joint instrument/listing resolution, selective status filtering and cold/warm
mocked dashboard cache timings. Actual PostgreSQL EXPLAIN checks cover ticker,
alias and status indexes. Results are local synthetic measurements, not live
provider latency or production throughput.

The completed local PostgreSQL run imported 10,000 synthetic listings in 11.828
seconds. Individual measured operations were:

| Operation | Local synthetic time |
| --- | --- |
| Exact ticker search | 12.08 ms |
| Company-name search | 23.02 ms |
| Prefix autocomplete | 29.56 ms |
| Paginated search | 28.67 ms |
| 24 concurrent searches, total elapsed | 163.00 ms |
| Selective listing-status filter | 1.06 ms |
| Joint instrument/listing resolution | 8.23 ms |
| Cold mocked dashboard cache load | 32.85 ms |
| Warm scoped cache lookup | 3.65 ms |

EXPLAIN verified use of `ix_registry_ticker_prefix`, `ix_registry_alias_prefix`
and `ix_registry_listing_status`. The cross-worker coordinated loader executed
once. Cold/warm measurements use mocked data and cache operations; they do not
measure fresh provider downloads or establish production throughput.

## 22. Automated verification

The final full backend run passed **1,600 tests** in 198.98 seconds, including the
real public listing fixture, dedicated PostgreSQL persistence/migration and scale
checks, with zero real HTTP attempts. The only warning is an upstream
Starlette/httpx TestClient deprecation. No tests failed or were skipped.

The final frontend unit run passed **78 tests**. The complete browser suite passed
**156 checks** (78 desktop + 78 mobile). ESLint, the production build, `pip check`
and the installed frontend dependency check passed. The running application API
also passed read-only health/schema/search checks with HTTP blocked. Final diff
review found no configured credentials or sensitive/generated paths among the
intended changes. No live OpenAI validation is included or implied.

## 23. PostgreSQL preservation and rollback

The dedicated ownership migration test passed with zero HTTP attempts. It proves
unchanged original company/fact/snapshot/quote IDs and source values, matching
registry issuer ownership, safe ticker reuse, duplicate-ticker rollback refusal,
schema comparison and re-upgrade. The full backend run includes these checks.
Development migrations and approved imports subsequently preserved original row
hashes for five companies, 165,486 facts, nine financial snapshots, 14 market
snapshots and 64 cache entries; all 10,444 original listing/instrument/issuer UUID
associations also survived. The existing PostgreSQL database and volumes were
used without reset, replacement or deletion.

## 24. Remaining blockers

- Confirmed source display/redistribution rights before public deployment.
- Three sample issuer-linkage mismatches and 19 undocumented-exchange rows need
  independently sourced reconciliation; current records remain unverified.
- Unknown security forms, including GOOG and TSM in the sample, need explicit
  authoritative descriptors before conventional operating-company valuation.
- Verified foreign/ADR share/currency evidence; unsupported IFRS/FX conversions.
- Historical corporate actions/permanent security identifiers absent from text directories.
- Global multi-worker provider rate coordination remains an operator responsibility.
- Safe long-term source archive retention and storage capacity policy.
- Financial coverage beyond the five retained issuers is not established by the
  listing audit; further acquisition needs a separate bounded authorization.
- Market-cap tiers, recent IPO status, permanent IDs and historical lifecycle
  relationships were not independently verified in this bounded acquisition.
- No live AI verification is claimed.

## 25. Actions requiring authorization

The two Nasdaq requests and one SEC reference request were explicitly approved
and completed within their limits; no further request is implied by that approval.
Any fresh financial source audit needs a separately bounded authorization.
Paid/commercial feed access, public display licensing, live OpenAI, commits,
pushes and deployment remain outside this implementation authorization. Secrets,
environments, caches, databases and generated `.phase66.local/` artifacts remain
excluded from Git; only the small audited public fixture is intended for source
control.

## 26. Proposed Phase 6.7 priorities

After source-rights confirmation and separately authorized financial audits: improve
compatible sector inputs, verified ADR/foreign share conversion and sourced REIT
AFFO coverage; strengthen lifecycle identifiers and globally coordinated provider
rate limits; establish measured archive retention and deployment licensing.
These are proposals only. Phase 6.7 is not started.
