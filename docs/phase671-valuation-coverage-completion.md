# Phase 6.7.1 — Financial scope, evidence clocks and valuation coverage

Audit date: 21 October 2026. The implemented engineering changes and offline
verification are complete. **The central real-data valuation coverage objective
remains blocked.**
Engineering safeguards and evidence visibility must not be described as new
financially defensible price targets.

## 1. Executive summary

Normalization 6 retains conflicting debt candidates and refuses to select an
unresolved total, including through legacy/API or supplemental observation
paths. Restricted cash and debt costs retain explicit scopes. Independent
listing and issuer expiry is now visible. Scenario results distinguish current,
historical and unavailable publication, independently of the numerical engine.
Dependence disclosures distinguish models, method families and shared evidence.

The approved bounded acquisition used eight requests and stopped on FMP HTTP
402. It refreshed directory evidence in an isolated replay and obtained four
quote observations, but no quote currency, profile, split or historical-price
refresh. It did not produce additional current estimates. All eleven equations,
aggregation weights and original AAPL/MSFT historical values are preserved.

## 2. Starting branch and commit

- Branch: `feature/phase-6-7-1-valuation-coverage-completion`.
- Starting HEAD: `79a0fce95310718f6c55fc75b7368ecb24bf405d`.
- Included Phase 6.7: `b7753f6`, through the existing merge.
- Initial working tree/index: clean. No branch operation, commit, push or
  deployment was performed. All current implementation changes remain local.

## 3. Previous Phase 6.7 baseline

The read-only local inventory confirms 17,060 instruments/listings, 23,710
immutable listing observations, 14,637 issuer reference rows, five company rows,
165,486 financial facts, nine financial snapshots, fourteen market snapshots and
64 cache entries. These are database inventories, not financial eligibility
counts. The historical directory audit reported 13,248 active observations and
6,661 recorded verified identities, dated 19 October; neither is current by
virtue of this report's date.

The retained thirty-security sample contains five financial issuers, three
historically compatible share/currency bases and two Forward P/E illustrations:
AAPL `214.2302568301956`, MSFT `619.5604742486083`. Each has one contributing
model and no independent corroboration. The separately acquired eight-issuer,
nine-security sample has zero default outputs. GOOG and GOOGL remain distinct.

## 4. Root-cause blocker matrix

`backend/scripts/replay_phase671_valuation_coverage.py` produces JSON and
Markdown for **330 retained security/model pairs** and **99 acquired pairs**.
It includes exact fixture registry IDs (explicitly not production IDs), CIK,
symbol/form/business/framework, all alternative input paths, available/missing
and incompatible fields, assumptions and provenance, provider restrictions,
publication clocks/blockers, financial compatibility, economic applicability,
contracts, recomputed values and original historical regressions.

The frozen before matrices are ignored local artifacts, generated before code
changes at `2026-10-20T15:25:12Z`. The after audit uses an explicit later clock;
source dates are never advanced. Ranking excludes economically inapplicable
models and records affected pairs/companies, materiality, retained resolution,
permissions and complexity. Counts indicate conditional blockers, not promised
coverage gains. Highest priority corrections were reference/quote proof,
scope-conflict quarantine and complete input provenance. Common remaining
blockers are missing compatible quotes, common-equity/share scope, complete
enterprise claims, discount rates and supported historical multiples.

Example offline replay (from repository root; development/test dependencies
required):

```powershell
backend/.venv/Scripts/python.exe backend/scripts/replay_phase671_valuation_coverage.py --population retained --as-of 2026-10-20T15:25:12Z --output .phase671.local/after-retained.json --markdown .phase671.local/after-retained.md
backend/.venv/Scripts/python.exe backend/scripts/replay_phase671_valuation_coverage.py --population approved --as-of 2026-10-20T15:25:12Z --output .phase671.local/after-approved.json --markdown .phase671.local/after-approved.md
```

Create the ignored output directory first. Optional `--compare` checks exact
population, evidence mode, source clock, unique model pairs and denominators.
An optional already acquired `--updated-evidence` manifest requires
`--authorization-receipt`; it cannot fetch data or grant user consent. HTTP
transports are blocked during replay. Maintained fixtures replay on another
machine; ignored acquisitions are deliberately optional and not redistributed.

## 5. Financial concept and scope review

The original acquired eight sources contain 129 annual and 531 quarterly
periods; the retained five sources contain 85 annual and 350 quarterly periods.
The maintained Phase 6.7 excerpt contains selected original observations, not
every concept in those full documents. No absence in an excerpt is treated as
proof of absence in a filing.

