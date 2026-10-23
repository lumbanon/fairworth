# Phase 6.8: bounded IBKR connection proposal

**Connection settings confirmed; live access remains unauthorized. No connection or market-data request has occurred.** The user specified TWS at `127.0.0.1:7496`, socket clients enabled, Read-Only API enabled and localhost-only access. Only `IBKR_HOST` and `IBKR_PORT` were set in the ignored local environment file; unrelated configuration was preserved. This is a reviewable proposal, not an approval. [Feasibility and rights review](phase68-ibkr-feasibility.md).

| Item | Proposed bound / required operator information |
| --- | --- |
| Interface | Official Python TWS API with the user's existing TWS session. Exact TWS version remains to be recorded. The optional official Python SDK is not installed; no installer was run. |
| Host | `127.0.0.1`, literal loopback only. No public/private LAN proxy. |
| Port | **7496**, explicitly supplied by the user. No paper/live account type is inferred from the number. |
| Session | Existing operator-authenticated session; Read-Only API and localhost-only access retained; no automatic setting changes. Confirm open-order download is disabled. |
| Client ID | Nonzero 68, subject to operator confirmation that it is unused and is not configured as the master client. |
| Selected security | **MSFT**, CIK `0000789019`, instrument `d88edb79-a587-4475-82bd-2bf8071dc1c2`, listing `73fdd304-f2d1-43a9-bf15-4ad25699f32e`, primary MIC XNAS. This aligns with the demonstrated financial scenario; another security needs a different approval. |
| Contract operations | At most one `reqContractDetails`, using STK/SMART, exact MSFT symbol and primary exchange; no fuzzy lookup. |
| Quote operations | At most one ordinary `reqMktData` subscription, live type 1 requested, cancelled within twelve seconds. `regulatorySnapshot=False`; no paid snapshot or generic tick requests. Actual returned data type governs classification. |
| History | **Zero** for this minimum quote-only proposal. An additional daily-history request would require a separately reviewed and explicitly approved scope. |
| Bound | Two data operations maximum plus handshake/cancellation/disconnect; at least one second between starts; fifteen-second timeout per operation, zero retries and no reconnect. |
| Errors | Stop on session, entitlement or pacing denial; never purchase permissions or substitute another source/security. |
| Accessible personal information | TWS may announce managed account IDs/next order ID during handshake. Application callbacks discard these; no account, orders, balance, position or trading requests are made. SDK logging is disabled. |
| Outgoing information | Local connection/client ID, MSFT contract fields and exact requested data type. No password, API key, personal contact, chat history or financial statement export. |
| Retention | Default in-memory only; safe completion status excludes private prices. An optional unique JSON under ignored `.phase68.local/` requires explicit agreement-based retention permission. No database import or public cache. |
| Permissions | Confirm the applicable exchange/GFIS/API agreement permits the exact private API/non-display use and optional local retention. Existing monthly payment alone is insufficient. Public/third-party display, AI transmission and external derived-data publication stay disabled. |
| Blocker resolved | Could establish exact-contract currency and a source-timestamped private MSFT market observation. A current quote cannot silently roll the dated dividend valuation forward for a current upside claim. It cannot establish financial currentness, common-share denominator, complete split-event history, annual historical multiples, a second valuation family or public redistribution rights. |

The unconnected CLI plan was checked locally with these exact IDs and port; it reported `not_connected`, zero history/account/trading requests and no retention. It neither loaded the SDK nor opened a database/provider/broker connection in plan mode. The generated plan is ignored at `.phase68.local/ibkr-connection-plan.json`.

Before a live authorization request, record the installed TWS and approved official SDK versions, confirm client ID 68 is unused/non-master and open-order download is disabled, and establish applicable API/non-display permissions. The SDK must be installed under a separate reviewed setup step; it is not downloaded automatically. Retention remains **none** unless separately permitted and approved. The authorization reference and confirmation flags are operator receipts, not independent proof of consent or entitlement. The user's configuration reply expressly withheld live connection/data authorization.

No SDK installation, broker configuration changes, live IBKR access, FMP/SEC acquisition, OpenAI request, application import, commit or push is authorized by this document.
