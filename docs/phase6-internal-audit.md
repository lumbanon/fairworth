# Phase 6 — Stage A audit and implementation decisions

Audit baseline: existing Phase 5.1 commit `4a4eb874abd0a0a45bc83d6b1cfb6ddc9236f516`.
The user's Phase 6 branch initially pointed to Phase 3 (`2e93fd4`); it was
fast-forwarded to that already completed local commit. No new commit was created.
This audit precedes Phase 6 implementation changes.

## Architecture and evidence boundary

- Phase 3 `FinancialService` caches raw SEC Company Facts separately from
  versioned normalized JSON. All original concepts, dates, accessions and units
  are retained in `FinancialFact.original_source`; immutable content-hashed
  `FinancialSnapshot` JSON records preserve each normalized result.
- Phase 4 `build_valuation_inputs`, explicit eligibility paths and eleven pure
  model functions form the authoritative financial boundary. Transient scenario
  assumptions and user overrides are never persisted as reported facts.
- Phase 4.5 `AutomaticInputsService` uses separate versioned evidence caches,
  native annual publications, compatible price/split history and sourced rates.
  It retains restricted FMP endpoints and incomplete components as unavailable.
- Phase 5.1 freezes each exact request-scoped evidence registry, generates typed
  references under dynamic enums, then independently validates category,
  citations, numerical claims and privacy. These protections must remain intact.
- PostgreSQL already stores flexible JSONB source/derivation metadata. Additional
  normalized fields and diagnostics do not by themselves require a schema change.
  Existing historical fact rows/snapshots must not be rewritten to hide a new
  normalization interpretation. Their initial `normalized_metric` is ingestion
  metadata; the versioned normalized snapshot is authoritative for valuation.
- Existing aggregation is a normalized weighted mean with shared method-family
  budgets. Preserve its arithmetic and explicit user weights. Additional related
  models do not establish independent confirmation.

## Source audit: cached observations, not fresh provider verification

The four raw Company Facts caches were inspected in a read-only PostgreSQL
transaction. No SEC, FMP, Treasury or OpenAI network request was made.

| Company | Cached retrieval UTC | Latest annual duration |
| --- | --- | --- |
| AAPL | 2026-10-15T06:29:26.628752 | 2024-09-29 to 2025-09-27 |
| MSFT | 2026-10-16T05:52:41.999839 | 2025-07-01 to 2026-06-30 |
| NVDA | 2026-10-15T06:30:03.729542 | 2025-01-27 to 2026-01-25 |
| ORCL | 2026-10-15T06:30:17.742780 | 2025-06-01 to 2026-05-31 |

Verified recoverable mapping gaps include stock-based compensation, separately
defined long-term investments versus noncurrent marketable securities, reported
long-term debt aggregates versus gross debt instruments, separate finance and
operating leases and their components, distinct borrowing/repayment scopes, and
individual operating asset/liability cash-flow changes. They require matching
concept definitions, units, duration/instant basis and filing provenance.

Material scope risks were also found. `DebtCurrent` includes capital lease
obligations; commercial paper alone does not prove all short-term borrowing.
Neither may silently establish conventional financial debt. Missing components
are not zero. Lease totals may be reconciled or derived only from complete,
compatible components; they are not automatically debt or added twice.
Reported D&A is not safely reconstructed by blindly adding separate concepts:
NVDA FY2026 aggregate D&A is 2.843 billion USD whereas separately disclosed
depreciation plus intangible amortization sum to 2.888 billion USD. MSFT aggregate
D&A and complete short-term borrowing therefore remain unsupported unless new
compatible source evidence is established.

FMP statement supplements currently serve reconciliation/capability diagnostics;
they do not override SEC observations or turn partial statements into complete
claims. ORCL quote/history restrictions remain restrictions. No verified issuer
extension mapping is established by these Company Facts caches; retain extension
observations without inventing a mapping. Annual and quarterly observations are
distinct. No TTM sum of incompatible/non-additive EPS or share denominators is
justified by these sources.

## Baseline eleven-model eligibility matrix

The retained four-company automatic-evidence fixtures reproduce the following
default results. These are dated fixtures, not current-market expectations.

| Company | Default contributing models | Base USD/share | Basis |
| --- | --- | --- | --- |
| AAPL | Forward P/E | 214.2302568301956 | Policy-based, low confidence |
| MSFT | Forward P/E | 619.5604742486083 | Policy-based, low confidence |
| NVDA | None | Unavailable | Unstable historical P/E target/forecast evidence |
| ORCL | None | Unavailable | Restricted history, share/common-income scope and other missing inputs |

