# Phase 6.5 — Market discovery, security identity and bounded analysis

Implementation and verification: 18 October 2026. Branch: `feature/phase-6-5-model-coverage`. Starting implementation commit: `79caf6ba6a10937025da69a215febc96fb4856fe`. No Phase 6.5 commit or push was made.

## 1. Executive summary

Fairworth now has a persistent, indexed security registry, separate issuer/instrument/listing identities, explicit ambiguity handling, paginated search, identity-scoped analysis and AI evidence, coordinated cache refreshes, and independent company coverage stages. Sparse financial evidence produces a usable profile workspace with precise limitations. The eleven valuation equations, original financial observations, Phase 6 source-scope checks, and Phase 5 numerical/category/citation/privacy rules remain intact.

The approved SEC reference snapshot yielded **10,444 usable ticker/exchange records**. It is imported into the local development registry. These are registrant references, not a verified actively listed common-equity universe. The dated real sample resolves **25 securities belonging to 24 issuers**. Five have retained financial evidence. No newly classified security in that reference-only sample establishes default valuation eligibility. This is broader discovery and safer analysis infrastructure, not independently demonstrated universal valuation coverage.

## 2. Baseline and source/provider audit

The [Stage A audit](phase65-coverage-audit.md) was written before implementation. There was no four-company provider allowlist. Existing cached JPM profiles, raw SEC facts, annual periods and a dated quote demonstrated acquisition outside AAPL/MSFT/NVDA/ORCL. The baseline had five cached issuer identities and 64 cache entries, but no persisted full directory, indexed security master, instrument classifications or stable listing identity. Ticker-keyed persistence could overwrite a historical company's CIK; that now fails closed.

After explicit user approval, the bounded reference audit read four official documentation pages, fetched one directory snapshot under 5 MB, and requested 24 submissions metadata records sequentially, with zero retries. All 25 provider requests returned HTTP 200. No companyfacts, full financial histories, FMP API calls, Treasury calls or OpenAI requests were made in this audit. The permanent fixture retains only public identity fields, SIC descriptions, form-type lists, former-name metadata and source hashes. Addresses, phone numbers, contact configuration and full submissions histories are excluded.

[SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) describes submissions metadata separately from entity-wide XBRL facts. A CIK identifies the registrant; it does not identify a quoted share class. Data APIs update as filings are disseminated. The directory's exact publication cadence and active-security completeness were not independently established, so retrieval date is not presented as listing verification.

