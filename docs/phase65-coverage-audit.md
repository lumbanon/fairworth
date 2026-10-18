# Phase 6.5 — Coverage audit and implementation contract

Stage A baseline: 2026-10-18, commit `79caf6ba6a10937025da69a215febc96fb4856fe`.
The existing `feature/phase-6-5-model-coverage` branch initially referenced Phase
3. Its tracked tree was clean and it was an ancestor of Phase 6, so it was
fast-forwarded to the completed Phase 6 baseline without changing branches or
creating a commit. This audit precedes Phase 6.5 implementation.

## Observed coverage

The financial application has no four-ticker allowlist. SEC directory resolution
already accepts arbitrary matching registrants, then attempts on-demand profiles,
Company Facts, normalization, automatic assumptions and valuation. The four
retained companies are regression examples, not a complete supported universe.

The local database contains five persisted issuer/company identities and 64
cache entries. JPM is the fifth: CIK `0000019617`, NYSE, SIC `6021`, with a cached
profile, raw SEC facts, normalized v3 data and an FMP quote. Its SEC snapshot was
retrieved 2026-10-15T12:19:29.838468Z and contains 17 annual periods (2009–2025).
The dated quote is $335.28, observed 2026-10-14T20:00:02Z and retrieved
2026-10-15T12:19:50.607878Z. Multiple-security/share-basis warnings remain. Cache
presence establishes ingestion beyond the original four; it does not prove a
valid valuation, instrument classification, current listing or successful AI
response. No fresh source request was made during Stage A.

| Capability | Existing behavior | Gap |
| --- | --- | --- |
| Discovery | SEC reference directory plus bounded query results | Registrants are not the complete active listed-security universe |
| Search | Case-insensitive in-memory scan; per-query SQL cache; 10 default / 50 maximum results | No indexed persistent universe, pagination, source lifecycle or security labels |
| Issuer identity | CIK resolution from SEC; Company Facts checks returned CIK | Submissions and FMP enrichment need matching checks; ticker is incorrectly a persistent identity |
| Profile | SEC identity, optional FMP profile/quote | CIK is mandatory in API schemas, preventing honest missing-CIK security records |
| Statements | On-demand raw facts and versioned normalized snapshots | US GAAP/DEI USD scope; partial or absent statements can prevent useful frontend rendering |
| Valuation | Deterministic eleven models with strict Phase 6 gates | No explicit ETF/warrant/preferred/ADR instrument gate; legacy assumptions can overstate class compatibility |
| AI | Strict typed bindings, categories, citations, numbers and privacy; exact company snapshots | Stable instrument/listing IDs must join cache/evidence identity; sparse evidence must remain sparse |

## Identity and cache risks

`companies.ticker` is unique, and the repository can overwrite its CIK. On ticker
reuse, old financial and market rows could remain attached to a newly assigned
issuer. Quotes, profiles, history, supplements and process-local valuation
snapshots also use bare ticker keys. Raw facts scoped by CIK and normalized
CIK/ticker/version keys provide a stronger starting point.

Mechanical dot/hyphen conversion cannot independently prove share-class identity.
Multiple names, ticker reuse, inactive listings, provider symbols and foreign
depositary securities need explicit evidence and validity intervals. An unknown
security type is not automatically ordinary common stock. Unsupported securities
must remain discoverable/profile-visible where evidence exists, while ordinary
valuation stays unavailable even with manually supplied assumptions.

## Provider contracts and limitations

SEC source adapters reference official developer/API documentation. Their current
directory is `company_tickers.json`, whose cached normalized rows retain only
ticker/name/CIK, with exchange populated later from submissions. No full directory
or exchange-directory snapshot is persisted locally. Fresh documentation and
reference access require the separately requested bounded audit authorization.

FMP is optional and configured server-side. Existing safe errors distinguish
401/403 denial, 402 subscription restrictions, 404 absence, 429 limits and
temporary/time-out failures. Denial caches are endpoint/symbol-specific; successful
old data is preserved on failed refresh. Existing artifacts establish restrictions
on some statements and ORCL history/quotes, not a global unrestricted subscription
or a verified plan name. No permissions will be inferred or bypassed.

SEC Company Facts normalization retains unsupported taxonomy observations, but
supports selected US GAAP/DEI USD financial concepts. Accepting a 20-F form label
does not establish IFRS normalization, currency translation or an ADR ratio.
Automatic native annual publications and AI filing extraction have narrower
document coverage. These limitations must remain explicit.

## Agreed implementation boundaries

1. Add stable issuer, instrument, listing, alias and refresh identities with
   source provenance and validity intervals. Never merge merely by name, ticker
   or missing CIK. Reassignment creates a new relationship and preserves history.
2. Import validated, dated local source snapshots atomically and idempotently;
   provide explicit provider refresh capability with bounded requests. Search
   operates on indexed SQL records and never fetches the universe per keystroke.
   Incomplete reference snapshots must not silently delist absent securities.
3. Preserve existing ticker routes while passing optional `instrument_id` for
   explicit selection. Return ambiguity instead of silently choosing a candidate.
4. Carry `issuer_id`, `instrument_id`, `listing_id`, exchange, source identity,
   instrument type, classification confidence and listing status through profile,
   source caches, financial response metadata, valuations and AI snapshots.
5. Separate source availability from financial suitability. Keep unknown classes,
   unverified ADR/share/currency basis and unsupported security types blocked.
   Preserve existing model equations, debt/period gates and four-company fixtures.
6. Add independent company coverage stages: `symbol_resolution`,
   `classification`, `profile`, `statements`, `normalization`, `freshness`,
   `valuation`, and `ai_research`. Each has a status, reason codes and explanation;
   valuation adds actual model IDs/count/classification/quality. AI evidence and
   configured AI-provider readiness are different capabilities.
7. Use the statuses `available`, `missing_evidence`, `provider_restricted`,
   `not_supported`, `financially_inapplicable`, `temporarily_unavailable`, and
   `identity_ambiguous`. State stale observations in the freshness stage instead
   of confusing them with permanent instrument/model inapplicability.
8. Improve search labels and identity-aware navigation; retain debounce/abort and
   bounded results. Render useful profile/coverage pages when statements are
   missing. Keep source and valuation controls conditional on backend authority.

## Verification plan

Maintain actual dated public identity evidence separately from clearly synthetic
financial/registry-scale fixtures. A desired sample symbol is not verified merely
because it appears in the task brief. Preserve unavailable/unaudited statuses
where fresh reference access is not authorized or evidence is absent.

Test issuer/ticker reassignment, name ambiguity, share-class aliases, missing CIK,
inactive/renamed listings, ETF/preferred/warrant/unit gates, ADR/currency/IFRS
limits, FMP identity mismatch, permissions/rate limits, stale snapshots and
concurrent requests. Exercise banks, insurers, REITs, growth/dividend/cyclical
businesses using explicit synthetic model inputs where actual financial coverage
is absent. Do not report those synthetic successes as real company valuations.

Run the complete backend suite, dedicated PostgreSQL migration/history/query
plan tests, frontend units, desktop/mobile browser regressions, lint, build,
dependency validation and all mocked AI checks. Benchmark realistic thousands-row
registries and bounded concurrent search without making production throughput
claims. No paid/live OpenAI, bulk financial downloads, database resets, commits
or pushes are authorized for implementation.
