# Phase 6.8: real financial data and intrinsic valuation

Report date: **23 October 2026**. Frozen pre-import audit calculation clock:
**2026-10-22T06:51:30Z**. This clock supports reproducible replay; it does not
replace any original source, filing, financial-period or broker observation date.

**23 October 2026 authorized execution update:** migration
`0005_financial_import_batches` and the exact reviewed eight-source import were
committed to the local development database after a verified full backup/restore.
Batch: `sec-f6189f16d8796bf0a99987d22850dfc6207ebff91055bc5d`.
Initial post-import verification stopped at Realty Income (`0000726728`) because
JSONB object-key ordering changed the first two normalization warnings. The
subsequent narrowly authorized correction makes normalization traversal stable;
all eight original snapshot hashes are reproduced exactly, with no persisted
row, version, source or audit changes. **Installed acceptance now passes**:
read-only receipt/provenance verification and the actual installed FastAPI route
returned the historical user-assisted **$53.56** DDM illustration. The import and
migration were not repeated. Section 18 records the correction and final checks.

## 1. Executive summary

**Implemented and offline tested:** transactional SEC import preview/apply,
durable batch provenance, immutable source-cache versions, optional local-only
IBKR research, a quote-independent dated intrinsic workflow and dashboard
presentation. All eleven financial equations and their weights remain intact.

**Functioning installed real-evidence milestone:** the complete previously
acquired MSFT companyfacts source is now verified through the actual installed
FastAPI valuation application. Isolated tests also cover repeated import
idempotency; development verification uses only a read-only receipt replay. Its native
FY2026 declared common dividend of **3.64 USD/share**, with explicit illustrative
scenario assumptions of **3% growth, 10% required return and sustainable payout**,
produces **53.559999999999995 USD/share**, displayed as **$53.56**. This capitalizes
only the modeled dividend stream; it excludes buybacks and payout-policy changes.
It is a historical, user-assumption-driven scenario with no market comparison.
It is not a new current/default valuation or a claim that MSFT is worth that
amount today. The illustrative entries are test-operator assumptions, not the
user's stated investment preferences or measured company facts.

**Applied after explicit authorization on 23 October:** the exact eight-source
application import and additive audit migration. Independent original-row
preservation, exact-count, immutable-snapshot and installed API checks now pass
after the ordering correction recorded above. **Not live verified:** IBKR connectivity,
subscription/API/non-display permissions and optional retention rights. No new
SEC/FMP/Treasury/OpenAI acquisition or broker connection occurred. Application
original financial rows and source caches remain unchanged; approved additions
are installed.

The installed historical user-assisted milestone passes; current publication
and independent multi-model coverage remain blocked.

## 2. Starting Git commit and branch

- Branch: `feature/phase-6-8-financial-data-and-valuation`.
- Starting HEAD: `413a5580ce91577dbce0616fccda5955e9e9804a`.
- Phase 6.7.2 commit `788059b` is present through the existing merge.
- Starting tree/index were clean. No branch switch, merge, rebase, reset,
  staging, commit, push or deployment was performed.

Reviewed predecessor reports:
[6.6](phase66-active-listing-coverage.md),
[6.7](phase67-financial-coverage.md),
[6.7.1](phase671-valuation-coverage-completion.md),
[6.7.2](phase672-real-data-valuation-integration.md).

## 3. Previous Phase 6.7.2 baseline

Read-only PostgreSQL inspection confirmed **14,637 registry issuers, 17,060
instruments/listings, 23,710 listing observations, five financial company owners,
165,486 facts, nine financial snapshots, 14 market snapshots and 64 cache rows**.
The existing PostgreSQL container was stopped; it was restarted in place. No
database/container/volume was recreated or reset.

The original retained 30-security / 330-model-pair sample and the separately
acquired eight-issuer / nine-security / 99-pair sample remain distinct. At the
22 October audit clock the retained 21 October reference proofs are expired;
financial retrieval does not renew them. No default/current-publication increase
is claimed from this phase's historical user-assisted path.

The installed registry specifically retains **19 October** proofs; its legacy
issuer linkage lacks a retrieval timestamp. The 21 October source records used
by the prior isolated replay were not installed. This distinction was verified
directly and is addressed by a separate MSFT-only archived attachment in the
reviewed import, rather than pretending the production registry was refreshed.