[SEC developer guidance](https://www.sec.gov/about/developer-resources) requires identified, efficient access and limits aggregate requests to ten per second across machines. Fairworth's existing SEC adapter defaults to a slower per-worker request interval. Multiple workers still require operator-wide rate coordination; the limit is not multiplied by worker count.

[FMP documentation](https://site.financialmodelingprep.com/developer/docs) distinguishes symbol directories, statement availability, active trading, exchange variants and symbol changes. Endpoint existence does not establish account access. The configured account's exact plan was not inferred from the presence of a key. Retained endpoint denials demonstrate actual subscription restrictions; identity-safe fallbacks preserve those restrictions.

[FMP terms](https://site.financialmodelingprep.com/terms-of-service) place restrictions on personal use and displaying or distributing data to other users without the relevant agreement. Public deployment therefore needs an operator-confirmed license. This phase does not claim that the current key authorizes market-wide financial ingestion, redistribution, or every documented endpoint.

## 3. Created and modified files

New runtime files:

- `backend/app/models/security_registry.py`: five registry SQL mappings.
- `backend/alembic/versions/0002_security_registry.py`: additive migration.
- `backend/app/registry/{schemas,repository,service,importers,audit,__init__}.py`: strict imports, indexed discovery, stable identity resolution and offline audit tooling.
- `backend/app/services/security_identity.py`, `coverage_service.py`, `backend/app/schemas/coverage.py`: compatibility/gating and independent coverage contracts.
- `src/lib/securityIdentity.js`, `src/components/dashboard/ProviderCoverage.jsx`: scoped frontend identity checks and coverage presentation.
- `backend/scripts/replay_coverage_sample.py`: network-blocked reproducible public-fixture audit.

New verification files:

- `backend/tests/test_security_registry.py`, `test_security_registry_postgres.py`: registry correctness, migration, persistence, scale and query-plan checks.
- `backend/tests/test_phase65_analysis_identity.py`, `test_phase65_ai_identity.py`, `test_phase65_snapshot_locks.py`: issuer/class isolation, applicability, sparse evidence, mocked research and retention safeguards.
- `backend/tests/test_cache_leases.py`: cross-worker loading, renewal, cancellation, ownership fencing and stale fallback.
- `backend/tests/cache_lease_postgres_helpers.py`: a real PostgreSQL row-lock race between lease renewal and expired-lease cleanup.
- `backend/tests/test_coverage_audit.py`, `coverage_sample_helpers.py`: honest audit denominators and exact retained sample replay.
- `backend/tests/fixtures/registry/sec_reference_sample_2026_10_18.json`: 25 small approved identity excerpts, approximately 52 KB.
- `backend/tests/fixtures/registry/jpm_retained_annual_excerpt.json`: approximately 45 KB of public retained annual SEC observations and exact provenance, normalized with version 4. No fresh financial request.
- `tests/unit/securityCoverage.test.js`, `tests/security-coverage.spec.js`: frontend transport, sparse states, search and desktop/mobile coverage checks.

Modified backend areas: `main.py`, `core/config.py`, `.env.example`, registry model exports, SEC/FMP adapters, financial repository identity guard, company/financial/automatic-input/valuation/cache services, response schemas and stock/financial/valuation/research routes. `valuation/inputs.py` and `eligibility.py` add instrument gates; model equations are unchanged. AI context/evidence/report envelopes gain stable identity; existing validators and prompts remain authoritative.

Modified frontend areas: stock search, API/AI transports, identity/compatibility adapters, provider valuation hook, stock route/workspace, company header, financial statements, research workspace/insights, navigation and scoped CSS. Layout, typography, existing chart calculations and Demo financial formulas remain intact. README and these two Phase 6.5 reports document operation and limits. No dependency or lockfile change was required.

## 4. Database changes and migration

Migration `0002_security_registry` adds `security_issuers`, `security_instruments`, `security_listings`, `security_aliases`, and immutable `security_registry_refreshes`. Existing companies, original financial observations, financial snapshots, quotes and provider caches are not rewritten by this migration.

The reviewed upgrade and approved reference import were applied to the existing development database. Before and after row counts were identical: 5 companies, 165,486 original financial facts, 9 financial snapshots, 14 market snapshots and 64 cache entries. No database reset or volume deletion occurred.

Dedicated PostgreSQL tests independently reject a non-PostgreSQL/non-`*_test` target and refuse a non-empty test database. They verify upgrade, metadata consistency, persisted search, rollback to `0001_financial_data` while preserving a financial snapshot, re-upgrade, and final cleanup of their disposable test tables. Development rollback was not performed. The first PostgreSQL run exposed missing ORM dependency ordering; explicit issuer/instrument relationships fixed parent-before-child insertion.

## 5. Exchange and security types

Registry records retain the source exchange label and optional MIC. The schema accommodates NYSE, NASDAQ, NYSE American and other explicitly sourced venues. No unknown exchange is silently mapped to a verified US listing. The approved sample includes SEC labels `NYSE` and `Nasdaq`; these are source labels, not assertions of current active status.

Types: unknown, common stock, foreign ordinary, ADR, REIT, financial institution, insurance, ETF, closed-end fund, preferred, warrant, right, unit and other. A non-unknown classification requires classification evidence. ETFs, funds, preferreds, warrants, rights, units and other unsupported instruments keep discovery/profile capability while ordinary-stock models remain inapplicable. Unknown types stay unavailable for valuation rather than being treated as common stock.

## 6. Registry source and update strategy

Imports accept an audited local `{records, provenance}` bundle. The SEC parser also accepts an operator-acquired ticker/exchange JSON file. Neither import command downloads data. Reference imports retain source URL, source date, hash, rights/scope statement and original validated records. Import changes are atomic; PostgreSQL advisory locking serializes administrative refreshes. A repeated identical snapshot is idempotent. Failed imports leave the previous version intact. Older observations cannot roll a newer listing backwards. An omitted record does not imply delisting.

From `backend`, after the normal environment setup:

```powershell
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m app.registry.importers path/to/audited-bundle.json
# Alternative: an already acquired SEC reference file and its explicit snapshot date.
.venv/Scripts/python.exe -m app.registry.importers path/to/company_tickers_exchange.json --sec-reference --as-of 2026-10-18
```

`REGISTRY_BOOTSTRAP_ENABLED=false` is the default. Enabling it is an operator decision permitting a bounded cold-start directory acquisition through the existing SEC adapter; it is not a recurring market-wide financial import. `REGISTRY_CACHE_TTL_SECONDS=86400` governs reference cache reuse, not a claim about the source's update schedule. Routine refreshes should be acquired under an approved source/access plan and imported as new dated observations. No scheduler or external search service was added.

## 7. Ticker-to-issuer identity

Issuer UUID and CIK identify the registrant. Instrument UUID distinguishes securities/classes. Listing UUID identifies a symbol/venue/validity interval. Provider symbols and verified aliases remain scoped to that listing. Explicit source instrument keys may connect a verified rename; names alone never merge issuers. Multiple GOOG/GOOGL references share the verified CIK but retain different instrument/listing IDs.

Dot/hyphen aliases require explicit records in the new registry. `BRK-B` is present in the audited SEC snapshot. That alone does not verify `BRK.B` as a provider-specific alias; an operator can import a separately evidenced alias. The legacy transport spelling remains compatible for old unscoped contracts. Scoped provider requests use the exact selected symbol or its explicit provider alias.

Company aliases in `aliases` support discovery only. Explicit `symbol_aliases` are separately validated and may establish a noncanonical security symbol. A company name cannot authorize a provider symbol or an AI financial identity. Both `instrument_id` and `listing_id` can be selected in route queries; joint selection resolves separate venues/listing intervals of one instrument. Instrument-only clients remain compatible when the instrument has a unique matching listing. Reuse across different instruments of the same issuer also requires a verified history interval; a matching CIK does not make their prices interchangeable.

Resolved identity and search results preserve registry source date, actual retrieval time, version, status and warnings. Freshness is assessed from the original source observation date. Reimporting an old reference today does not make its listing observation current. This reports staleness without inventing a delisting or changing the recorded classification.

Ambiguous names/tickers return candidates. Ticker reuse does not replace an old CIK, and market history is rejected or bounded to a verified listing interval. The older financial tables still have a unique ticker constraint: a newly reused symbol can be discovered/profiled, but persistence of a second issuer's statements deliberately stops with `incompatible_financial_identity`. Supporting both issuers in that older schema requires a separately reviewed migration; old facts are never reassigned.

## 8. Search and measured performance

Search is case-insensitive by exact ticker, verified alias, prefix and company-name tokens. Ranking favors exact symbols, explicit aliases and prefixes; active/source statuses affect ordering. Candidate queries use indexed prefix lookups and token intersections. Only a bounded page is returned. The API defaults to 10 results, caps a page at 50, and supports offsets up to 100,000. Autocomplete is debounced 250 ms, cancels stale requests and displays at most a page of results. It never transfers the whole registry on each keystroke.

Recorded local PostgreSQL benchmark, 10,000 **synthetic** records:

| Operation | Observed time |
| --- | ---: |
| Atomic initial import | 8.26 s |
| Exact ticker search | 13.7 ms |
| Name-token search | 19.2 ms |
| Prefix search | 23.7 ms |
| Offset page | 23.6 ms |
| 24 concurrent bounded searches, total | 125.6 ms |

PostgreSQL `EXPLAIN` verified `ix_registry_ticker_prefix` and `ix_registry_alias_prefix`. After removing accidental loading of whole historical refresh JSON per result, lookup cost remained bounded to requested matches.

The actual 10,444-reference development import took 8.18 s. Local exact/name/prefix/page queries measured 17.6/8.3/31.8/33.7 ms respectively. These are small local measurements with specific caches/hardware, not latency percentiles, production capacity or a throughput SLA.

## 9. Provider entitlement limits

Existing adapters retain distinct safe errors for 401/403 access denial, 402 subscription restriction, 404 absence, 429 throttling, timeouts and transient server failure. Restrictions remain symbol/endpoint-scoped. No alternate endpoint bypass, credential disclosure, inferred field replacement or financial bulk download was introduced.

Retained AAPL/MSFT/NVDA/ORCL evidence includes restricted optional FMP statements; ORCL also lacks a usable permitted comparison quote in its fixture. Existing original source data is preserved. Newly requested FMP access, active-security feeds, redistribution licenses and account-plan confirmation need the operator's authorization/documentation.

## 10. On-demand ingestion and caching

The workflow resolves identity, checks persistent caches, obtains permitted sources only when needed, normalizes observations, evaluates source/period/scope, derives defensible assumptions, and runs existing Python eligibility/calculation. Registry imports do not fetch financial statements.

Scoped keys include stable issuer/instrument/listing IDs, CIK, symbol/venue, provider aliases, classification/listing metadata and historical validity. Source-specific keys retain provider and normalization/evidence versions and relevant observation/retrieval dates. SEC raw facts remain issuer-CIK scoped because they are entity-wide. Old ticker-only quote/profile caches are not silently reused for newly scoped securities. Automatic-input and transient valuation caches use the same scope.

Database-backed, expiring owner leases coalesce independent workers. The owner renews its lease during loading; publication checks the owner under a short transaction. A lost owner cannot replace another worker's snapshot. No connection/transaction spans provider awaits. Provider failure preserves original data and retrieval age. Wait time is bounded; a waiter receives explicit stale fallback or a retryable busy error. Nested different-key loads are supported. Local keyed locks are reference-counted and released after the last waiter, including cancellation/failure. Transient valuation snapshots are capped at 100; FMP profile and denial maps are capped at 1,000 each. Expired coordination rows are reclaimed in bounded batches without deleting provider caches.

Two independent workers produced one loader invocation in the PostgreSQL test. Cold single-company provider latency remains dominated by authorized SEC/FMP/Treasury response time and existing timeout/retry budgets. No fresh financial-ingestion or production dashboard latency benchmark was authorized. Synthetic singleflight/dashboard tests verify behavior, not live provider performance.

## 11. Valuation eligibility and sector safeguards

Eligibility policy is versioned `instrument-eligibility-1`; financial formula engine version remains `1.1.0`. No model equation or valuation input was changed. Instrument/identity gates cannot be overridden by assumptions-editor flags. New registry instruments require verified identity, active listing and compatible class/share basis.

Banks/financial businesses and insurance retain financial-sector enterprise-framework exclusions. REITs do not become ordinary GAAP earnings-multiple businesses through an editor toggle; missing sourced AFFO remains missing. Existing safeguards still cover negative/unstable earnings, cyclicality, dilution, debt completeness, noncontrolling equity, currency, periods, forecasts, DCF bridges and model independence. Synthetic tests exercise these paths without labeling invented values as real-company financial coverage.

Foreign/ADR analysis requires compatible source accounting and currency, explicit share basis and a sourced ADR ratio. This engine does not implement non-unit ADR per-security conversion or FX translation. Such cases remain unavailable. IFRS-only raw evidence is retained, but the USD/US-GAAP mapper produces empty compatible statements with an explicit unsupported-accounting warning; it never asserts USD or zero financials.

## 12–16. Real sample, new discovery and unavailable analyses

The permanent reference sample is dated **18 October 2026**. The offline replay uses the exact captured SEC identities plus retained financial excerpts. It makes no current financial-availability claim for unfetched companies. Its denominator is 25 securities / 24 issuers, independent of the 10,444-record directory denominator. Industry is SEC SIC text where present; no market-cap classification is inferred.

Every row below resolves its exact SEC reference and remains **unclassified/reference-only**, with active-listing status unverified. Consequently every new scoped row has **zero contributing valuation models**. `Missing` means absent from this audited evidence bundle, not proof that the company has no public statements. `AI facts` means registered structured facts exist; no new AI report was generated.

| Symbol | CIK | Source exchange | Retained statements | Default valuation stage | AI facts |
| --- | --- | --- | --- | --- | --- |
| AAPL | 0000320193 | Nasdaq | Available | Missing class/listing proof | Yes |
| MSFT | 0000789019 | Nasdaq | Available | Missing class/listing proof | Yes |
| NVDA | 0001045810 | Nasdaq | Available | Missing class/listing proof | Yes |
| ORCL | 0001341439 | NYSE | Available | Missing class/listing proof; optional quote restricted | Yes |
| AMZN | 0001018724 | Nasdaq | Missing | Missing evidence | No |
| GOOG | 0001652044 | Nasdaq | Missing | Missing evidence | No |
| GOOGL | 0001652044 | Nasdaq | Missing | Missing evidence | No |
| META | 0001326801 | Nasdaq | Missing | Missing evidence | No |
| TSLA | 0001318605 | Nasdaq | Missing | Missing evidence | No |
| AMD | 0000002488 | Nasdaq | Missing | Missing evidence | No |
| PLTR | 0001321655 | Nasdaq | Missing | Missing evidence | No |
| SOFI | 0001818874 | Nasdaq | Missing | Missing evidence | No |
| JPM | 0000019617 | NYSE | FY2025 retained | Missing class/listing/forecast proof | Yes |
| BAC | 0000070858 | NYSE | Missing | Missing evidence | No |
| KO | 0000021344 | NYSE | Missing | Missing evidence | No |
| WMT | 0000104169 | Nasdaq | Missing | Missing evidence | No |
| BRK-B | 0001067983 | NYSE | Missing | Missing class/share basis | No |
| TSM | 0001046179 | NYSE | Missing | Missing currency/depositary/class evidence | No |
| BABA | 0001577552 | NYSE | Missing | Missing currency/depositary/class evidence | No |
| NVO | 0000353278 | NYSE | Missing | Missing currency/depositary/class evidence | No |
| O | 0000726728 | NYSE | Missing | Missing sourced REIT/class evidence | No |
| PGR | 0000080661 | NYSE | Missing | Missing sourced insurance/class evidence | No |
| CMT | 0001026655 | NYSE | Missing | Missing evidence | No |
| CRWV | 0001769628 | Nasdaq | Missing | Missing evidence | No |
| SPY | 0000884394 | NYSE | Missing | Ordinary-stock applicability not established | No |

The following companion matrix makes profile availability, counts and quality explicit for every sampled row. All 25 reference resolutions are available; eligible models are empty and contributing counts are zero. `Limited` and `Unavailable` below are the engine's data-quality labels; valuation confidence is unavailable for every row because no model contributes. `U` means unverified instrument/listing evidence; `S` means statements absent from this audited bundle; `F` means explicitly stale retained financial sources; `P` means only an identity reference is available for the profile. Complete field/model reasons remain in the reproducible JSON and Markdown exports. A restriction not reported here is not evidence of account-wide entitlement.

| Symbol | Profile | Statements | Contributing models | Data quality | Reported provider restriction | Primary blockers |
| --- | --- | --- | ---: | --- | --- | --- |
| AAPL | Available | Available | 0 | Limited | None in sampled response | U, F |
| MSFT | Available | Available | 0 | Limited | None in sampled response | U, F |
| NVDA | Available | Available | 0 | Limited | None in sampled response | U, F |
| ORCL | Available | Available | 0 | Limited | Optional FMP market access | U, F |
| AMZN | Available | Missing | 0 | Unavailable | None in sampled response | U, S |
| GOOG | Available | Missing | 0 | Unavailable | None in sampled response | U, S |
| GOOGL | Available | Missing | 0 | Unavailable | None in sampled response | U, S |
| META | Available | Missing | 0 | Unavailable | None in sampled response | U, S |
| TSLA | Available | Missing | 0 | Unavailable | None in sampled response | U, S |
| AMD | Available | Missing | 0 | Unavailable | None in sampled response | U, S |
| PLTR | Available | Missing | 0 | Unavailable | None in sampled response | U, S |
| SOFI | Available | Missing | 0 | Unavailable | None in sampled response | U, S |
| JPM | Identity only | FY2025 retained | 0 | Limited | None in sampled response | U, F, P |
| BAC | Available | Missing | 0 | Unavailable | None in sampled response | U, S |
| KO | Available | Missing | 0 | Unavailable | None in sampled response | U, S |
| WMT | Available | Missing | 0 | Unavailable | None in sampled response | U, S |
| BRK-B | Available | Missing | 0 | Unavailable | None in sampled response | U, S |
| TSM | Available | Missing | 0 | Unavailable | None in sampled response | U, S |
| BABA | Available | Missing | 0 | Unavailable | None in sampled response | U, S |
| NVO | Available | Missing | 0 | Unavailable | None in sampled response | U, S |
| O | Available | Missing | 0 | Unavailable | None in sampled response | U, S |
| PGR | Available | Missing | 0 | Unavailable | None in sampled response | U, S |
| CMT | Available | Missing | 0 | Unavailable | None in sampled response | U, S |
| CRWV | Available | Missing | 0 | Unavailable | None in sampled response | U, S |
| SPY | Identity only | Missing | 0 | Unavailable | None in sampled response | U, S, P |

Provider source failures remain independent: a quote 402/403 does not turn SEC statement absence into a subscription failure. Raw scoped SEC facts and submissions must identify the exact requested CIK before they can be accepted; unknown identity is not filled in from the request. A lease renewal/cleanup race is covered with real PostgreSQL row locks; cleanup rechecks expiry after waiting and preserves renewed leases.

This is reference discovery beyond the original four; it is not 25 verified current common stocks. O and PGR supply real SIC-sector samples. CMT and CRWV are audited identity candidates for small/recent issuer expansion; this bounded source set does not independently verify current market capitalization or initial-listing date. Former-name records are retained, but no new historical ticker relationship or delisting was invented. ETF/renamed/delisted/security-class behavior is additionally verified with explicitly synthetic records. Full real classification of these categories remains pending a permitted listing/instrument source.

Sample stage counts from the offline replay: symbol reference resolution 25/25; classification proof 0/25; SIC/profile enrichment 23/25; retained annual statements and normalized financial evidence 5/25; current-source freshness established 0/25; eligible new scoped default valuation 0/25; structured AI financial evidence 5/25; newly generated AI reports 0/25. Registry-only identity profiles remain useful even where richer profile fields are missing. Aggregate audit output groups exact statuses by issuer, exchange, SIC text and instrument type and rejects duplicate securities or mixed real/mocked denominators.

The separate four-company **legacy dated regression** remains unchanged: AAPL `214.2302568301956`, MSFT `619.5604742486083` (single contributing Forward P/E model, policy estimate, low quality); NVDA and ORCL unavailable. Those values use their retained compatible fixtures, not the new unclassified registry records. They must not be advertised as estimates validated for today's listing/security context.

Reproduce the saved public-fixture audit from the repository root, after installing backend test dependencies:

```powershell
New-Item -ItemType Directory .phase65.local -Force
backend/.venv/Scripts/python.exe backend/scripts/replay_coverage_sample.py --responses .phase65.local/coverage-responses.json --output .phase65.local/coverage-audit.json
# Summarize those exact saved responses independently, from backend:
.venv/Scripts/python.exe -m app.registry.audit ../.phase65.local/coverage-responses.json --output ../.phase65.local/coverage-summary.json
.venv/Scripts/python.exe -m app.registry.audit ../.phase65.local/coverage-responses.json --format markdown --output ../.phase65.local/coverage-matrix.md
```

Create the ignored output directory first if absent. The replay uses a new in-memory SQLite database and blocks real HTTP transports. The audit CLI itself reads local files only. Neither tool reads API credentials or contacts providers.

## 17. Frontend behavior

Search results show exchange, instrument type and class; duplicate exact company names require selection. The selected `instrument_id` stays in the route query and every company/financial/valuation/research request. Stale responses and cross-security evidence are rejected. A new selected instrument creates fresh workspace state. Demo symbol validation and formulas remain compatible.

Selection also carries `listing_id`; search keeps separate rows for different listings of the same instrument. Ambiguity choices disclose exchange, class, CIK, lifecycle and listing identity. Workspace state resets between listings. Keyboard users can Tab through result pagination; focus leaving search closes results. Coverage 503/429 responses produce an explicit diagnostics-unavailable notice, while an older server's optional 404 remains compatible.

Annual, quarterly and optional endpoint failures remain independent. Valid quarterly data is retained when annual data is missing. Profile-only, missing-CIK, unsupported-instrument and provider-restricted workspaces display available identity/profile facts and the exact missing-data reason. No empty financial field becomes zero. Coverage shows eight scan-friendly stages with expandable complete diagnostics and source identities. Existing assumptions, scenarios, comparison chart, source inspection and AI presentation remain available where evidence permits them. Desktop/mobile tests preserve layout and overflow behavior.

## 18. AI Research compatibility

Evidence adapter `financial-evidence-3` adds public stable identities to scoped records and snapshot hashes. Company, financial, valuation, source-record and selected-instrument IDs must agree. Report caches and session-bound evidence capabilities distinguish instruments/classes; missing/wrong instrument scope cannot retrieve a scoped citation. A profile-only context contains explicit unavailable values, not invented financials.

The current prompt remains `fairworth-research-9`. Typed scalar/date/model references, dynamic binding catalogs, exact numerical assertions, categories/uncertainties, source classifications, citations, privacy redaction and rendering validators are unchanged. The exact successful v8 MSFT fixture remains immutable and passes backend/frontend/browser replay. No paid or unpaid OpenAI requests occurred during this phase.

## 19. Verification results

The final complete offline backend run passed **1,461 tests**, including both guarded PostgreSQL modules, with zero real HTTP attempts. This includes the actual row-lock renewal/cleanup race, joint listing selection, company/symbol alias separation, source-specific availability, mandatory scoped raw CIK validation, registry source freshness, audit matrix output, and the existing independent AI validators. Focused checks during development are included in that final full-suite count rather than added to it.

Frontend **70 unit tests**, **144 browser tests** (72 desktop + 72 mobile), ESLint and production build passed after the follow-up review. Browser scenarios include 24 Phase 6.5 coverage cases and the retained v8 response on both viewports. `pip check` and `npm ls --depth=0` passed; dependencies/lockfiles are unchanged. The audited 25-security replay and production-wired read-only search check also passed, with outbound HTTP blocked.

Backend verification includes API backward compatibility, all eleven equations, four-company retained defaults, strict AI fixtures, every unsupported instrument/model combination, bank/insurance/REIT gates, IFRS-only data, missing CIK/statements, ADR ratio/currency mismatches, ambiguous names, changed/reused symbols, source mismatches, staleness, concurrent requests, bounded caches and sampled audit denominators. Concrete HTTP transports are blocked throughout the offline suite; mocked/ASGI transports remain usable. No external HTTP attempt was observed.

The existing FastAPI test client emits a Starlette deprecation warning about its HTTP test transport. It does not affect passing assertions and no dependency migration is bundled into this phase. Local Chromium mobile emulation does not establish Safari/physical-device behavior.

The implementation originally covered 71 modified/new files. On the follow-up request those 71 files were already staged outside this turn. That index was preserved; review fixes and the new PostgreSQL race helper remain unstaged for review. `.env`, local audit/provider data and generated reports remain ignored. No configured secret or sensitive/generated path belongs in the implementation diff. `git diff --check` passed. The branch and parent commit remain as recorded above; nothing has been committed or pushed.

## 20. Performance and scaling constraints

Registry-scale search, pagination, resolution, actual PostgreSQL index plans, concurrent queries, cache lookup/singleflight and sparse dashboard behavior are exercised offline. Cold financial ingestion is intentionally on demand; provider plan limits, shared SEC fair-access limits, database I/O, normalization CPU, upstream freshness and historical-data quality remain the bottlenecks. Ten thousand synthetic identities test architecture and index use, not ten thousand real financial analyses.

Transient in-process results and provider metadata are bounded, but retained source snapshots grow with actual analyzed issuers and refresh history. An operator retention/storage policy is still needed. Search uses SQL prefix/token lookup rather than fuzzy/trigram infrastructure; very broad offset searches and full registry imports are administrative/local operations, not a production-scale SLA. Distributed cache coordination is tested on PostgreSQL; global multi-worker provider request-rate coordination is still an operator responsibility.

## 21. Remaining limitations

- Reference discovery is broad; active listing, instrument classification, provider entitlement, compatible statements and valuation eligibility remain independent.
- The bounded sample verifies issuer metadata, not full current financial coverage, market-cap tiers, all real security classes, IPO dates or delistings.
- Unit ADR/compatible USD-US-GAAP evidence can be evaluated only after explicit verification. Non-unit ADR conversion, IFRS mapping, FX translation and new sector valuation formulas are not implemented.
- Unknown classifications/listing statuses block new scoped valuations; this intentional safeguard also applies to original-example symbols imported from reference-only sources.
- Reused-ticker financial persistence fails closed until the older unique-ticker financial schema is separately migrated.
- No new live AI response, FMP entitlement request, or cold external financial-ingestion benchmark was performed. Retained source dates remain dated, including quotes and financials.
- The public reference source does not prove whole-market completeness or grant FMP display rights. Universal support is not claimed.

## 22. Actions requiring further authorization

Further external acquisition needs a concrete bounded approval: a permitted active-listing/instrument/class source, ADR ratio/currency/share-basis evidence, provider account-plan verification, or a limited multi-sector financial sample. FMP data display/redistribution requires appropriate license confirmation. Any live OpenAI verification needs separate evidence-export and request approval. No such additional request, commit, push, database reset or later phase has been performed automatically.

Local `.env`, `.phase5.local/`, `.phase6.local/`, `.phase65.local/`, downloaded reference/cache data, databases, credentials, virtual environments, node dependencies, reports and screenshots remain ignored. Only small curated public fixtures and source/test/documentation files belong in a future reviewed commit.