The new 30,038-byte deterministic scope excerpt preserves actual source
observations and acquisition hashes. New disclosure-only metrics distinguish
combined cash, restricted current/noncurrent cash, restricted cash/investments
and signed debt discount/premium/issuance costs. They are not aliases for
unrestricted cash or complete debt. Common diluted income remains non-additive;
no invalid quarterly YTD subtraction, D&A alias or EPS/share assumption is added.

## 6. Debt and enterprise reconciliation

The candidate graph distinguishes reported total debt, short plus long-term
debt, short plus current/noncurrent debt, and long-term subtotals. Exact source
concept, accession, unit, period, form, amount and compatible filing context are
checked. Overlapping leases, commercial paper, gross instruments and issuance
costs remain separate. Both reported and derived candidates survive conflicts.

- AMZN long-term candidates differ by **$440 million**.
- GOOGL long-term candidates differ by **$542 million**. A numerically matching
  signed issuance-cost disclosure does not prove an accounting reconciliation.
- MSFT current/noncurrent debt and NVDA components do not independently establish
  every short-term borrowing and senior claim.
- ORCL/PGR supported reported debt remains unchanged. Insurer reserves are not
  industrial debt and do not make industrial EV methods appropriate.

Unresolved comparisons quarantine effective debt. Legacy source-backed totals
cannot escape this by omitting period currency or by supplying another copy of
one candidate. Dataset currency is validated consistently, including API round
trips. Restricted cash is not substituted for bridge cash; missing preferred,
noncontrolling and other senior claims are not assumed zero.

Read-only full-source normalization 5→6 comparison preserves all periods.
Exactly five old MSFT debt values (one annual, four quarterly, 2014–2015) change
to unavailable because of unresolved candidates; all other pre-existing metric
values are unchanged. The new scoped fields add 355 non-null observations in
the retained five sources and 610 in the acquired eight. These are overlapping
populations and must not be summed.

## 7. Working-capital and financing-flow mappings

The production `REVIEWED_FORECAST_SCOPE_CONCEPTS` allowlist remains empty. No
generic current-assets-minus-current-liabilities proxy is admitted. Complete
operating receivables/inventory/payables/accruals/deferred revenue and other
operating components remain necessary, with overlap and cash/financing
exclusions. Balance-sheet debt changes are not net borrowing.