Frozen AAPL **214.2302568301956** and MSFT **619.5604742486083** Forward P/E
regressions remain reproducible as dated, single-model policy illustrations.
The new MSFT dividend scenario is a separate model/workflow. It is not a renamed
version of either regression.

## 4. Existing SEC financial evidence

All eight original Phase 6.7 source files and their acquisition manifest were
available: MSFT, NVDA, ORCL, JPM, AMZN, Alphabet, O and PGR. Together they contain
247,920 unique observations and **36,961,056 original bytes**. Their original
retrievals were on 20 October 2026; no file was refetched. The separately acquired
AAPL bundle is also present but is not part of the proposed eight-issuer import.

The [exact import preview](phase68-sec-import-preview.md) lists every original
source SHA-256, CIK, duplicate/new count and proposed write. Full raw files remain
ignored local evidence. Maintained tests include an 11.8 kB public MSFT excerpt
with 12 original SEC observations, dated reference proofs and retained profile
provenance. Mocked/synthetic records remain explicitly labeled test data.

## 5. Import preview and transaction design

`backend/scripts/import_sec_financials.py` has separate **preview** and **apply**
commands. Neither command downloads data or upgrades schema automatically.
Preview uses a read-only consistent snapshot and binds original source bytes,
timestamps, stable issuer ownership, proposed interpretation hashes and full-row
database fingerprints. The current exact digest is:

```text
f6189f16d8796bf0a99987d22850dfc6207ebff91055bc5d6282314b6828ef36
```

On **22 October 2026 at 15:22 UTC**, the preview was rebuilt from all original
files and the current read-only development PostgreSQL snapshot. It matched
the frozen manifest exactly, including all source/interpretation hashes,
archived MSFT attachment, ownership, row counts and database fingerprints.
The technical conflict flag is clear; application authorization is still absent.
Revalidation does not renew the original acquisition or evidence clocks.

Apply requires the intact preview plus exact `APPLY <digest>` confirmation,
after separate user authorization. PostgreSQL serializable isolation and bounded
lock waits protect ownership and write tables. Sources are rechecked inside the
transaction and immediately before their writes; normalized output must match
the preview. Count or preservation mismatches roll back the entire batch.
Repeated application returns the original durable batch without duplicate rows.

One canonical financial owner is selected per stable SEC issuer. GOOG/GOOGL
share Alphabet's consolidated statements without duplicating the owner or
relaxing selected-share compatibility. Ticker reuse never reassigns historical
facts. Same-accession conflicting values block apply; different filing versions
remain original observations under the existing precedence/quarantine policy.
After import, profile visits reuse that issuer owner without changing its
metadata. GOOG quotes remain in GOOG's selected-security cache/API response;
they cannot be persisted as GOOGL market snapshots or create a second owner.

`0005_financial_import_batches` adds only a durable batch audit table. Populated
downgrade refuses to discard its audit history. It was absent at the 22 October
checkpoint and was installed under explicit approval on 23 October. Source-SHA
cache entries are appended, retaining original
retrieval/expiry; older raw and normalized cache rows are left unchanged.
An empty audit table can be downgraded. Once an applied batch exists, downgrade
deliberately refuses to delete its provenance; successful import has no automatic
destructive undo. A separately committed migration remains installed if the
later import rolls back, and PostgreSQL sequence allocations can leave ID gaps
even when every imported row is rolled back. The exact migration SQL and file
SHA-256 are shown in the approval preview.

The preview also binds exactly two already acquired 21 October directory files
for a **MSFT-only historical reference attachment**. The importer reparses their
original bytes, verifies CIK/symbol/venue/common-stock scope, and retains selected
original rows, full-file/row hashes, retrieval clocks and unchanged one-day
expiry. The package is stored only in the new batch's audit metadata under the
exact listing ID. It creates no registry observations or current verification.
The dated workflow can use that reviewed 21 October evidence while publication
continues to show the installed 19 October proof. An ordinary financial-only
import is not misrepresented as sufficient for this installed-data case.

## 6. Import test results

Importer regressions cover exact CIK ownership, Alphabet classes, ticker reuse,
source/preview tampering, missing hashes, same-accession conflicts, restatement
history, full rollback, unauthorized confirmation, changed database baselines,
repeat batches and preservation. Additional tests mutate both source and local
acquisition manifest after inventory to verify the final write-boundary check.