| Model | Required financial/economic basis | Retained four-company blockers | Recoverability |
| --- | --- | --- | --- |
| FCFF DCF | FCFF path or complete operating/reinvestment path; WACC; dated shares; complete enterprise/equity bridge | WACC, operating NWC, preferred/NCI/nonoperating scope; MSFT debt/D&A; ORCL share/forecast scope | Additional mapped fields improve inspection; complete bridge/rates/forecast still missing |
| FCFE DCF | FCFE or complete NI/D&A/capex/NWC/net-borrowing path; cost of equity; dated shares | Complete operating NWC/financing; MSFT/ORCL D&A; ORCL common-income/share basis | Partial cash-flow financing lines cannot establish complete net borrowing |
| Forward P/E | Supported forward EPS and target P/E, or compatible trailing EPS/growth route | AAPL/MSFT policy-based eligible; NVDA unstable historical target; ORCL history/share basis | Preserve defensible historical targets; never relax instability to force an output |
| EV/EBITDA | Forward EBITDA, target multiple, shares, complete enterprise/equity bridge | Target/claims; MSFT debt/D&A; ORCL scope | EBITDA margin is distinct from EBITDA; a complete bridge still required |
| EV/Revenue | Revenue forecast, target multiple, shares, complete bridge | Target/claims; MSFT debt; ORCL scope | Historical price alone cannot establish intrinsic target |
| PEG | Positive compatible EPS/growth and justified target PEG | Target unavailable; ORCL EPS/share scope | No arbitrary sector multiple |
| Graham | Positive common EPS/book and meaningful common book basis | Common-equity/book applicability unconfirmed; ORCL scope | Economic confirmations cannot be inferred from balance-sheet totals |
| Dividend discount | Stable, sustainable per-share dividend or explicit projection; equity discount rate | Stability/per-share basis/projection missing | Aggregate dividends do not establish a future sustainable common distribution |
| Residual income | Meaningful common book, clean surplus, ROE/payout path, equity discount rate | Clean-surplus/common-book suitability; ORCL scope | Retain confirmations and source checks |
| Price/book | Meaningful common book, dated shares, justified target P/B | Book/common scope and target | No market-price-derived circular intrinsic target |
| REIT AFFO | Verified REIT/AFFO economic and per-share basis, justified target | All four are non-REIT/ineligible | Do not enable for coverage statistics |

None of the cached recoverable mappings alone establishes a second economically
independent default model for these issuers. A missing output is preferable to
an invented model input. A higher model count is not an accuracy claim.

## Prioritized implementation matrix

| Priority | Finding | Intended action |
| --- | --- | --- |
| P0 | Scope-ambiguous debt components can look complete | Expose precise reported scopes, quarantine unsupported conventional totals, retain original observations and issue reasons |
| P0 | Supplemental amount observations need not match selected financial period | Require compatible period/source provenance; preserve explicit user inputs |
| P0 | Forecast evidence can end in a different base period | Add exact base alignment guards and regression tests |
| P0 | Sourced WACC capital observations can come from arbitrarily different dates | Add documented compatibility checks without substituting rates |
| P1 | Correct additional SEC fields are retained raw but not normalized | Add verified mappings and narrowly complete derivations; retain full provenance |
| P1 | Confidence uses unused defaults/unsuitable models and ignores adverse factors in its level | Assess actual contributing dependencies; distinguish data quality, coverage and confidence; cap on adverse source/dispersion/terminal conditions |
| P1 | Closest-path blocker lists conceal alternative required inputs | Expose all model input alternatives and precise missing reasons |
| P1 | Aggregation hides range, concentration and related assumptions | Add versioned diagnostics without changing normalized weighted arithmetic |
| P1 | UI drops financial facts and hides completeness/weight rationale | Add authoritative completeness/coverage/provenance presentation, responsive and backward compatible |
| P1 | New metadata must reach AI faithfully | Register exact deterministic outputs and provenance; keep structured aggregates citation-only and numerical eligibility strict |
| P2 | Generic extensions, incomplete NWC/net borrowing/D&A and unsupported ERP | Preserve blockers and document evidence/approval needed; no speculative fallback |

The existing forecast integration's `fill_only` precedence is preserved: a Phase
6 policy migration must not silently replace the historical assumptions that
produced the retained P/E values. Independently computed DCF/bridge benchmarks
will test mathematical paths; small rate/terminal spreads require conspicuous
diagnostics, not arbitrary replacement formulas.

## Implementation contracts and verification plan

Use additive scenario `diagnostics` separating `data_quality`, `coverage` and
`aggregation`, plus a provenance-backed `data_completeness` inventory. The UI
must render server classifications/counts/ranges, preserve user weights, and not
compute independent eligibility/confidence. Family counts are heuristic method
groupings, not proof of economic independence or calibrated probabilities.
Retain old response compatibility.

Version normalization, automatic evidence and valuation eligibility/diagnostic
policies where their interpretation changes. Preserve old cache namespaces and
content-hashed snapshots. Do not mutate historical provider records or create
an additional application database.

All tests use deterministic source excerpts and mocked provider/OpenAI responses.
Run complete backend, dedicated PostgreSQL, frontend unit, production browser,
lint, build and dependency checks, plus four-company before/after matrices and
AI binding/citation regressions. Any fresh SEC/FMP/Treasury audit requires separate
explicit approval. Paid/live OpenAI calls, commits and pushes remain unauthorized.
