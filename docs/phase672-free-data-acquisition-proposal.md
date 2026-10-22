# Phase 6.7.2 — Minimum AAPL evidence proposal

Status: **authorized and executed once on 21 October 2026**. The operator approved
all seven bounded requests and confirmed that their FMP agreement permits private
local evaluation and retention. Six requests transferred **5,477,016 bytes**;
the FMP split request returned HTTP 402, so the historical-price request was
skipped. No unused request authorizes a substitute endpoint or another attempt.
Earlier Phase 6.7/6.7.1 approvals remain exhausted.

The redacted receipt and original bytes remain in ignored
`.phase672.local/approved-aapl/`. See the
[implementation report](phase672-real-data-valuation-integration.md) for the
actual outcomes, source clocks and unresolved valuation blockers. No database
import, OpenAI request, subscription upgrade or public redistribution was
authorized or performed.

The first target is **AAPL / CIK 0000320193**, its exact registered common-stock
instrument and Nasdaq listing. This proposal does not acquire every symbol or
change the application database. MSFT is the next target only after this path is
assessed, under a separate authorization.

## Request inventory and limits

| Order | Provider / endpoint | Required evidence / blocker | Maximum |
| --- | --- | --- | --- |
| 1 | FMP `https://financialmodelingprep.com/stable/profile?symbol=AAPL` | Explicit currency, exchange, CIK, symbol and source version; exact-listing currency contract | 1 GET, 1 MB |
| 2 | FMP `https://financialmodelingprep.com/stable/quote?symbol=AAPL` | Original price and observation timestamp; profile is never used as a replacement quote | 1 GET, 1 MB |
| 3 | FMP `https://financialmodelingprep.com/stable/splits?symbol=AAPL&limit=1000` | Dated complete split basis, if the response establishes completeness | 1 GET, 1 MB |
| 4 | FMP `https://financialmodelingprep.com/stable/historical-price-eod/full?symbol=AAPL&from=2020-01-01` | Filing-aligned split-adjusted price observations; no market-wide history | 1 GET, 5 MB |
| 5 | SEC `https://data.sec.gov/submissions/CIK0000320193.json` | Latest applicable annual filing metadata, report date, calendar/identity/currentness review | 1 GET, 2 MB |
| 6 | SEC `https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json` | Refresh expired AAPL facts only; retain concept/unit/filing vintages, compare to original dated inputs | 1 GET, 12 MB |
| 7, conditional | SEC `https://www.sec.gov/Archives/edgar/data/320193/{accession_without_hyphens}/{primaryDocument}` | At most one latest applicable annual primary document selected from request 5; verify reporting/class/disclosure policy before admitting currentness | 1 GET, 8 MB |

**Absolute ceiling: 7 requests / 30 MB (decimal), sequential, at least one second
apart, 30-second total timeout per request, zero retries and no redirects.**
The conditional filing must be the exact AAPL 10-K/10-K/A selected from the
returned SEC submissions record. Validate accession syntax and a simple relative
primary filename; no arbitrary URLs, linked exhibits, older submissions pages or
extra filing downloads. If no unambiguous latest applicable annual record exists,
do not issue request 7.

## Authorization and access

The [FMP Basic pricing page](https://site.financialmodelingprep.com/developer/docs/pricing)
describes a free account with 250 calls/day and restricted endpoint/symbol access.
This is not proof that this account can use all four requested endpoints.
The dated AAPL quote success does not establish present entitlement. Stop **all
remaining FMP calls** immediately on HTTP 401/402/403/429 or equivalent access
error payload; do not try a different symbol or substitute endpoint. No paid
statement endpoint, PGR or ORCL access test, account rotation, subscription or
purchase is included. A successful but empty/truncated split response is not
proof of no splits or complete history.

The [FMP terms](https://site.financialmodelingprep.com/terms-of-service) restrict
personal use, third-party display and copying/downloading. Public display rights
and local response-retention permission are **not inferred from the free key**.
Before the FMP portion, the operator must confirm that their account's agreement
permits this private local API evaluation and response retention. Approval of a
request does not itself override provider terms. If that permission cannot be
confirmed, execute only separately authorized SEC requests and keep FMP blocked.
No provider account or commercial redistribution license is created.

SEC documents are public and its APIs do not need an API key. Use the existing
identifying User-Agent and conservative fair-access rate. No SEC source access
is inferred from old approvals.

## Privacy, cost, storage and update semantics

- FMP receives only `AAPL`, endpoint parameters and the privately appended
  existing API key. The key must not appear in logs or source manifests.
- SEC receives the public CIK/filing path and existing identifying User-Agent,
  including its configured contact address. Do not print that address.
- No chat history, model assumptions, financial evidence bundle, database
  credentials or user account records are uploaded. No OpenAI/Treasury request.
- No known SEC fee; FMP may consume up to four calls and 8 MB of the existing
  allowance. No upgrade or additional payment is authorized. Remaining account
  allowance and any separate account-specific terms are unknown.
- Retain raw bytes and redacted SHA-256/status/byte/time manifest in ignored
  `.phase672.local/`. No raw FMP response enters Git or a public dataset. Storage
  permission must be confirmed as above; retain evidence only as permitted for
  this private review, with no automatic deletion of existing local data.
- Reconcile only in disposable offline replay. **No production/development data
  import or cache refresh is authorized by this acquisition approval.** The
  eight-source import dry run has no apply operation and needs separate review.
- Reuse the 21 October retained listing and issuer observations only while their
  existing independent TTLs remain valid. If they expire before execution, stop
  current-valuation verification and request a separate bounded reference plan;
  do not add directory requests to this budget or advance dates.
- Preserve original price/financial/filing/source clocks and historical AAPL/MSFT
  regression evidence. Metadata currency applies only to the matching listing
  and supported quote observation/version period. A new profile cannot silently
  re-denominate a dated price.

## Success test

Evaluate one complete AAPL Forward P/E path, including exact identity, compatible
currency, splits, permitted historical multiple, financial observation currentness
and default assumptions. Review source-backed policy before registering any
production currentness rule; fresh downloads alone are insufficient. Record all
remaining blockers if the data fails any condition. The plan does not guarantee
a current result, a second independent model, or an adequate historical response
under the free account. No unsupported fallback or relaxed financial gate is
authorized.

Documentation references: [profile](https://site.financialmodelingprep.com/developer/docs/stable/profile-symbol),
[quote](https://site.financialmodelingprep.com/developer/docs/stable/quote),
[splits](https://site.financialmodelingprep.com/developer/docs/stable/splits-company),
[historical prices](https://site.financialmodelingprep.com/developer/docs/stable/historical-price-eod-full),
[SEC APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).