Imported reads cross-bind batch inventory, original source hash and clocks,
snapshot ownership/version and normalization recomputed from the immutable raw
record. A valid older same-issuer snapshot cannot inherit a newer source's
provenance. Native PostgreSQL acceptance tests exercise migration on populated
financial data, transactional rollback, idempotency and audit preservation.

The full-source MSFT disposable import adds **one test owner, 32,671 facts and
one normalized snapshot**. Reapplying its exact batch makes no additional writes.
The normal FastAPI route returns HTTP 200, passes `ValuationResponse`, and
publishes the same supported dividend scenario with zero external HTTP calls.

A second rehearsal copied the installed MSFT rows, including the original
19 October registry proofs, into an in-memory database. The complete source and
reviewed archived attachment added one snapshot and no company/fact rows.
The ordinary API again returned HTTP 200 and **$53.56**, with the 21 October
historical context, unchanged 19 October registry, unavailable market comparison
and current publication blocked. Reapplying remained idempotent. No application
writes or external requests were used for either rehearsal.

## 7. Actual database writes performed

**Application migration/import: committed under explicit user authorization on
23 October 2026. Post-import acceptance passes after the read-only ordering repair.**

The original database was backed up to an access-restricted ignored custom
archive of **35,744,826 bytes**, SHA-256
`b0f33ad2b6eebe8988e1810d93dfb51d957c137c44ae92c187c6f16f891955a3`.
A full restore to `fairworth_phase68_restore_20261023_055228` matched all twelve
original tables, four sequences, schema definitions, owners and grants. The
archive and isolated restore are retained locally. No production database was
accessed. Backup details remain in ignored `.phase68.local/backups/`.

Actual installed counts are **9 companies, 273,055 facts, 17 financial snapshots,
14 market snapshots, 72 cache records and one audit batch**. Revision is
`0005_financial_import_batches`; batch is
`sec-f6189f16d8796bf0a99987d22850dfc6207ebff91055bc5d`.

The concrete application plan adds **four owners, 107,569 facts, eight snapshots,
eight immutable raw-source cache entries and one audit batch**. It updates or
deletes zero existing company/fact/snapshot/cache rows. Three JPM different-filing
review candidates are retained; zero same-accession conflicts are present.
These generic audit flags concern `ffd:NrrtvMaxAggtOfferingPric` in 424B2
offering filings, not confirmed restatements of annual financial statements.
The approval preview lists the three incoming and twelve existing accession/value
records; no unique original-to-replacement pairing or overwrite is implied.
The exact installed counts above match the approved additions.

The 22 October automated acceptance/replay writes occurred only in disposable
SQLite or the guarded PostgreSQL test database. The separately approved
23 October installation is recorded above. The subsequent repair/verification
performed zero development database writes, migrations or import attempts.

## 8. Original financial row preservation

Before/after audits hash every column of application companies, facts, financial
snapshots, market snapshots and cache entries, with deterministic row ordering.
The importer additionally verifies the original row baseline during apply, and
immutable source caches preserve all prior source dates. Saved analysis inputs
and original source observations are never overwritten by a newer quote/filing.

The final read-only audit exactly matched all original counts and full-row
SHA-256 fingerprints: **5 companies, 165,486 facts, 9 financial snapshots,
14 market snapshots and 64 cache records**. The final verification additionally
hashed **all twelve existing application tables** before and after every check;
all row counts and full-row fingerprints matched, including schema version,
117,986 security aliases and four registry refresh records. Registry counts remain
14,637 issuers, 17,060 instruments/listings and 23,710 observations. The application
was still at `0004_financial_issuer_ownership` with the audit table absent during
that pre-import check. After the approved installation, an independent check
matched every original primary key and full-row hash, except the explicitly
authorized Alembic revision-row replacement. Local hashes,
preview manifests, reports and test logs remain in ignored `.phase68.local/`;
credentials and contact details are excluded from maintained artifacts.

Post-repair installed acceptance again checks every original primary key and
full-row hash, including all nine original financial snapshots. All thirteen
installed tables, four sequences and the complete schema remain unchanged
through read-only receipt verification and the actual FastAPI request. The
verified backup archive is unchanged; no reset or restore was performed.

## 9. IBKR API feasibility and licensing

The [official-source feasibility review](phase68-ibkr-feasibility.md) recommends
the separately installed official Python TWS API with an operator-authenticated
TWS or IB Gateway session. Client Portal/Web API was evaluated but is not added.
Fairworth does not request an IBKR password or change broker settings.

