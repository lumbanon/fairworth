# Phase 6.7.1 bounded acquisition proposal

Status: **explicitly authorized and completed on 21 October 2026**. The run made
8 requests / 1,417,683 bytes and stopped on PGR HTTP 402 before the remaining
FMP calls. See [the outcome report](phase671-valuation-coverage-completion.md).
The inventory below records the approved maximum, not permission for another
run. This was one-time local verification, not a scheduled downloader. No
previous approval was reused.

The retained caches contain no fresh quote. The identifying SEC directory and
exchange observations are independently expired. An API key is configured, but
that does not establish current FMP endpoint entitlement. Prior cached FMP
statement endpoints returned `provider_subscription_required`; those endpoints
and the previously restricted ORCL split endpoint are excluded from this plan.

## Exact request inventory

| Provider | Exact endpoint | Securities / CIK | Purpose | Maximum |
| --- | --- | --- | --- | --- |
| Nasdaq Trader | `https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt` | Directory; exact selected listings only reconciled locally | Refresh dated listing observations | 1 GET / 5 MB |
| Nasdaq Trader | `https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt` | Directory; exact selected listings only reconciled locally | Refresh NYSE/other exchange observations | 1 GET / 5 MB |
| SEC | `https://www.sec.gov/files/company_tickers_exchange.json` | Directory; exact issuer-symbol-venue links only | Refresh issuer linkage independently of listing evidence | 1 GET / 5 MB |
| FMP | `https://financialmodelingprep.com/stable/quote?symbol={symbol}` | AAPL / 0000320193; MSFT / 0000789019; NVDA / 0001045810; AMZN / 0001018724; PGR / 0000080661 | Price, observation timestamp, symbol | 5 GETs / 1 MB each |
| FMP | `https://financialmodelingprep.com/stable/profile?symbol={symbol}` | Same five securities | Currency, exchange, identity metadata; never sufficient share-class proof by itself | 5 GETs / 1 MB each |
| FMP | `https://financialmodelingprep.com/stable/splits?symbol={symbol}` | Same five securities | Dated split factors / completeness for historical EPS and price basis | 5 GETs / 1 MB each |
| FMP | `https://financialmodelingprep.com/stable/historical-price-eod/full?symbol={symbol}` | AMZN / 0001018724; PGR / 0000080661 | Permitted historical closing prices for filing-date-aligned own-history multiples | 2 GETs / 5 MB each |

The FMP key is added privately as the provider-required `apikey` query parameter;
it must never appear in logs, manifests, error output, or documentation. No CIK
is transmitted to FMP unless required by an endpoint; the table identifies the
expected local reporting issuer. No financial evidence bundle is uploaded.

## Hard limits and handling

- At most **20 sequential HTTPS GETs**, **40 MB total**, using decimal MB;
  concurrency one, at least one second between requests.
- Total timeout **30 seconds per request**, **zero retries**, **no redirects**.
  Stop a provider on access denial, entitlement restriction, or rate denial
  (including HTTP 401, 402, 403, 429 or equivalent provider error payload).
- Exactly one run. Do not replace failed calls with additional endpoints.
  Direct requests avoid adapter helpers that implicitly acquire profiles.
- Nasdaq receives ordinary HTTP request metadata only. SEC additionally receives
  the existing configured identifying User-Agent, including its contact address.
  FMP receives the symbols and existing key. No chat history, saved assumptions,
  database credentials or personal account data is sent.
- Raw responses and redacted manifests stay in ignored `.phase671.local/`.
  Record endpoint without key, SHA-256, actual bytes, status, retrieval clock,
  provider observation/publication clocks and exact selected identity.
- Validate each source's identity, dates, exchange and scope. A quote cannot
  renew issuer proof; a listing cannot renew SEC linkage; no date or TTL is
  advanced artificially. Fresh retrieval does not establish fresh observation.
- Initially reconcile in an isolated offline audit only. **No production
  database or cache imports** are authorized by approval of this proposal.
  Phase 6.7 raw financial imports require a separate reviewed plan and approval.
- FMP entitlement is **uncertain** despite earlier successful calls. No paid
  upgrade or purchase is authorized. No OpenAI request or charge is involved;
  FMP calls may consume the existing plan's allowance. Incremental provider
  billing cannot be promised without the user's subscription terms.
- Public display/redistribution licensing is **unconfirmed**. Approval is for
  local verification, not deployment or republication of provider datasets.

## Success tests and remaining limits

The three directories must yield dated, exact, mutually compatible observations
for the selected instrument and issuer. Quote results must have a usable price
and actual observation time within existing policy. Profile/split evidence must
support, rather than assume, the selected security's class/currency/price basis.
Historical prices must support the existing minimum three distinct qualifying
annual observations, with valid EPS periods and publication-date alignment.

Existing AAPL/MSFT/NVDA historical observations can be reused only for their
dated historical role. Newly acquired AMZN/PGR prices may still be insufficient
for a defensible multiple. This proposal does not resolve incomplete debt,
senior claims, common-equity or discount-rate evidence and does not guarantee
five eligible securities or independent multi-model coverage. Missing or
restricted results stay unavailable.

If authorization is declined or unavailable, offline fixtures and the existing
strict gates remain in place, and actual current coverage remains blocked.
