# Phase 6.7.2: free-tier market data and valuation integration

Audit date: **21 October 2026**. Before clock: **09:34:04 UTC**. After clock:
**15:04:55 UTC**. These are frozen calculation clocks, not refreshed financial
observation dates. All counts below refer to the stated local sample.

## 1. Executive summary

Engineering improvements are implemented and verified: explicit FMP acquisition
scope, retained entitlement denials, a shared request budget, source-backed quote
currency, clearer dashboard states, a read-only financial import audit and an
HTTP-blocked end-to-end replay. Existing financial equations, weights and AI
evidence validation remain unchanged.

**The current-valuation objective remains blocked.** The approved AAPL audit
established one fresh, currency-compatible quote. Split access returned HTTP 402;
historical-price acquisition stopped without a fallback. Current forecast-period
proof and financial currentness also remain unverified. No new current default
valuation or independent second model became eligible. A successful quote is
not a successful valuation.

The original dated AAPL Forward P/E **214.2302568301956** and MSFT Forward P/E
**619.5604742486083** remain reproducible. Applying the new AAPL evidence in an
isolated replay makes its updated calculation unavailable; it does not overwrite
that original historical result. No application financial data or caches were
imported, and no live OpenAI request was made.

## 2. Git branch and starting commit

- Branch: `feature/phase-6-7-2-real-valuation-integration`.
- Starting commit: `e0164ac3179955a2f6310da03444468331b79e13`.
- Phase 6.7.1 dependency: `b5b9134`, included in the starting history.
- Starting working tree: clean. No branch switch, merge, reset, staging, commit,
  push or deployment was performed for this implementation.

The preceding reports are [Phase 6.6](phase66-active-listing-coverage.md),
[Phase 6.7](phase67-financial-coverage.md) and
[Phase 6.7.1](phase671-valuation-coverage-completion.md). Original reports retain
their own dated conclusions; the comparisons here use the explicit clocks above.

## 3. Phase 6.7.1 baseline

The existing registry contains **14,637 issuers, 17,060 instruments/listings and
23,710 immutable listing observations**. The development application contains
five companies, 165,486 facts, nine financial snapshots, 14 market snapshots and
64 cache entries. Full-column hashes and row counts of those application tables
matched before and after this phase; registry counts also remained unchanged.

The retained sample has **30 securities / 330 security-model pairs**, five
financially populated securities, two historical single-model Forward P/E
illustrations, zero current valuations and zero independent multi-model
corroborations. The separately acquired Phase 6.7 sample has **eight reporting
issuers / nine securities / 99 pairs**, with GOOG and GOOGL evaluated separately;
it has zero historical default outputs and zero current valuations. These are
different populations and must not be added together or extrapolated to all
registered securities.

Normalization version 6, debt conflict quarantine, operating/financing scope,
cash restrictions, independent listing/issuer expiry and evidence-dependence
disclosures remain in force.

## 4. FMP free-plan restrictions