API subscription permissions can differ from displayed TWS data, usernames,
exchange feeds and historical services. The current GFIS agreement/API
supplement also imposes non-display/retention/redistribution constraints. Monthly
payment alone establishes none of those rights. Exact applicable personal API,
non-display and optional local-retention permissions must be confirmed before
live evaluation. Public display, external derived-data publication and AI export
remain disabled. Official references and SDK licensing/version tradeoffs are in
the feasibility report; no SDK was installed or bundled here.

## 10. IBKR adapter implementation

The optional provider and small official-SDK callback bridge support exact STK
contract resolution, positive conId, primary venue, trading class, source-backed
currency, bounded quotes and daily TRADES bars. There are no order, position,
account-balance or transfer operations. Unsolicited account/order identifiers are
discarded, SDK callback output is suppressed, and errors use safe fixed messages.

The local CLI requires explicit connection authorization, an actual configured
loopback port and read-only/personal/API permission confirmations. Defaults do
not connect or import the optional SDK. Zero retries, no reconnect, exact session
counters, cancellation and minimum pacing bound every approved operation.

Actual market-data-type callbacks distinguish live, frozen, delayed and delayed
frozen data. Source trade timestamps are never replaced by retrieval time.
Daily bar dates do not become precise UTC trades, and bars do not establish
complete split history. Missing subscription, pacing, ambiguous contract,
currency/venue mismatch, session failure and unsupported semantics fail closed.

IBKR data stays in a separate local process/ignored optional output. It is not a
public FastAPI provider. Recursive guards reject private broker evidence and
derived records at cache/API/AI boundaries, including injected providers and
previously retained nested records. FMP/disabled remain the public provider modes.

## 11. Authorized live IBKR tests

**None. No socket connection or new broker market-data request occurred.**

The [bounded proposal](phase68-ibkr-live-proposal.md) targets MSFT with one exact
contract lookup and one ordinary quote subscription cancelled within twelve
seconds, with zero history requests, retries/reconnects or chargeable regulatory
snapshots. The user confirmed TWS at `127.0.0.1:7496`, Read-Only API and
localhost-only access, and expressly withheld live authorization. These host/port
values were saved locally without changing unrelated environment settings.
The unconnected CLI plan was checked with the exact installed registry IDs.
The optional official SDK is absent; no install/download occurred. Version,
client-ID and applicable API/non-display permissions still need review before a
live approval request. Configuration is not permission to connect.

## 12. FMP Free limitations

All Phase 6.7.2 free-plan guards remain: exact acquisition scope, cached-only
default, shared request budget, retained denials, no hidden profile acquisition,
no automatic paid fallback and no FMP retry. The observed AAPL split HTTP 402
was not probed again. No historical data, quote, profile, directory or Treasury
refresh was requested. The retained AAPL quote's verified unit remains distinct
from its observation freshness, split completeness and public-display rights.

## 13. Intrinsic valuation versus current market comparison

The existing equations already calculate without a quote when their financial
inputs are complete. No price dependency was removed from a formula. New
metadata separates **intrinsic calculation**, **financial observation/forecast
anchor**, **market comparison**, and **current publication**.

An explicit `context: "dated_intrinsic"` request supports a narrowly scoped
domestic-common-share dividend scenario from approved imports and archived
registry/profile evidence, without any provider/cache loader. It requires exact
stable identity, original source hashes/URLs, nonfuture source/filing clocks and
an evidence clock within the original reference interval. The new opt-in path
conservatively rejects the exact expiry boundary; existing current-policy TTL
semantics are unchanged. It never advances proof dates or infers current listing.

Only explicit dividend growth, required return and sustainability assumptions are
accepted. Other financial overrides, models, manual price and discount-rate
bundles are rejected. The original expired/current company proof is preserved in
publication checks. No reviewed currentness allowlist was added; no current or
automatic coverage is granted by the historical scenario.

## 14. Actual valuation model and input provenance