The retained source review found incomplete or mismatched debt issuance and
repayment intervals (including NVDA's older issuance series, PGR's incomplete
repayment history and GOOGL's debt/lease mix). A reported zero repayment does
not establish zero issuance. No financing or NWC contract was defensibly added.
Original linked filing/note inspection is recommended before proposing any
issuer-specific contract; those fresh documents were not authorized here.

## 8. Share/common-equity reconciliation

Weighted-average diluted shares remain separate from point-in-time common
shares. Direct diluted-common earnings support native EPS reconciliation only;
they do not prove common-equity valuation, split adjustment or class rights.
Consolidated GAAP equity is not automatically common equity. GOOG/GOOGL values
are not transferred. BRK.B/BRK-B aliases require exact symbol/venue/ownership
proof. ADR/foreign-share conversion and FX remain unavailable without evidence.

## 9. Listing/quote freshness design

`verification_state` and `proof_expiry` expose independent listing and SEC issuer
proof, original source, observation/publication/retrieval clock, fixed expiry and
existing TTL. The one-day reference policy is unchanged, including its existing
source-date anchoring. Quote observation remains distinct from retrieval and
calculation; existing two-day compatible quote policy is unchanged. Neither
financial acquisition nor a fresh quote renews issuer or exchange proof.

Publication also requires independently supported financial observation
currentness and finite source-cache validity. A newly fetched old filing cannot
be labeled current merely because the cache is fresh. Absent a code-reviewed,
source-backed currentness contract, the estimate remains historical. No new
universal reporting-age TTL is invented. Mocked positive current-publication
tests are capability checks, not real sample coverage.

## 10. Per-model eligibility improvements

The machine-readable matrix documents every exact complete alternative from
the existing engine. No eligibility check is bypassed or equation changed.

| Model | Required scope / assumptions still enforced |
| --- | --- |
| FCFF | Complete operating cash flows, supported WACC/growth/reinvestment and non-overlapping EV bridge |
| FCFE | Common-equity cash flows, complete financing, cost of equity; no second debt deduction |
| Forward P/E | Compatible positive common EPS, supported forward path and target multiple |
| EV/EBITDA | Company-wide EBITDA, permitted multiple, compatible shares and complete claims |
| EV/Revenue | Suitable industrial revenue forecast, multiple and complete EV bridge |
| PEG | Supported common EPS, economically valid growth and permitted target PEG |
| Graham | Positive applicable earnings and meaningful common book equity |
| DDM | Supported sustainable per-share dividends, growth and cost of equity |
| Residual income | Common book, clean-surplus-compatible ROE/payout and discount assumptions |
| P/B | Meaningful common book/share basis and supported suitable target P/B |
| REIT AFFO | Auditable issuer-specific complete AFFO, forecast, shares and multiple |

Automatic own-history multiples continue to need at least three qualifying
distinct fiscal years, with filing-publication and split alignment. Automatic
three-year growth needs four compatible annual endpoints. Explicit paths have
their own model requirements and are never assigned a universal history count.
CAPM still needs dated risk-free yield, beta and explicit ERP policy; WACC still
needs supported debt costs and capital weights. No universal rate/multiple is
introduced. Evidence classifications remain reported, derived, historical,
policy, user or unavailable with exact provenance.

## 11. Sector-specific coverage

AAPL/MSFT retain historical P/E only. NVDA/ORCL remain blocked by existing input,
growth/multiple or selected-share evidence. AMZN's financial excerpt is acquired
evidence, not part of the original thirty's five retained financial issuers.
JPM/BAC need supported common-equity/share and applicable assumptions; bank
enterprise methods remain excluded. PGR needs insurer-appropriate evidence and
entitled market data; its failed quote is not replaced. O/PLD need original
FFO/AFFO definitions. META and other sample securities without maintained
financial evidence remain unavailable. BABA/TSM/NVO retain foreign/ADR gates.
SPY and AGNCN remain exclusion controls. Exact per-security/model reasons are in
the separate matrices, not inferred from ticker suffixes.

## 12. Model independence methodology

`evidence-dependence-1` reports active positive-weight model count, distinct
method families, shared observed inputs, shared assumptions and exact source
records (concept/accession/unit/start/end). Recursive dependencies disclose
shared EPS/growth and other common drivers. A user override does not inherit
unused original-filing provenance. Lack of detected overlap does not establish
independent corroboration. No weights or confidence formulas change; neither
real sample establishes two independent families.

## 13. Authorized requests

The user approved [the exact bounded proposal](phase671-acquisition-proposal.md)
in this conversation. The one-time run on 21 October made **8 of at most 20
GETs**, **1,417,683 bytes**, concurrency one, at least one second apart,
30-second total timeout each, no redirects and zero retries.

| Result | Requests | Bytes |
| --- | ---: | ---: |
| Nasdaq listed directory, HTTP 200 | 1 | 348,727 |
| Other-listed directory, HTTP 200 | 1 | 543,094 |
| SEC ticker/exchange directory, HTTP 200 | 1 | 523,851 |
| AAPL/MSFT/NVDA/AMZN quote, HTTP 200 | 4 | 1,796 |
| PGR quote, HTTP 402 | 1 | 215 |

Nasdaq parser accepted 5,609 + 7,642 records; SEC yielded 10,443 references.
These inventory counts are not combined with sampled financial denominators.
FMP stopped immediately on PGR's entitlement denial. No profile, split or
historical-price request followed; no SEC facts, Treasury or OpenAI call was
made. The four quotes omit currency, and no acquired profile can supply it.
Their dated prices are retained but do not become compatible current quotes.
No original eight-request Phase 6.7 authorization was reused.

## 14. Real versus retained versus mocked evidence

The original thirty use maintained `retained_public` fixtures. The eight-issuer
financial excerpt is separately labeled `newly_approved_live` from the preceding
Phase 6.7 acquisition. Phase 6.7.1 updated-reference/quote evidence is labeled
separately under `additional_evidence`; it never changes financial-source dates.
Mocked complete-model, currentness and independence tests are not counted as
real-data coverage. The small maintained scope fixture is original public SEC
evidence; raw full sources, FMP responses and verification reports stay ignored.

## 15. Database and cache safety results

All updated source integration uses disposable in-memory SQLite. No production
financial, registry or cache imports are performed. No schema migration is
needed; additive response/evidence metadata uses existing JSON boundaries.
Normalization/completeness/coverage interpretation versions isolate old results.
AI scoped identity includes bounded proof metadata; proof details remain
citation-only. Typed bindings, numerical/category/citation/privacy validation
and financial formulas remain unchanged.

Final read-only comparison confirms identical row counts and SHA-256 hashes for
all five application tables: companies, financial facts, financial snapshots,
market snapshots and cache entries. Registry counts are also identical. The
existing development database and
Docker volume are preserved; tests use the distinct guarded `fairworth_test`
database. Existing Docker was restarted to restore that local service, without
recreating or resetting it. Environment files and credentials were not edited.

## 16. Frontend improvements

Existing dashboard disclosure styles now show independently expired listing
and ownership proof, exact source clocks, scenario-specific result type,
contributing family/dependency information and debt conflicts with candidate
provenance. Legacy payloads are not inferred current; failed requests cannot
retain a stale current label. No JavaScript financial calculations, design
changes, font/layout changes or new dependencies are introduced. Desktop and
mobile disclosures preserve accessibility.

## 17. Automated test counts

- Frontend units: **87 passed**.
- Browser: **170 passed**, 85 desktop and 85 mobile, no skips.
- ESLint, Vite production build, frontend dependency tree: passed.
- Python dependency check: passed.
- Backend final HTTP-blocked suite: **1,868 passed**, zero failures or skips,
  including all three populated PostgreSQL migration/persistence/rollback
  acceptance tests. **Zero external HTTP attempts.**
- Final replay/independence focused checks: **18 passed** after the audit-field
  refinements; original AAPL/MSFT regressions remain exact.
- Diff whitespace and configured-secret checks: passed; **zero staged bytes**
  and no sensitive/generated paths among the intended changes.

The first full backend run had 1,800 passes and three local PostgreSQL connection
failures because Docker was stopped. Restarting the existing service restored
all three PostgreSQL checks. The final full repeat includes the added adversarial
review regressions and replay/manifest tests. No test is silently skipped.
Existing nonfatal warnings remain: Starlette's httpx TestClient deprecation and
Vite's entry-chunk size advisory (505.13 kB).

## 18. Before/after security/model coverage

The frozen baseline current clock is 20 October 15:25:12 UTC; historical source
replays keep their original 19/20 October clocks. Updated evidence is assessed
at **2026-10-21T08:00:12Z**. Denominators remain separate. The matrix distinguishes
recomputed engine eligibility from full current eligibility/publication; a dated
model calculation is not counted as a current eligible security.

| Measure | Retained 30 | Acquired 9 (8 issuers) |
| --- | ---: | ---: |
| Security/model pairs | 330 | 99 |
| Original historical default securities | 2 | 0 |
| Baseline current engine-eligible securities | 0 | 0 |
| Current reference-verified issuer identities after update | 27 | 9 |
| Current source-backed active listing observations after update | 30 | 9 |
| Securities with statement evidence | 5 | 9 |
| Sufficient historical growth window inventory | 4 | 9 |
| Complete compatible fresh quote | 0 | 0 |
| Recomputed default model securities after reference update | 2 historical | 0 |
| Fully current eligible securities | 0 | 0 |
| Current published default securities | 0 | 0 |
| Established independent multi-family valuations | 0 | 0 |

Restoring reference proof lets the original two dated calculations run again;
this is not an additional eligible security. Their exact historical regression
values remain unchanged. No new real-data model or current result is claimed.
Financial data available, financially compatible and eligible are independent
states, and missing numerical assumptions do not redefine fact compatibility.

## 19. Financial accuracy and licensing limitations

The five-to-ten eligible-security and three-independent-family provisional
targets are **not achieved**. Financial/currentness scope, compatible quote and
share metadata, entitlement and supported forecast/discount assumptions remain
blocking. A functioning model in a mocked test is not actual financial coverage.
Neither sample measures market-wide financial performance. SEC public reference
access and Nasdaq/FMP display/redistribution rights remain separate; local audit
authorization does not establish launch rights. No provider dataset is deployed.

## 20. Remaining blockers and recommended next work

1. Confirm FMP endpoint entitlement outside this audit; do not automatically
   retry PGR or previously restricted statements/splits. Request a new exact
   authorization only for the minimum now-permitted metadata needed.
2. Review original linked annual-filing disclosures for the AMZN/GOOGL debt
   discrepancies, MSFT/NVDA borrowing/claims and complete working capital and
   financing scope. No fresh filing fetch is authorized by this report.
3. Establish a reviewed source-backed financial currentness policy/contract,
   retaining original period/filing, source assessment and finite cache expiry.
4. Review issuer-specific common-equity, split/class and forecast contracts;
   keep generic production scope mappings empty until evidence warrants them.
5. Any production import of acquired Phase 6.7 financial sources requires its
   own reviewed import/migration plan and explicit approval. No import occurred.

The implemented safeguards and audit workflow improve trust and diagnosis.
The main additional real-data valuation coverage objective **remains blocked**;
no extra price targets were generated to make the results look more complete.

Final repository state: original branch and HEAD are unchanged; all intended
source, test, fixture and documentation edits remain unstaged/uncommitted.
Environment files, provider keys, `.phase671.local/`, `.phase67.local/`, raw
responses, database contents, dependencies and generated reports remain ignored.
No commit, push, merge, deployment or next phase was started.