The [Basic pricing documentation](https://site.financialmodelingprep.com/developer/docs/pricing)
describes a free plan with 250 calls/day and 500 MB trailing-30-day bandwidth,
with endpoint/symbol restrictions. Documentation is not account entitlement.
Remaining account allowance and use by other clients are unknown. The local
guard is deliberately more conservative and is not an account-wide usage meter.

No upgrade, new account, paid statement fallback, credential rotation, scraping
or automatic retry is implemented. A key alone authorizes no endpoint. HTTP
401/403 and 402 are retained separately from temporary/rate-limit failures.

The [terms](https://site.financialmodelingprep.com/terms-of-service) and pricing
page distinguish personal evaluation from third-party/public display. The
operator explicitly confirmed permission for this private local evaluation and
retention. **Public display/redistribution rights remain unresolved**; no launch
or redistribution permission is inferred from that confirmation.

## 5. Provider capability and licensing matrix

All access observations below are dated, exact-scope evidence. A documented
endpoint that was not called remains untested for this account.

| Provider / source | Available fields and identity | Authentication / actual access | Limits, retention and production suitability |
| --- | --- | --- | --- |
| SEC companyfacts | Entity-wide standard-taxonomy facts, units, periods, accession and filing dates; CIK, not class-specific market identity | No API key; identifying User-Agent; eight retained Phase 6.7 successes and one new AAPL success | [SEC API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), [fair access](https://www.sec.gov/about/developer-resources); documented ceiling 10 requests/sec, audit used at least 1 sec spacing. Public source provenance retained. No price, quote currency or split completeness guarantee; scope review required before production valuation. |
| SEC submissions / annual document | Filing calendar, report date, accession, primary document and original disclosures | No key; identifying User-Agent; new AAPL submissions and selected annual document succeeded | Same SEC fair-access policy. No older submission pages or extra documents fetched. Filing publication/observation clocks remain distinct from retrieval. No market-price feed. |
| Nasdaq Trader listing directories | Dated security name, symbol, listing venue and security flags | Existing public directory imports; prior approved 21 October snapshot, no new Phase 6.7.2 request | One-day independent listing proof. Source URL/hash and original directory clock retained. [Field definitions](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs) do not establish quote currency or class share counts. Public display/redistribution licensing remains a deployment review item; no inferred permission from anonymous access. |
| SEC issuer-symbol directory | CIK/symbol/venue linkage | Prior approved 21 October snapshot; no new request | Independently expires after one day. Reference linkage only; not price, currency, corporate-action or financial-currentness proof. No omissions treated as delisting. |
| FMP profile | Symbol, CIK, exchange and explicit currency, where returned | Existing key; AAPL HTTP 200 on 21 October | Dated exact-security metadata only. A profile's price is not a quote observation. Local retention confirmed; public display unresolved. Free-plan/account limits above. |
| FMP quote | Original finite price and source timestamp; currency only if explicit or separately verified | Existing key; AAPL HTTP 200 on 21 October; older MSFT/NVDA/AMZN successes are historical access observations | Preserve observation/retrieval times separately. AAPL response omitted currency. No inferred USD, entitlement for another symbol, or public display right. |
| FMP splits | Dated split numerator/denominator, if allowed and complete for the required interval | AAPL HTTP 402 on 21 October | Requires paid subscription in the observed scope; no retry or substitute symbol. Empty/limit-sized responses cannot establish complete history. |
| FMP historical EOD | Dated closes and documented split-adjustment basis, if returned; source currency still required | Not called: skipped after split denial | Historical currency cannot be copied from today's profile. Access, account limits and display rights unresolved. No synthetic prices substitute for missing history. |
| FMP dividends / float / statements | Potential dividends, dated share counts or supplemental statement rows | No new call; not established by the quote/profile successes | No automatic paid statement fallback. Exact units, period, class and entitlement review required. No current share basis or dividend sustainability inferred from endpoint names. |
| US Treasury integrated provider | Dated official yield curve / risk-free observation | Existing implementation and retained evidence; no new call | Official public-source attribution and date retained. A risk-free yield is not WACC, cost of equity or an equity-risk premium. No discount-rate completeness inferred. |
| Other market providers | No new source selected | No new account, request or approved entitlement | Terms, attribution, caching, timestamp/currency, corporate-action scope and actual permission would need a separate review. No undocumented scraping fallback. |

Endpoint documentation: [profile](https://site.financialmodelingprep.com/developer/docs/stable/profile-symbol),
[quote](https://site.financialmodelingprep.com/developer/docs/stable/quote),
[splits](https://site.financialmodelingprep.com/developer/docs/stable/splits-company),
[historical EOD](https://site.financialmodelingprep.com/developer/docs/stable/historical-price-eod-full).
No undocumented account-specific attribution, caching permission or commercial
license is asserted. Source labels/URLs accompany displayed evidence, while
unresolved rights remain explicit.

## 6. Minimal AAPL/MSFT evidence requirements

| Required path | AAPL | MSFT |
| --- | --- | --- |
| Exact identity | CIK `0000320193`, selected common-stock instrument and Nasdaq listing; 21 October listing and issuer proof | CIK `0000789019`, separate common-stock instrument/listing; same dated independent reference checks |
| Financial observation | New FY 2025 annual ending 27 September 2025; latest annual filed 31 October 2025; submissions also disclose quarter ending 27 June 2026, filed 31 July 2026 | Retained FY 2026 annual ending 30 June 2026, filed 29 July 2026; retained replay source and current-cache evidence remain separate |
| Price / unit | New observed quote plus exact-listing USD profile proof established | Earlier quote lacks reviewed currency metadata in this bundle; no MSFT refresh authorized |
| Shares / splits | Annual diluted EPS and diluted weighted-average shares are source-backed; current split completeness denied, not inferred | Historical EPS/share basis supports only the retained illustration; current split/class and quote compatibility still need proof |
| Target multiple | A new current filing-aligned split-compatible history was not acquired | Existing dated policy multiple remains historical; no new complete current path |
| Forecast horizon | One-year annual-based default does not establish an explicit current forecast start/end or next-12-month horizon | Financial currentness, assumptions and effective horizon require their own review |
| Additional family | Common-equity/book, sustained per-share dividends, complete enterprise claims or operating/financing forecast scope still missing | Independent common-equity/enterprise/cash-flow/discount evidence still incomplete |

Forward P/E was the minimum candidate because historical earnings and a policy
path already existed. The bounded proposal sought only the missing AAPL market,
split/history and calendar evidence. No broader market-wide history was needed
or acquired. This evidence did not complete the path.

## 7. Provider integration architecture

`market_access.py` wraps actual FMP service loaders **inside** existing cache
loaders. Valid caches require no reservation; denied refreshes preserve dated
stale evidence under existing policy. Quote/history/dividend calls no longer
silently acquire a profile. Profile currency may augment a quote only from an
already retained, compatible original source record.

Default configuration in `backend/.env.example` is cached-only:

```dotenv
FMP_AUTHORIZED_ENDPOINTS={}
FMP_ACCESS_REVIEW_ID=initial
FMP_DAILY_REQUEST_BUDGET=50
FMP_MINIMUM_REQUEST_INTERVAL_SECONDS=1
```

An operator may configure at most 20 exact symbols with explicit supported
endpoints after permission/entitlement review; wildcard scope and automatic paid
statement fallback are rejected. This phase did not change the real `.env`.
FMP's adapter uses zero retries independently of the SEC retry setting.

Capability responses distinguish observed access, explicit denial, untested,
paid subscription, temporary outage, rate limiting and unsupported source fields.
Acquisition permission and unresolved display rights are separate fields.
Successful responses are dated access evidence, not a permanent entitlement.

HTTP 401/403/402 denials persist in the existing cache table under exact stable
issuer/instrument/listing/CIK/symbol/endpoint and review scope. Refreshed listing
proof does not bypass a retained denial. Re-enabling requires an explicit access
review; automatic expiry does not cause a new probe. A denial is checked again
after queued dispatch waits. No SQL transaction is held during network I/O.

A shared atomic lease reserves at most the configured rolling-24-hour budget
(default 50, maximum 250), with at least one second between scheduled starts.
Failed/cancelled reservations remain consumed. Account-wide remaining calls and
monthly bandwidth are unknown; the documented 500 MB allowance is disclosed,
not represented as a locally verified account meter. No recurring ingestion or
provider-discovery task is enabled. No new database table/migration is needed.

## 8. Quote currency verification

`currency.py` accepts finite source values and dated, hashed original quote or
profile currency fields only for the exact selected identity. It verifies source
type/URL, provider, symbol, available CIK/venue and stable registry scope. Metadata
has an explicit one-day age bound and cannot be a later-date re-denomination of
an older quote. Conflicting original units fail closed. Company reporting
currency is compared separately and never supplies a missing trading unit.

The newly acquired AAPL quote had original price **343.695**, observed
**2026-10-21 15:02:52 UTC**, retrieved **15:02:54.123475 UTC**, and no raw currency.
The preceding AAPL profile supplied explicit **USD**, CIK and Nasdaq metadata.
Its original record hash, retrieval clock and exact identity support a verified
USD resolution at the audit clock. The profile's own price is not used as a
replacement quote. This establishes one compatible observation in isolated
replay, not a current fair value or a persisted production quote.

Missing, stale, mismatched or conflicting records produce
`quote_currency_unverified` or a conflict. Neither a US venue, ticker, company
name nor accounting currency is a currency source. Historical rows retain their
own original currency; no current-profile fallback is used for history units.

## 9. Share count and split reconciliation

New AAPL FY 2025 diluted EPS **7.46** and diluted weighted-average shares
**15,004,697,000** remain native annual observations. They are not point-in-time
current shares and cannot be copied to another instrument or share class.

The split request used an explicit limit of 1,000 and returned HTTP 402. The
effective current split completeness is therefore false. An empty response or a
limit-sized response also cannot establish complete history. The new FMP cache
scope separates these completeness semantics from older cached lists.

Existing adjustment-date/coverage-interval, native EPS/share reconciliation and
split-adjusted-price safeguards remain active. Dated retained split evidence is
preserved separately; a new quote never renews it. No additional split factor,
share count or adjustment is invented to recover a target multiple.

## 10. Listing freshness handling

The existing manual registry importers remain the bounded administrative entry
point. They take explicit local source files, preserve hashes/original clocks,
are idempotent and independently update listing and issuer-symbol evidence.
Conflict quarantine, retention bounds, ownership isolation and proof-based
cache invalidation remain covered by the complete regression suite. No downloader
or recurring refresh was added.

The retained 21 October directories expire at **22 October 2026 00:00 UTC** under
the unchanged one-day policy anchor. Their undocumented publication timezone is
not fabricated. A quote, profile, statement or later file read cannot renew
either proof. Beyond that clock, the same replay must report expired evidence.
Fresh acquisition would require another exact authorization; no directory fetch
was added to the seven-request AAPL plan. See the README's existing importer
commands for local administrative refresh; no data import occurred here.

## 11. Financial evidence and scope reconciliation

The new SEC facts were retrieved at **15:02:58.498795 UTC**. Submissions identified
annual accession `0000320193-25-000079`, filed **31 October 2025**, reporting
**27 September 2025**, and quarterly accession `0000320193-26-000020`, filed
**31 July 2026**, reporting **27 June 2026**. Fiscal year end is `0926`. The
selected annual document was retrieved at **15:02:59.899074 UTC**. Those clocks
remain distinct; retrieval in October 2026 does not make annual EPS current.

Annual net income **112,010,000,000**, equity **73,733,000,000**, diluted EPS and
shares remain separate normalized metrics with original units/filing identity.
Normalized total debt remains unavailable. Reported principal debt
**91.281 billion**, carrying debt **90.678 billion** and commercial paper
**7.979 billion** have different scopes; they are not interchangeable complete
enterprise-bridge totals. No absent preferred-equity/NCI tag is treated as zero.

The annual per-share declaration **1.02** refers to dividends and dividend
equivalents per share or RSU. It is a display-only candidate, not proof of cash
paid, quoted-class ownership, payout sustainability or a DDM forecast. Original
annual contexts are retained in the local document: FY `f-54`, equity `f-219`
(`c-20`), dividend `f-271`/`f-272`/`f-273` (`c-1`/`c-18`/`c-19`).

Previously acquired MSFT, NVDA, ORCL, JPM, AMZN, Alphabet, O and PGR facts were
reviewed locally, without repeating the eight downloads. AMZN/Alphabet debt
conflicts remain quarantined. Restricted cash, issuance costs, finance leases,
preferred/NCI and other nonoperating claims still need economically complete
scope before EV/DCF admission. Generic working capital, debt changes, narrow
depreciation, generic FCF and issuer-wide ownership are not substitutes for
operating NWC, net borrowing, aggregate D&A, AFFO or selected-class evidence.
`REVIEWED_FORECAST_SCOPE_CONCEPTS` remains empty.

## 12. Default model eligibility changes

No equation or model weight changed. No new real-data model was admitted.

| Model | Remaining decisive requirements in the focused evidence |
| --- | --- |
| FCFF DCF | Complete operating cash-flow/forecast scope, WACC and enterprise bridge |
| FCFE DCF | Complete equity cash flow, financing/net borrowing and common-earnings basis |
| Forward P/E | Current split-compatible target history and reviewed financial/forecast horizon; MSFT also lacks verified current quote currency |
| EV/EBITDA | Aggregate EBITDA, complete enterprise claims and compatible target multiple |
| EV/Revenue | Complete enterprise claims, compatible revenue forecast and target multiple |
| PEG | Compatible growth, forward EPS and split-compatible historical target |
| Graham | Meaningful common book equity, class-compatible shares and EPS |
| Dividend Discount | Compatible per-share dividends and sustainable projected payout/growth |
| Residual Income | Common book equity, clean surplus, compatible ROE/payout and cost of equity |
| Price/Book | Meaningful common-equity/class basis and compatible historical multiple |
| REIT AFFO | Reviewed REIT/class scope, AFFO and compatible target; generic FCF rejected |

The replay emits every required/available/missing input, model contract, source
record and financial blocker per security/model pair. Banking, insurance, REIT,
ETF, preferred and ADR restrictions remain distinct. Multiple methods sharing
earnings/growth/rates are not independent corroboration. No independent second
family became defensible from these acquisitions.

## 13. Production financial import dry-run analysis

`audit_financial_import.py` validates retained raw bytes against the original
Phase 6.7 manifest, resolves exact ownership and opens a read-only transaction
against the existing local PostgreSQL database. It does not create a database,
change a volume, refresh a cache or expose an apply option. SQLite tests restore
the prior query-only setting; output cannot overwrite source/manifest paths.

| Issuer | Already persisted observations | New observations | Different-filing restatement review candidates |
| --- | ---: | ---: | ---: |
| MSFT | 32,671 | 0 | 0 |
| NVDA | 27,281 | 0 | 0 |
| ORCL | 26,350 | 0 | 0 |
| JPM | 54,049 | 51 | 3 |
| AMZN | 0 | 29,761 | 0 |
| Alphabet | 0 | 20,907 | 0 |
| O | 0 | 21,723 | 0 |
| PGR | 0 | 35,127 | 0 |
| **Total** | **140,351** | **107,569** | **3** |

There are **247,920 unique incoming observations**, zero same-filing conflicts,
four hypothetical new company owners, four existing-company metadata updates
and eight proposed normalized snapshots. The three JPM restatement candidates
are review items, not approved overwrites. Native FY/FP/frame observations remain
preserved even when they describe the same economic context. Normalization is
version 6; the report lists existing versions and proposed snapshot hashes.

**Executed writes: zero.** Original acquisition/expiry bounds remain dated;
configured SEC TTL is a policy bound, not a fabricated original cache expiry.
Material import would require separate authorization, immutable source history,
ownership checks, rollback/safe-failure review and preservation checks. There is
no authorization to apply this dry run or the new AAPL bundle.

Example local-only command, using already retained files:

```powershell
backend/.venv/Scripts/python.exe backend/scripts/audit_financial_import.py --source .phase67.local/approved-sec-MSFT-0000789019.json --manifest .phase67.local/approved-sec-acquisition.json --ticker MSFT --as-of 2026-10-21T09:34:04Z --output .phase672.local/import-msft.json
```

The aggregate eight-source result is retained in ignored
`.phase672.local/financial-import-dry-run.json`. Running this command is an
inspection, not an import or a new provider request.

## 14. Current versus historical publication policy

`REVIEWED_FINANCIAL_CURRENTNESS_POLICIES` remains empty. The newly inspected
annual calendar does not establish a complete production input-path contract.
The annual-derived one-year EPS assumption has no explicitly supported current
forecast start/end or next-12-month roll-forward; no horizon was invented.

Current publication still requires independent current identity/listing proof,
financial source/period assessment, exact shares/currency, all model inputs and
a compatible observed quote where required. Neither a fresh retrieval nor an
available annual filing substitutes for those gates. Audit-only normalization
does not install a fresh production source cache. Intrinsic calculation
eligibility and current comparison/publication eligibility remain separate.

Historical AAPL/MSFT source values stay frozen. In the updated audit AAPL loses
the target P/E because current split/history compatibility is unsupported; its
updated result is unavailable. MSFT retains one historical illustration. The
preserved historical regression count of two and the updated eligible count of
one measure different things and are both reported explicitly.

## 15. Frontend integration

The existing design and JavaScript/JSX architecture remain. The company header
and provider/valuation panels expose security form, independent listing/issuer
verification, original quote observation date, unit proof and reporting-currency
compatibility. Price formatting no longer borrows accounting currency.

An expandable market-evidence panel shows access states, dated currency source,
hash/provenance, missing fields, cached-only acquisition scope and unresolved
rights. Backend values drive the presentation; there is no JavaScript valuation
arithmetic. Existing current/historical/unavailable, policy/single-model and
method-family disclosures remain visible. Long hashes wrap on mobile without
forcing the viewport wider. No API keys or account/contact data are displayed.

The new AAPL source was inspected in replay only. It was not injected into the
running application's cache to make the website appear current. Browser tests
exercise these states using explicitly mocked API responses.

## 16. Real versus synthetic evidence and reproducibility

The Phase 6.7.2 replay separates five evidence classes:

1. Retained financial fixtures from original Phase 6.7 source observations.
2. Previously approved SEC excerpts and Phase 6.7.1 directory/quote acquisitions.
3. Newly approved Phase 6.7.2 AAPL originals and safe manifest metadata.
4. Mocked provider/API responses used only by automated tests.
5. Synthetic negative/contract fixtures used only by automated tests.

Only the first three classes count toward real sample coverage. The new manifest
validator verifies exact receipt scope, path safety, hashes, bytes, clocks,
denial stop conditions and annual-document selection against SEC submissions.
A caller-supplied receipt is a scope check, not an independent consent service.
Raw FMP responses are not redistributed as fixtures. Small deterministic tests
need no provider credential or retained private bundle.

The replay blocks concrete HTTP transports, creates its fixture registry in
memory, writes JSON/Markdown locally and does not connect to the application DB.
The sample registry UUIDs are deterministic fixture identities, not production
IDs. No previously spent receipt authorizes a new request.

Maintained-excerpt replay (works without the private acquisition files):

```powershell
New-Item -ItemType Directory -Force .phase672.local | Out-Null
backend/.venv/Scripts/python.exe backend/scripts/replay_phase672_valuation_coverage.py --population retained --as-of 2026-10-21T15:04:55Z --output .phase672.local/retained-excerpts.json --markdown .phase672.local/retained-excerpts.md
backend/.venv/Scripts/python.exe backend/scripts/replay_phase672_valuation_coverage.py --population approved --as-of 2026-10-21T15:04:55Z --output .phase672.local/approved-excerpts.json --markdown .phase672.local/approved-excerpts.md
```

To reproduce the exact local before/after comparison, additionally use the
already retained manifests and their original receipts:

```powershell
backend/.venv/Scripts/python.exe backend/scripts/replay_phase672_valuation_coverage.py --population retained --as-of 2026-10-21T15:04:55Z --prior-manifest .phase671.local/approved-audit/manifest.json --authorization-receipt call_5bac25295829451a94f814a3c0674f98 --new-aapl-manifest .phase672.local/approved-aapl/manifest.json --new-authorization-receipt call_5e411a124b9c4a189a268fe58d77fd70 --compare .phase672.local/baseline-retained.json --output .phase672.local/after-retained.json --markdown .phase672.local/after-retained.md
```

Repeat with `--population approved` and the corresponding baseline/output paths
for the nine-security population. AAPL is outside that population, so its new
evidence is inventoried but not applied. Output includes original hashes,
observation/filing/listing/quote/retrieval/calculation clocks, classifications,
counts, source restrictions, exact blockers and before/after decisions. The
generated matrices cover all requested primary, secondary, sector and exclusion
controls, including GOOG/GOOGL, BRK.B, BABA, TSM, SPY and preferred AGNCN.

## 17. Authorized external requests actually executed

The [bounded proposal](phase672-free-data-acquisition-proposal.md) was explicitly
approved, including private FMP evaluation/retention permission. Its ceiling was
seven sequential GETs / 30 MB, 30 seconds total per request, at least one second
spacing, zero retries and no redirects. The acquisition was executed once:

| Order | Source | Result | Bytes |
| --- | --- | --- | ---: |
| 1 | FMP AAPL profile | HTTP 200 | 3,150 |
| 2 | FMP AAPL quote | HTTP 200 | 443 |
| 3 | FMP AAPL splits, limit 1,000 | HTTP 402; stop remaining FMP calls | 223 |
| 4 | FMP AAPL historical EOD | **Not requested** | 0 |
| 5 | SEC AAPL submissions | HTTP 200 | 163,778 |
| 6 | SEC AAPL companyfacts | HTTP 200 | 3,789,099 |
| 7 | SEC selected annual primary document | HTTP 200 | 1,520,323 |
| **Actual total** | **6 requests** | **No retries/redirects** | **5,477,016** |

The exact selected annual URL is
`https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm`.
FMP received only AAPL/endpoint parameters and the existing private key; SEC
received CIK/document paths and the existing identifying User-Agent/contact.
Secrets/contact details are absent from maintained artifacts and reports.

Original bytes and the redacted manifest remain ignored in
`.phase672.local/approved-aapl/`. No database import, extra directory request,
Treasury/OpenAI call, alternate symbol, provider fallback or paid subscription
occurred. The skipped request is not reusable authorization for another call.

## 18. Test counts and results

| Check | Final result |
| --- | --- |
| Complete backend suite, including guarded local PostgreSQL acceptance | **1,927 passed**, zero skips, zero real HTTP attempts |
| Frontend unit tests | **91 passed**, zero skips |
| Playwright desktop/mobile | **182 passed**: 91 desktop and 91 mobile, zero skips |
| ESLint | Passed |
| Explicit Vite production build | Passed |
| Python `pip check` | Passed |
| Frontend `npm ls --depth=0` | Passed |
| `git diff --check` | Passed |
| Source/private-artifact review | No configured secret or sensitive/generated path found in intended changes; nothing staged |
| Application preservation | All audited full-column hashes/counts unchanged; no import executed |

Tests cover access denials across restarts, rate limits, shared budget/scope,
cache-first behavior, no hidden profile/paid fallback, original currency proof,
wrong identity/venue, source clocks, denied/empty split completeness, manifest
tampering, read-only ownership/restatements, isolated replay and desktop/mobile
states. The complete suite retains eleven-model, scenario, reverse DCF,
sensitivity, override, PostgreSQL/migration and strict AI-validation regressions.

The PostgreSQL acceptance tests used the pre-existing guarded local test
database, distinct from the application database; no application volume was
reset. Backend transport guards recorded **zero** real HTTP attempts. Logs,
XML, screenshots, browser artifacts, dependency output and generated reports
remain ignored under `.phase672.local/` or existing test output paths.

Non-failing advisories: existing Starlette/httpx TestClient deprecation and a
Vite minified chunk of 510.81 kB (155.18 kB gzip). No check was suppressed.

## 19. Before/after valuation coverage

The before run used retained Phase 6.7.1 acquisitions at 09:34:04 UTC; the after
run additionally used the approved AAPL bundle at 15:04:55 UTC. Both retain the
same denominator and independent one-day reference policy.

| Retained population measure | Before | After |
| --- | ---: | ---: |
| Securities / model pairs | 30 / 330 | 30 / 330 |
| Current verified issuer linkage | 27 / 30 | 27 / 30 |
| Current verified listing | 30 / 30 | 30 / 30 |
| Financial statements available | 5 / 30 | 5 / 30 |
| Fresh compatible quote | 0 / 30 | **1 / 30 (AAPL)** |
| Compatible currency/share stage | 0 / 30 | **1 / 30** |
| Original historical regressions preserved | 2 | 2 |
| Eligible models recomputed with effective audit evidence | 2 / 330 | **1 / 330** |
| Recomputed historical illustrative outputs | 2 | **1 (MSFT)** |
| Current eligible defaults | 0 / 30 | **0 / 30** |
| Current published defaults | 0 / 30 | **0 / 30** |
| Independently corroborated model families | 0 | 0 |

AAPL's updated Forward P/E changes from historical illustration to unavailable
because `target_pe` is not established after current split/history failure.
Its original historical value stays **214.2302568301956**. MSFT remains the
single historical recomputation at **619.5604742486083**. No calculated current
value is substituted for either regression. The nine-security/99-pair acquired
sample remains unchanged: nine current listing/issuer proofs, nine financially
populated securities, zero compatible quotes, zero default model outputs,
zero current publications and zero independent corroborations.

There are **zero new real model calculations and zero new current publications**.
The updated AAPL quote and its financial normalization are audit-only, not
installed application coverage. These sample outcomes do not establish
market-wide valuation support for the 17,060 registered instruments.

## 20. Remaining provider and financial blockers

- FMP split entitlement is denied; historical EOD acquisition was stopped. No
  permitted complete current split/multiple path has been established.
- MSFT and other retained quotes lack compatible reviewed current currency
  evidence in this bundle; no additional symbol acquisition was approved.
- Financial currentness and a current forecast horizon have no complete reviewed
  production contract. New retrieval/annual availability cannot fill that gap.
- Debt/enterprise claims, common-book/class scope, sustainable per-share
  dividends, operating NWC, financing cash flows and discount assumptions remain
  incomplete for independent additional models. Missing values are not zeros.
- Application financial import is not authorized; the eight-source analysis is
  a read-only proposal. New AAPL raw evidence is also not installed in caches.
- Public display/redistribution rights for provider/reference sources require
  review before launch. Private evaluation permission is not a display license.
- Listing and issuer evidence expires independently after the stated clock;
  further acquisitions require a new bounded approval, not a TTL extension.

## 21. Next recommended engineering priorities

1. Review a complete input-path currentness/forecast-horizon contract from
   retained disclosures before adding any production allowlist entry. Preserve
   quarter/annual and source-version distinctions throughout.
2. Evaluate a legally permitted corporate-action/history source only under a
   separate documented entitlement/licensing review and bounded authorization.
   Do not repeat the denied split request to probe access.
3. Review the financial-import dry run and restatement/ownership plan separately
   before authorizing material writes; implement safe apply/rollback only then.
4. Complete an economically meaningful second-family scope contract rather than
   adding a correlated method to inflate model counts.
5. Resolve display rights and production operational budgets before deployment.

No additional acquisition, import, commit, push, merge or deployment is implied.
Engineering safeguards and diagnostics are improved; the first defensible
current default valuation remains explicitly **blocked**.