| Item | Source / exact basis |
| --- | --- |
| Security | MSFT, SEC CIK `0000789019`, selected domestic common-stock instrument/listing; stable scope is separate from financial ownership |
| Reported period | FY2026, 1 July 2025–30 June 2026 |
| Dividend baseline | SEC `us-gaap:CommonStockDividendsPerShareDeclared`, **3.64 USD/shares**, exact annual interval/native filing |
| Filing | `0001193125-26-323660`, 10-K filed **29 July 2026** |
| Original acquisition | **20 October 2026 12:01:53.080073 UTC**, 4,881,196 bytes; SHA `f8aae2965b20ad0df44bdf7ccbedf797d275b6b8dc030154a7a311361bb7246f` |
| Share basis | Original per-common-share disclosure, selected common-stock registry and retained SEC adapter profile; no division of total dividends by weighted shares |
| Profile basis | SEC adapter's 15 October single-listed-ticker observation, canonical payload SHA `5b0fdc622233f5dfd2e8480a4a4bd53b5a5a06b17dd94c3551b73c9da11fa0a5`; not proof of absent unlisted classes or current shares |
| Identity evidence cutoff | **21 October 2026 15:05 UTC**, within original listing/linkage proof intervals; this does not refresh today's identity |
| Forecast anchor | Reported annual base **30 June 2026**; first annual scenario **1 July 2026–30 June 2027**, then constant-growth perpetuity |
| Forecast assumptions | Explicit illustrative operator entries: **3% growth**, **10% required return**, sustainable payout confirmed for this scenario only |
| Equation | Existing DDM: next dividend / (required return − growth); no formula change |
| Exact result | **53.559999999999995 USD/common share**, displayed **$53.56** |
| Classification | `user_defined`, `historical_illustration`; no automatic-default count |
| Market comparison | Unavailable: no quote, upside or margin of safety invented |

The reported common dividend is declared, not measured cash paid. Future payment,
sustainable payout and growth are assumptions. This is a retrospective financial
baseline scenario, not a claim that the later-filed information was available
on 30 June. No elapsed-time roll-forward or present-day share/split equivalence is
invented. The model omits buybacks and payout changes and provides no independent
model confirmation. Complete source facts, units, native precision, accessions,
profile limits and assumptions remain in response metadata.

## 15. AAPL/MSFT results

AAPL's original Forward P/E regression remains **214.2302568301956**. MSFT's
original Forward P/E regression remains **619.5604742486083**. Neither is promoted
to current. The new MSFT **$53.56** dividend scenario has different economics and
assumptions and is not compared with an unverified retained market price.

FCFF/FCFE and enterprise methods still require complete cash-flow, enterprise
claims and discount scope. Book models still require economically meaningful
common equity/class basis. Other dividend/REIT/sector gates remain intact.
`REVIEWED_FORECAST_SCOPE_CONCEPTS` and the reviewed financial-currentness registry
remain empty. No fabricated debt, cash, D&A, working capital, financing, shares,
AFFO, target multiple or preferred/NCI zero is admitted.

## 16. Automatic versus user-assisted valuation

Automatic defaults continue to use existing reviewed inputs and policy. The
new dividend source interpretation does not automatically assert sustainability.
The existing source-backed native-period/currency/class checks remain required.

User-assisted dated mode starts with empty explicit forecast controls. An analyst
chooses an original evidence timestamp and inputs the three scenario assumptions.
The server verifies records and rejects missing, contradictory, future or
out-of-scope evidence. Entering a past timestamp does not create proof. Dated
mode also works when ordinary automatic defaults are unavailable, and errors
hide the previous result rather than publishing stale output.

## 17. Frontend improvements

The existing React/JSX design, model/scenario controls and editable assumptions
remain. A compact intrinsic-evidence panel shows the financial date, actual API
calculation timestamp, forecast convention, classification, assumptions,
limitations and exact source records. Values are rounded for display only;
backend validation retains original precision. Scenario metadata stays scoped
to the selected scenario.

The optional dated controls explicitly select the dividend-only workflow and
disable manual comparison price. Imported-evidence details separate original
retrieval from import time and canonical financial owner from selected security.
The intrinsic panel separately displays original financial retrieval, selected
archived identity time, calculation time and explicit first forecast dates.
IBKR is visibly optional and not connected to the public website. No private
broker quote, browser gateway connection or trading control was added. Source
hashes wrap on mobile; no financial equation runs in JavaScript.

## 18. Full automated test results

Final post-repair verification on **23 October 2026** completed with these
results, superseding the 22 October pre-import test run:

