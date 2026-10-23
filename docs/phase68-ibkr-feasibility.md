# Phase 6.8: IBKR feasibility and personal research boundary

Reviewed against official IBKR documentation on 22 October 2026. **Implemented and offline tested; no SDK installed, broker socket opened, subscription verified, or live observation acquired.** See the [separate connection proposal](phase68-ibkr-live-proposal.md) before considering access.

## Interface decision

Use the official Python TWS API through an operator-run TWS or IB Gateway session. Fairworth exposes a small asynchronous market-data facade over the SDK's callback interface. It provides contract details, one bounded watchlist quote subscription, daily historical TRADES bars, cancellation and disconnect. There are no browser, FastAPI, account, positions, order or transfer endpoints for this provider. Ordinary Fairworth startup remains independent of the SDK and broker availability.

The connection uses the actual operator-configured loopback socket port. TWS/Gateway handles login and any required multifactor authentication; Fairworth neither requests nor stores the IBKR password. Connection failures are distinct from an unavailable authenticated API session. The operator must retain **Read-Only API**, use localhost-only access, and disable downloading open orders on connection. The generic IBKR getting-started example enables trading by disabling read-only mode; that step is inappropriate for this adapter and must not be followed. Fairworth changes no broker settings. [Official connection reference](https://www.interactivebrokers.com/docs/tws-api/doc/connectivity/establishing-an-api-connection), [API settings](https://www.interactivebrokers.com/docs/tws-api/doc/tws-settings/introduction).

Client Portal/Web API is an alternative, but it introduces a separate local HTTPS gateway, browser authentication/session handling, and certificate configuration. Its documented local base address is `https://localhost:5000/v1/api`; that is not the TWS socket. No Client Portal gateway, insecure TLS workaround or OAuth credentials are introduced here. [Official Web API introduction](https://www.interactivebrokers.com/docs/web-api/v1/endpoints/introduction).

## Dependency and maintenance

`ibapi` is optional and dynamically imported only after an explicit local session authorization. No new mandatory dependency or network installer is added. Obtain a supported official release from IBKR rather than assuming a similarly named package index release is current. Keep the SDK and TWS/Gateway versions aligned, and record their exact installed versions before an approved connection.

IBKR's current changelog identifies TWS API **10.49** as released on 3 August 2026 under GPL; earlier releases had different licensing. This repository does not vendor or distribute the SDK. Operators must review the license of the version they install; this separation does not settle any future combined distribution obligations. Official installation, callback and protobuf changes still require compatibility testing against that installed release. The offline tests exercise the required SDK-facing methods with deterministic doubles, including both documented error callback signatures; they do not certify the installed SDK or broker service. [Official download guidance](https://www.interactivebrokers.com/docs/tws-api/doc/download-the-tws-api/introduction), [official changelog](https://www.interactivebrokers.com/docs/tws-api/changelog).

The implementation avoids a second full trading framework or an unofficial protocol implementation. Its cost is maintaining a small callback bridge and an explicit allowlist as the official SDK evolves. Unsupported outbound `req*`, `cancel*`, order and account operations are disabled on the bridge, including protobuf counterparts. The public facade has only contract and market-data methods.

## Subscription, use and retention permissions

A monthly subscription is evidence that the user pays for something; it does not prove the relevant username, exchange feed, API product, snapshot, historical service, or non-display use is entitled. Off-platform API permissions can differ from TWS display permissions and paper/live usernames. A denied request stops without a delayed fallback, retry, subscription purchase or FMP substitution. [Official market-data restrictions](https://www.interactivebrokers.com/docs/tws-api/doc/md/introduction), [API subscription troubleshooting](https://www.interactivebrokers.com/docs/third-party-integrations/general-third-party-frequently-asked-questions).

The current GFIS subscriber agreement distinguishes subscriber classifications and restricts non-display use, derived products and redistribution; its API supplement adds specific usage boundaries. The older IBKR agreement also restricts copying and redistribution without permission. Neither this feasibility review nor a personal subscription establishes permission to export, retain, calculate from, or publicly display data in Fairworth. Before live access, the operator must confirm the applicable agreement permits this exact private API research/non-display workflow; local retention needs its own confirmation. Third-party/public display and externally published derived values remain prohibited by Fairworth pending separate rights review. [GFIS subscriber agreement and API supplement](https://ndcdyn.interactivebrokers.com/Universal/servlet/Registration_v2.formSampleView?formdb=3089), [IBKR market-data subscriber agreement](https://www.interactivebrokers.com/Universal/servlet/Registration_v2.formSampleView?file=IBISAgreement.html).

## Contract identity and currency

The local CLI reads one exact issuer/instrument/listing from the existing registry by explicit IDs. The adapter requires a verified domestic ordinary-stock identity, supported primary MIC and SEC CIK. It requests STK/SMART with the exact symbol and primary exchange; it does not search another security on failure. Zero matches, multiple matches, a conflicting local symbol, venue, trading class, currency or missing positive conId fail closed.

If a separately sourced trading currency already exists, it must match the returned contract. Otherwise the exact contract's explicit ISO currency is retained as the market-data source; neither US listing membership nor financial reporting currency supplies it. Missing source currency is an error. A conId does not replace the CIK, establish issuer ownership, verify today's listing, reconcile consolidated share counts, or prove corporate actions. Selected share-class aliases require reviewed provider mappings; the initial CLI intentionally limits symbols to AAPL/MSFT.

## Quotes

`reqMktData` uses ordinary subscription mode with an empty generic tick list and `regulatorySnapshot=False`, then always cancels after at most twelve seconds. It never requests a chargeable regulatory snapshot. Last, bid and ask are kept separately. The actual `marketDataType` callback controls live/frozen/delayed/delayed-frozen classification, regardless of the requested type. Live/delayed tick families are not mixed. The last-trade observation timestamp comes only from source tick 45 or delayed tick 88, with source and retrieval clocks retained separately. Absent timestamp leaves the current comparison ineligible; retrieval time is never substituted. Missing last price is an unavailable result. A frozen or delayed result is retained as such, never described as live. [Official streaming/tick reference](https://www.interactivebrokers.com/docs/tws-api/doc/md/streaming-data), [market-data types](https://www.interactivebrokers.com/docs/tws-api/doc/md/delayed-data).

The local comparison flag also requires a source timestamp no more than five minutes old and not in the future. It is a private quote-level check, not authorization for a current valuation publication. Market open/closed state is not inferred from receipt or trade time. Outside-session and unavailable bid/ask observations are explicit nulls. A broker last-trade feed does not guarantee a contemporaneous executable price.

## History and corporate actions

Optional history is bounded to one request of at most 31 calendar days of regular-session daily `TRADES` bars, `keepUpToDate=False`. Source period dates, currency, contract and retrieval clock are retained. IBKR documents TRADES as split-adjusted and not dividend-adjusted; ADJUSTED_LAST is adjusted for both and is rejected by this adapter. Daily dates do not become invented precise UTC trade timestamps, and session-close/completeness is not asserted. Complete split-event history remains **false**: historical bars cannot resolve the earlier FMP split-history denial or alone make historical earnings multiples compatible. [Official historical bar conventions](https://www.interactivebrokers.com/docs/tws-api/doc/md/historical-bars).

Corporate-action services, future dividends, split factors and historical adjustment reconstruction are not requested. This initial adapter cannot produce an annual/multi-year multiple series from a 31-day sample.

## Pacing and safe errors

One operation runs at a time, with at least one second between request starts, bounded per-operation timeouts and exact per-session request counters. Failed/cancelled requests consume the approved budget. One instance cannot reconnect or reset counters. There is no automatic retry, delayed fallback, account rotation or paid endpoint discovery. Actual IBKR pacing also depends on the user's market-data line allowance and other clients, so the local ceiling is not an account-wide quota guarantee. Code 100/420 pacing failures are distinct from code 162's broader historical rejection. [Official pacing limits](https://www.interactivebrokers.com/docs/tws-api/doc/pacing-limitations/introduction), [pacing behavior](https://www.interactivebrokers.com/docs/tws-api/doc/pacing-limitations/pacing-behavior).

Safe error codes distinguish refused connection, unavailable/disconnected session, client ID collision, subscription missing, pacing, missing/ambiguous contract, conflicting security/currency, missing timestamp, absent price and unsupported historical adjustment. Raw SDK error text is discarded, including account/session details.

## Isolation and execution

All private records carry `provider=ibkr`, `permitted_use=personal_local_only`, `public_redistribution_allowed=false`, and `data_origin=simulated_ibkr|actual_ibkr`. The local JSON schema is `fairworth-private-ibkr-1`; exact contract, stable identity, source dates and an observation hash accompany retained values. Derived records must retain their source/permitted-use metadata.

Shared cache reads/writes recursively reject these records, including private evidence nested inside derived values. CompanyService rejects an injected IBKR provider before dispatch; private data from a mislabeled provider is also rejected. ResearchService rejects personal evidence before sanitization, context generation or external transmission. Tests insert a preexisting private cache payload and attempt public/API/AI exports; none succeeds. No personal observation is written to the application database, public source fixtures or analytics responses.

The TWS handshake may announce managed account IDs or the next valid order ID without an explicit account request. The bridge discards these and every other unused callback without retaining or logging arguments. The standalone CLI disables SDK/process logging before import/connection, does not collect balances/positions, and emits only a safe session result. The underlying official decoder may transiently receive unsolicited protocol fields; the application does not store, export or interpret them. No claim is made that TWS never transmits them.

Configuration defaults are `IBKR_HOST=127.0.0.1`, unset `IBKR_PORT`, nonzero client ID 68, fifteen-second timeout. Configuration alone cannot connect. `MARKET_DATA_PROVIDER` remains `disabled|fmp`; selecting `ibkr` for public mode is rejected.

An offline plan prints without importing the SDK or querying the database:

```powershell
backend/.venv/Scripts/python.exe backend/scripts/ibkr_local_research.py --symbol AAPL --instrument-id <registry-instrument-id> --listing-id <registry-listing-id>
```

After separately approved exact configuration and rights, the same CLI additionally requires `--connect`, an approval reference, `--confirm-personal-use`, `--confirm-api-non-display-use` and `--confirm-read-only`. Optional `--history-days 31` must be in that approval. Retention requires `--confirm-local-retention` and `--output .phase68.local/<unique-file>.json`; existing files are never overwritten and no other output directory is accepted. Without retention approval, private values stay in memory only. This command has **not** been run in connected mode.

Offline verification: `test_phase68_ibkr.py` covers authorization, loopback restrictions, identity/currency, live/delayed/frozen states, absent timestamps, request budgets, failures, historical semantics, SDK callbacks, forbidden operations, cache/API/AI isolation, and optional SDK absence. Test fixtures explicitly identify simulated observations. Full-phase verification counts are recorded in the main Phase 6.8 report.
