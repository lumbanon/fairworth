# Phase 6.6 baseline audit

Stage A, 19 October 2026. This document precedes Phase 6.6 runtime edits.

## Repository and preservation boundary

The checked-out branch is `feature/phase-6-6-active-listing-coverage`. It initially
pointed to Phase 6 (`79caf6ba6a10937025da69a215febc96fb4856fe`). The user explicitly
authorized a fast-forward to the completed Phase 6.5 dependency:
`0506073d3fb4506281bf2cb9335a85ec9963fe8b`. That operation completed without
switching branches or creating a merge commit. The tracked tree was clean after
the fast-forward. No other Git operation, commit, push or deployment is authorized.

Existing migrations are `0001_financial_data` and `0002_security_registry`.
Phase 6.5 source, tests and its two reports are present. The existing development
database, provider caches, original observations and financial snapshot ownership
must be preserved. Migration verification uses the existing dedicated
`fairworth_test` PostgreSQL database with explicit target/emptiness guards.

## Observed reference population

The read-only baseline registry audit found 8,030 issuers, 10,444 instruments,
10,444 listings, 45,865 aliases and one SEC reference refresh. All 10,444 listings
are `unknown` status and `reference_only` identity; all instrument types are
`unknown`. Issuers have CIK mappings, but a CIK does not establish security form,
share class, active status, quote compatibility or a depositary ratio.

The retained source observation is 18 October 2026; its retrieval timestamp is
`2026-10-18T12:11:32.351992Z`. Neither timestamp proves active trading. Existing
issuer/instrument/listing UUIDs must survive any uniquely evidenced enrichment.
No arbitrary company-name or CIK-only instrument merge is permitted.

The preceding documented financial baseline contains five companies (AAPL,
MSFT, NVDA, ORCL and JPM), 165,486 original facts, nine financial snapshots,
14 market snapshots and 64 cache entries. A fresh read-only ownership check is
required before the proposed ownership migration is applied. These are retained
local observations, not fresh financial coverage claims.

The subsequent read-only ownership check confirmed every one of these five exact
CIKs maps to exactly one existing registry issuer. Company IDs and child-row
counts below are the preservation baseline; no facts or snapshots were changed:

| Symbol | Company ID | CIK | Original facts | Financial snapshots | Market snapshots |
| --- | ---: | --- | ---: | ---: | ---: |
| AAPL | 1 | 0000320193 | 25,135 | 2 | 3 |
| MSFT | 6 | 0000789019 | 32,671 | 2 | 7 |
| NVDA | 11 | 0001045810 | 27,281 | 2 | 3 |
| ORCL | 16 | 0001341439 | 26,350 | 2 | 0 |
| JPM | 672 | 0000019617 | 54,049 | 1 | 1 |

## Ten independent capabilities

| Capability | Phase 6.5 baseline | Phase 6.6 work |
| --- | --- | --- |
| Ticker discovery | Indexed SEC reference search; 10,444 rows | Preserve bounded search and pagination |
| Verified security identity | Reference-only rows; stable UUIDs | Source-linked observations and explicit ambiguity |
| Verified active US listing | Not independently established | Dated authoritative directory observations, conflicts and staleness |
| Verified security form | Unknown for the real registry | Evidence-backed form; separate issuer business category |
| Compatible issuer/share mapping | CIK available, class compatibility not implied | Preserve class boundaries and financial share-basis gates |
| Company profile | Identity-only fallback; richer retained profiles | Keep sparse workspaces and provider restrictions explicit |
| Financial statements | Five retained financial issuers in the dated sample | On-demand compatible ingestion, no market-wide financial preload |
| Normalized evidence | Versioned US-GAAP mapping; unsupported IFRS remains unavailable | Preserve source, currency, period and debt checks |
| Eligible valuation | No newly scoped reference-only security eligible | Remove only justified classification blockers; unchanged equations |
| AI Research evidence | Scoped typed evidence; no new AI request required | Add verified identity metadata without weakening validation |

Freshness remains a separate diagnostic rather than a substitute for these ten
capabilities. Counts use explicit denominators and distinguish real observations,
retained historical fixtures, synthetic cases and mocked providers.

## Existing architecture and gaps

- SQL prefix/name-token search and exact-symbol resolution return bounded pages.
  Ambiguous tickers require explicit instrument/listing selection. Company-name
  aliases are search aids; only separately evidenced symbol aliases authorize
  provider symbols. GOOG/GOOGL retain distinct instruments even with one CIK.
- Registry imports are atomic, idempotent and source-dated; omission does not
  delist. The source namespace currently creates separate records across
  providers, so cross-source enrichment needs explicit linkage and immutable
  source observations. Directory symbols are not permanent security identifiers.
- The legacy type combines security form and business category. A bank's common
  stock must remain common stock while bank-specific eligibility applies.
- `companies.ticker` has a unique index. Financial persistence fails closed on
  ticker reuse instead of overwriting the CIK. A reviewed issuer ownership FK
  can resolve this only if exact legacy mappings are unambiguous, preserving
  company IDs and all fact/snapshot FKs. Downgrade must refuse duplicate tickers.
- Scoped provider caches include issuer/instrument/listing IDs and source
  versions. Raw SEC Company Facts remain CIK-scoped. Owner leases, fenced
  publication and reference-counted locks must remain intact. Listing verification
  versions must invalidate derived analysis and report caches independently of
  statement/quote retrieval clocks.
- SEC raw payload CIKs and FMP symbol/venue/class mappings are checked. Endpoint
  denials are distinct from missing financial evidence. A profile or stale quote
  does not verify active listing. Key presence does not establish FMP entitlement.
- USD/US-GAAP normalization, verified share basis, debt completeness and eleven
  authoritative formulas remain unchanged. IFRS mapping, FX translation and
  non-unit ADR conversion are not silently introduced.
- AI adapter `financial-evidence-3` and prompt `fairworth-research-9` retain exact
  request-scoped bindings, categories, citations, numerical checks and privacy.
  Source/identity changes must participate in snapshot/cache isolation; the exact
  successful legacy v8 MSFT fixture must remain reproducible offline.
- Frontend coverage currently shows eight stages. It needs ten independent
  capability cards, source clock distinctions and conservative verified labels,
  with expandable provenance and unchanged desktop/mobile design.

## Audit conclusions and implementation boundary

Use official listing documentation first; see the separate source/license audit.
No fresh listing or financial data acquisition has been authorized for Phase 6.6
at this baseline. A bounded two-file directory request is awaiting explicit
approval. Runtime implementation and mocked/offline tests may proceed without it.
No live OpenAI request, formula change, database reset or automatic commit is
permitted. Prior Phase 6.5 verification (1,461 backend, 70 unit and 144 browser
tests) is historical evidence; Phase 6.6 must run its own final checks.