| Check | Passed | Failed / errors | Skipped | Result |
| --- | ---: | ---: | ---: | --- |
| Complete backend suite | **2,120** | **0 / 0** | **0** | 316.73 seconds; one existing deprecation warning |
| Native PostgreSQL acceptance tests, included above | **14** | **0 / 0** | **0** | Original four persistence/migration tests, nine JSONB regressions and one read-only enforcement test |
| Frontend unit suite | **95** | **0 / 0** | **0** | 570.9434 ms reported by Node |
| Complete desktop/mobile browser suite | **198** | **0 / 0** | **0** | 99 desktop + 99 mobile; 2.4 minutes; zero retries |
| ESLint | — | **0 errors** | — | Exit 0; no warnings |
| Standalone production build | — | **0 errors** | — | Exit 0; 2,429 modules; 14.73 seconds |
| Python dependency consistency | — | **0 mismatches** | — | `pip check` passed; all 46 lockfile pins match installed versions |
| Frontend dependency consistency | — | **0 mismatches** | — | `npm ls --depth=0` passed; package/lockfile declarations match |

The backend suite includes all new CLI output-protection, canonical-owner,
archived-reference, dividend/API and private IBKR regressions, as well as the
existing model, AI validation, scenario, sensitivity, reverse DCF, source
identity and history checks. The repair adds **38** tests: eleven snapshot
ordering/integrity cases and twenty-seven read-only receipt/legacy-preservation
cases. All eight complete retained source regressions executed. None was skipped
because PostgreSQL or a retained source was absent.

Warnings are retained, not suppressed: the backend reports **one** existing
Starlette/httpx `TestClient` deprecation. The standalone build reports **one**
Vite chunk-size advisory: the main bundle is 521.32 kB (157.56 kB gzip), above
the 500 kB advisory threshold. Browser setup repeats that build advisory and
emits **six** Node `NO_COLOR`/`FORCE_COLOR` environment warnings. Unit and lint
checks report no warnings. Dependency checks required no installs or downloads.

The previous 197-pass/1-failure browser run overlapped a separate build; its
failed landing-page trace recorded HTTP 404 for `/`. The final complete rerun
kept builds and browser execution separate and passed the same mobile search
test and all other cases. No assertion was removed, skipped, retried or relaxed.

No live OpenAI or provider request is allowed by automated tests. Concrete HTTP
transports are blocked; the complete backend runner recorded **zero real HTTP
attempts and zero IBKR socket attempts**, with broker ports explicitly blocked.
IBKR tests use simulated callbacks/transports. Browser financial/AI endpoints
are mocked and the site is served locally. PostgreSQL tests use only the
pre-existing guarded `fairworth_test` database, not the development application
database. No failed check is suppressed. The successful MSFT API replay and
read-only development preservation/preview checks are separate from test counts.
The earlier 22 October installed-row rehearsal returned HTTP 200 and the exact
**53.559999999999995 USD/share** historical user-assisted result, without market
comparison or current publication. All twelve development-table fingerprints
remained unchanged during that pre-import verification.

### 18.1 Warning-order root cause and correction

The first installed acceptance correctly stopped on O: its stored snapshot hash
was `2f3d7f1e330b1a608a9a1b457aed61e33d9819a68e301ffb0217c7f808d39a0c`,
while normalization reconstructed from JSONB produced
`56337ba7a15fc8e17cafdc6b9f283867d330547ca0597292c93d0a070863d641`.
Complete comparison found only the ordering of `normalized_data.warnings`.
Original source bytes, canonical source payload, stored normalized payload and
recorded audit hashes all matched.

`extract_observations` visits taxonomy/concept/unit dictionaries in insertion
order. Normalization emits deduplicated first-seen diagnostics before appending
period diagnostics. PostgreSQL JSONB does not preserve JSON object-member order:
its returned concept order put `ProfitLoss` before `CommercialPaper`, reversing
O's first two diagnostics. The retained source orders the incompatible EUR
commercial-paper warning before the unverified net-income ownership warning.
JSON serialization with `sort_keys=True` canonicalizes dictionaries, but keeps
arrays ordered; JSONB also preserves the stored warning array. Consequently,
reconstructing from the reordered raw-source dictionary changed the strict hash.

Warning order has no financial precedence or severity semantics. Concept
priority remains explicit in `METRIC_DEFINITIONS`; filing dates, amendments,
ambiguity and compatibility rules select evidence independently. Consumers do
not choose financial values from the first warning. Every diagnostic remains
available, with its original field, code and message.

