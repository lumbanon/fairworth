# Phase 6.6 listing source and license audit

Documentation reviewed 19 October 2026. This is an engineering access audit,
not a grant of redistribution rights. No account entitlement is inferred from a
configured key. Fresh data requests require the user's bounded approval. The
approved two Nasdaq directory requests and one SEC reference-directory request
completed on 19 October 2026; no financial-history or AI acquisition was included.

## Candidate sources

| Source | Fields and scope | Clocks/history | Access and rights decision |
| --- | --- | --- | --- |
| [Nasdaq Trader directory definitions](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs) | Nasdaq symbols/security descriptions/market category/test flag/financial status; other-listed ACT/CQS/Nasdaq symbols, exchange and explicit ETF flag | Files update during the day; creation footer is an observation/publication marker with undocumented timezone. No listing-start or corporate-action history inferred | Two public HTTPS files acquired within explicit local-audit approval. Test issues excluded; financial deficiency is not suspension; ETF=N does not prove common stock |
| [Nasdaq symbol lookup](https://www.nasdaqtrader.com/trader.aspx?id=symbollookup) | Nasdaq and other-exchange current directory lookup | Current trading-day scope, not complete historical lifecycle | Page distinguishes unrestricted event datasets from restricted products. Exact rights for planned public display and redistribution of all imported directory fields require operator confirmation; launch blocker |
| [NYSE reference products](https://www.nyse.com/market-data/reference) and [Security Master](https://www.nyse.com/data-products/catalog/nyse-group-security-master) | Daily security/reference products; ADR master; broad cross-asset security master | Start-of-day products and separately licensed history; not a free historical corporate-action source | Licensed product. No subscribed account or commercial feed access assumed. Do not download sample archives or treat cross-asset record counts as listed-stock coverage |
| [SEC APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Issuer CIK, ticker/exchange reference, submissions, original XBRL facts | Filings and facts are dated separately from retrieval; reference directory is not active-listing proof | One fresh ticker/exchange reference GET separately approved and completed. Historical reference/financial evidence retained. Fresh company facts/submissions still require separate bounded approval |
| [SEC developer resources](https://www.sec.gov/about/developer-resources) | Access policy for official SEC endpoints | API updates follow filing dissemination | Identifying User-Agent, efficient access and aggregate maximum ten requests/second across machines. Existing per-worker throttling does not establish a global multi-worker rate limit |
| [FMP documentation](https://site.financialmodelingprep.com/developer/docs) | Stock list, active-trading list, ETF list, profiles, exchange variants, statement symbol lists, symbol changes and delisted companies | Endpoint-specific dates/history; no assumption of complete lifecycle | No FMP request made. Documented endpoint existence is not subscription access. Retain distinct 401/403/402/404/429/timeout outcomes |
| [FMP terms](https://site.financialmodelingprep.com/terms-of-service) | Account-specific financial and market-data services | Entitlements and terms may change | Public display/redistribution needs the appropriate agreement. Local key presence and cached successful quotes do not establish that right; unresolved launch blocker |

## Parser and evidence contract

Official Nasdaq file paths:

- `https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt`
- `https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt`

Retain source URL, exact content/row hashes, parser version, creation footer,
observation date, retrieval UTC and original public fields. Preserve an absent
effective date and an unknown footer timezone. Do not convert the footer to an
invented UTC timestamp. Require known headers, valid rows, bounded sizes and
consistent snapshot quality before atomic publication.

Map documented exchange codes explicitly: Nasdaq to XNAS; other-listed N to NYSE
(XNYS), A to NYSE American (XASE), P to NYSE Arca (ARCX), Z to Cboe BZX (BATS),
and V to IEX (IEXG). Preserve unfamiliar codes as unverified rather than guessing.
Financial-status deficiency/bankruptcy flags are warnings, not trading halts.
Directory membership supports a dated listing observation, not uninterrupted
trading, a corporate-action relationship or future active status.

Classification uses explicit source fields and descriptions, never symbol
suffixes alone. Security form and issuer business category are separate. Source
aliases require actual row fields; no mechanical punctuation conversion is proof.
A matching CIK can join issuers but cannot merge separate quoted instruments.
Conflicting authoritative observations remain inspectable and block convenient
promotion to verified status. Absence from a refreshed directory remains an
unreconciled omission, not a delisting.

## Completed bounded acquisition and evidence record

The user explicitly authorized exactly two sequential HTTPS GETs to the Nasdaq
paths above, with zero retries, no redirects, a 30-second timeout and a 5 MB bound
per file. Both returned HTTP 200. A separately authorized single GET to the
[SEC ticker/exchange directory](https://www.sec.gov/files/company_tickers_exchange.json)
used the same 5 MB, 30-second, zero-retry/no-redirect bounds and returned HTTP 200.
The three requests transferred 1,416,449 bytes in total and stayed within every
bound. No API key, subscription endpoint or known per-request charge was involved.
The SEC request used the existing configured identifying User-Agent; its contact
details are not reproduced in documentation or fixtures.

| Source file | Bytes | Retrieved at (UTC) | Exact SHA-256 |
| --- | --- | --- | --- |
| Nasdaq-listed | 349,398 | 2026-10-19 11:45:39.025685 | `e53df7b657e8d358300234b78323f3d62db0d30b70e20ebb8f76c8d8bde6f487` |
| Other-listed | 543,200 | 2026-10-19 11:45:39.787934 | `5c301c1313e61742bc6c9536eafc214949df76c9276ccb8df12c849115dde94e` |
| SEC ticker/exchange reference | 523,851 | 2026-10-19 11:55:33.555239 | `6c29e2e3db973d4479875164603c2434f81ad22e14c9f1694999aca9cca246cb` |

The Nasdaq creation footer was `1019202607:00`; its undocumented timezone remains
unknown. SEC retrieval and reference observation are dated separately from
financial filing periods. Acquired data consists of public security symbols,
descriptions, exchange/ETF/status flags, footer metadata and issuer CIK references.
No company-facts, submissions, quote/history, FMP, Treasury or OpenAI request was
made, and no new financial coverage is inferred from the reference snapshots.

Raw snapshots and acquisition logs stay in ignored `.phase66.local/`. Small
curated public record excerpts were audited into the 82,451-byte deterministic
fixture `backend/tests/fixtures/registry/nasdaq_listing_sample_2026_10_19.json`:
30 actual public listing rows and dated SEC linkage evidence, with no secrets or
contact information. Original full snapshots/manifests remain local ignored
artifacts. The fixture preserves actual source wording and does not invent a
classification, CIK alias, ADR ratio or financial value.
Acquisition is for local engineering evaluation; public deployment remains
blocked by unresolved display/redistribution rights. Any further financial or
metadata audit needs its own explicit request bound and approval. Implementation
continues to distinguish real listing observations, retained financial evidence
and synthetic/mock validation results.

## Observed source limits after approved import

The development registry contains 17,060 listing records and 13,248 dated active
observations, including 6,661 recorded CIK-linked verified identities. All 10,444
original listing/instrument/issuer UUID associations were preserved. Nineteen
other-listed rows have an undocumented exchange code and remain unverified.
These counts include funds and specialized instruments and are not a count of
supported operating-company valuations or all uniquely listed US stocks.

The real 30-security sample has 27 verified security identities representing
26 unique CIK-linked issuers, plus three unresolved registry issuer IDs. BRK.B's
unproven BRK-B alias and CMT/SPY's differing SEC versus listing-directory venues
are not silently reconciled. GOOG's “Capital Stock” and TSM's absent form descriptor
remain unknown. NVO's directory common-share description does not establish
domestic reporting, ADR conversion or compatible foreign financial evidence.

Only five existing dated financial sets were replayed. Current market-cap tiers,
recent-listing/IPO dates, uninterrupted trading, historical lifecycle relationships
and public redistribution rights were not independently established by these GETs.

## Operational limitations

NYSE commercial identifiers/history and verified depositary ratios remain outside
this access plan. Public text directories do not provide every permanent security
identifier, IPO/delisting date, trading suspension, beneficial share basis or
currency mapping. Missing fields remain unknown. The existing provider cache and
operator-controlled refresh architecture must not become unattended scraping.