The correction is a stable `(taxonomy, concept, unit)` observation-group sort
inside `normalize_company_facts`. Raw extraction/persistence and every original
concept/unit observation array keep their order. No warning array is sorted,
filtered or excluded from hashing. `content_hash`, normalization version **6**,
financial equations, source facts, immutable snapshots, provenance and audit
records remain unchanged. All eight complete original normalized objects and
approved hashes reproduce exactly from both original files and real PostgreSQL
JSONB round trips, including O's original stored hash. Historical regression
fixtures remain checked; arbitrary mismatching historical hashes are not accepted
or rewritten by a compatibility fallback.

`test_phase68_snapshot_integrity.py` provides two portable synthetic regressions,
one small real-JSONB regression and eight complete retained-source regressions.
The full captures remain ignored optional local acceptance inputs; they were
present and all eight executed here. Checks include exact warning/source-reference
arrays, original-byte and canonical payload hashes, and complete observation
identity multiplicity. No provider download or database import is part of them.

### 18.2 Final installed-database acceptance: PASS

The unchanged installed revision is `0005_financial_import_batches`; the committed
batch is `sec-f6189f16d8796bf0a99987d22850dfc6207ebff91055bc5d`, bound to preview
`f6189f16d8796bf0a99987d22850dfc6207ebff91055bc5d6282314b6828ef36`.

- All eight original SEC source hashes, snapshot self-hashes, reconstructed
  hashes, acquisition/expiry clocks and stable issuer ownership bindings match.
- Exact installed counts: **9 companies, 273,055 facts, 17 financial snapshots,
  14 market snapshots, 72 cache entries and 1 audit batch**. The approved batch
  added 4 companies, 107,569 facts, 8 snapshots, 8 source entries and 1 audit row.
  The repair added, updated and deleted **zero** development database rows.
- Every original primary key and full-row fingerprint remains preserved:
  165,486 original facts, 9 snapshots, 64 caches, 5 companies, 14 market snapshots
  and all registry records. Only the previously authorized Alembic revision-row
  replacement is excepted. The verified backup archive is unchanged.
- All three JPM 424B2 cross-filing candidates coexist with the twelve prior
  observations. No existing observation is overwritten, paired as a definitive
  replacement or promoted to a confirmed annual restatement.
- `verify_applied_preview` verifies the exact committed receipt using PostgreSQL
  **READ ONLY / REPEATABLE READ**, no explicit `LOCK` statements, and no apply call. It checked
  **247,920** incoming observation identities/values and returned the original
  receipt with `already_applied=true`. Actual write-path retry idempotency remains
  covered by isolated tests; a second development import was not executed.
- The new verifier also proves the complete original fact-row baseline before
  preserving **7,707 original fact rows with older normalization labels** across
  MSFT, NVDA, ORCL and JPM.
  These rows intentionally retain earlier labels such as `metric: null`; every
  source field, amount, period and immutable identity matches. Current extraction
  must not rewrite historical interpretations. New facts retain strict label
  checks, and tests reject subsequent legacy-row label, source, retrieval, amount
  or deletion changes. This corrects a false comparison in the new verification
  code; no persisted evidence was repaired or financial validation relaxed.
- Actual `app.main.create_app` lifespan/services, installed development data,
  read-only database connections and ASGI HTTP serialization returned **HTTP 200**
  through `POST /api/stocks/MSFT/valuation/calculate`. Exact result:
  **53.559999999999995 USD/share ($53.56)**, DDM, `user_defined`, `user_assisted`,
  `historical_illustration`, `current_eligible=false`. SEC accession remains
  `0001193125-26-323660`, dividend **3.64 USD/share**, observation/anchor
  **2026-06-30**, explicit 3% growth/10% return/sustainability assumptions and
  evidence context **2026-10-21T15:05:00Z**. Actual calculation time was
  **2026-10-23T06:57:55.249792Z**. Price, upside and margin of safety remain absent.
- All thirteen installed table fingerprints, four sequences and the schema were
  unchanged across receipt/API verification. The SQL guard recorded **293 SELECT
  and 8 SET statements**, zero mutation attempts, zero provider requests and zero
  broker connection attempts. No migration, reset, restore, import, live AI request,
  commit, push, merge or deployment occurred during this repair.

After the complete 2,120-test backend/PostgreSQL run, a separate final read-only
comparison again matched every installed row-count/full-table hash and all four
sequence fingerprints against the captured installed baseline. **All thirteen
development tables and four sequences remained unchanged throughout the final
offline suite.** The maintained-file privacy scan found zero configured private
values or sensitive generated paths across 61 intended paths; the Git index is
empty. Branch and HEAD remain unchanged; all implementation work remains local.

These installed acceptance checks are separate from automated test counts. A
successful historical illustration does not enable automatic/current publication,
independent multi-model corroboration or IBKR connectivity.

## 19. Before/after real coverage measurements and replay

| Measure | Starting application | Before import approval | Verified installed application |
| --- | ---: | ---: | ---: |
| Financial company owners | 5 | 5 | **9** |
| Persisted facts | 165,486 | 165,486 | **273,055** |
| Newly approved Phase 6.8 application imports | 0 | 0 | **1 batch / 8 sources** |
| Newly demonstrated real MSFT user-assisted dividend scenarios | 0 | **1 / 1 selected security** in replay/test DB | **1 / 1** through installed FastAPI |
| New current default publications | 0 | 0 | **0** |
| Independent model corroborations added | 0 | 0 | **0** |
| Live IBKR subscription tests | 0 | 0 | **0** |

The selected MSFT population has one security / eleven candidate model pairs;
one supported historical user-assisted model and zero automatic/current models.
Neither that population nor simulated IBKR data is added to the predecessor's
30/330 or 9/99 denominators or extrapolated to 17,060 listings.

The new replay supports `baseline`, `retained-sec`, `test-import`,
`approved-import`, `mock-ibkr` and `actual-ibkr`. Approved-import mode requires an
existing authorized batch; it cannot execute import. Actual-IBKR mode requires
already authorized local observations and a receipt; it cannot connect. Broker
populations remain private and separate, and their output is restricted to the
ignored local directory. Source, observation, filing, retrieval, evidence and
calculation clocks are explicit in JSON/Markdown.

Run from the repository root:

```powershell
New-Item -ItemType Directory -Force .phase68.local | Out-Null
backend/.venv/Scripts/python.exe backend/scripts/replay_phase68_real_valuation.py --mode baseline --as-of 2026-10-22T06:51:30Z --output .phase68.local/valuation-baseline.json --markdown .phase68.local/valuation-baseline.md
backend/.venv/Scripts/python.exe backend/scripts/replay_phase68_real_valuation.py --mode test-import --as-of 2026-10-22T06:51:30Z --output .phase68.local/valuation-excerpt-test.json --markdown .phase68.local/valuation-excerpt-test.md
```

The second command uses maintained real excerpts and a disposable in-memory
database, not the application database. To replay the full already acquired
MSFT source, append:

```text
--sec-source .phase67.local/approved-sec-MSFT-0000789019.json --sec-manifest .phase67.local/approved-sec-acquisition.json
```

Original raw sources are optional for routine tests and are not committed. Full
local results are in `.phase68.local/valuation-test-import-full-sec.json/.md`;
the actual HTTP response validation stage records status 200, valid response
schema, supported intrinsic output, correct classification and no market claim.

## 20. Remaining blockers

- The installed historical workflow passes acceptance. No further database-write
  approval is needed for this repair. Any future import, migration or write-path
  repetition against development requires separate authorization.
- TWS host/port and read-only settings are configured, but the optional SDK is
  absent. TWS/SDK versions, client-ID isolation and applicable API/non-display/
  retention rights need confirmation before a live connection proposal.
- Current listing/linkage and financial currentness are not refreshed. No new
  currentness policy or contemporary forecast path is claimed.
- Complete splits/history, enterprise claims, cash-flow scopes and independent
  additional model inputs remain unavailable where previously blocked.
- DDM is a conditional payout-stream scenario with low/single-model confidence,
  not a comprehensive current capital-return or enterprise valuation.
- Public broker data/derived publication stays disabled; reference/FMP launch
  licensing remains separately unresolved.

## 21. Next development priorities

1. Retain the repaired JSONB normalization regressions and read-only installed
   acceptance checkpoint. Keep immutable snapshots and source/audit identities
   unchanged; no follow-up database repair is required.
2. Complete the separately bounded IBKR configuration/permission checkpoint,
   then test only explicitly authorized operations. Keep private observations
   out of public/AI/cache exports.
3. Review a complete current financial/forecast contract and any needed fresh
   reference plan separately. Do not renew clocks or bypass denied data.
4. Pursue an independent model only after its economic inputs are complete.

No commit, push, merge, deployment, broker access or new provider acquisition is
authorized by this report. Engineering and the real-evidence test workflow are
implemented and the installed historical user-assisted application passes
acceptance. Current valuation coverage and optional live IBKR access remain
blocked for the reasons above.
