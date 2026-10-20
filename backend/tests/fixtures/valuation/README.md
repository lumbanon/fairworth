# Verified provider excerpts

`verified_provider_excerpts.json` contains exact financial observations from the
Phase 3 SEC/FMP verification for AAPL, MSFT, NVDA, and ORCL. It is a maintained,
deterministic test fixture, not a downloaded provider cache. Financial amounts
retain absolute reporting units and source accession numbers, filing dates,
concepts, observation periods, and derivation coefficients.

The excerpt includes each company's six latest normalized annual periods. It
reduces duplicate equivalent observations to one original record per derivation
component, and excludes warnings about omitted older financial history. It
retains selected-period warnings, source references, verified quote timestamps,
and all known missing inputs. No synthetic financial or market values are added.

In particular, FMP current shares remain unavailable; MSFT complete debt and
mapped D&A remain missing; ORCL has no authorized quote, negative latest free
cash flow, and unverified per-share/class and common-earnings bases. These facts
must not be patched to obtain a valuation number. Synthetic examples in Python
unit tests are separately identified and are not represented as provider data.

## Phase 4.5 automatic evidence

`automatic_evidence_excerpts.json` is a separate deterministic excerpt of actual
permitted SEC, FMP and US Treasury observations verified on 2026-10-14. The older
Phase 4 fixture is unchanged. This excerpt retains eight original annual filing
vintages per company, with EPS, diluted shares, revenue and net income. The last
three native vintages also retain operating income, D&A, capex and bridge fields
needed to reproduce the normalized forecast estimates. Original filing accession
numbers and publication dates are retained; later comparative EPS restatements
are deliberately excluded from these historical vintages.

Only the first available trading close strictly after each retained annual
publication (within seven calendar days) is included. There are five such closes
each for AAPL, MSFT and NVDA, and none for ORCL. These are dated, split-adjusted
FMP price observations, not a bulk daily-price dataset. Full returned split-event
lists preserve the factors required to put original EPS on the price basis. For
example, native NVIDIA FY2023 EPS is $1.74; its later ten-for-one split is handled
explicitly instead of mixing that EPS with today's split-adjusted prices.

Additional observations distinguish filing-cover common shares, annual period-end
shares and weighted-average shares. Provider share-float processing dates do not
replace the underlying SEC share observation dates. Treasury observations retain
their published dates and the ten-year par-yield convention. FMP beta remains a
provider estimate with an unpublished methodology warning. ERP is unavailable
unless a complete dated research-policy configuration is supplied.

Truthful gaps remain: complete Microsoft debt and aggregate D&A are unknown;
its separate depreciation/amortization fields are not automatically summed.
NVIDIA's explicit zero *nonredeemable* preferred-stock value does not establish
that every other preferred or nonoperating claim is zero. Oracle's preferred
stock stated value is a nominal reported amount rather than a complete market
claim valuation. ORCL's quote/history/splits remain restricted, and its quoted
share-class compatibility remains unverified. No provider key, contact details,
request query strings, synthetic quotes or user assumptions are retained.

## Phase 6.7 complete-scope boundary example

`phase67_scoped_forecast_history.json` is explicitly **synthetic**. It demonstrates
three annual pairs of complete noncash operating balances and complete debt cash
flows, with dated original-observation metadata and explicit economic scope.
It is not a retained SEC response and does not establish real financial coverage.

Positive contract tests install a separately labeled synthetic concept mapping
with `monkeypatch`. The production reviewed concept/scope allowlist is empty and
cannot be supplied through configuration or a provider response. Scope annotations
alone cannot admit any real financial evidence. Future real admission requires an
economically reviewed mapping in source code and an exact, unambiguous match to
the original concept, unit, value, period, accession and filing in the raw SEC
snapshot.

The automatic-input boundary also requires exact issuer ownership, annual filing
and period alignment, compatible units, complete scope on each original
observation, and an explicit verified-zero state for a zero amount. It never substitutes
accounts receivable/inventory/payables for exhaustive operating working capital,
long-term-only debt proceeds for complete debt issuance, or debt-balance changes
for financing cash flows. The current SEC adapter does not independently establish
these complete scopes; the real retained company fixtures therefore stay blocked.

## Phase 6.7 approved SEC financial excerpts

`phase67_sec_financial_excerpts_2026_10_20.json` contains 886 exact original
observations selected from eight separately authorized SEC companyfacts responses
acquired on 20 October 2026. The 464,114-byte fixture retains original source
URLs, full-response SHA-256 hashes, byte sizes, retrieval clocks, CIKs, concepts,
units, accessions and filing contexts. No keys, identifying User-Agent or personal
contact details are included. Full responses remain in ignored local storage.

Revenue, income, diluted common income, EPS and weighted shares span four annual
intervals; other mapped fields cover only the latest annual interval. All original
native/comparative candidates within that selection remain present, including
conflicting debt observations. Missing older fields in this excerpt are deliberate
omissions, not evidence that the issuer did not report them. The full-source
coverage audit and this smaller reproducible excerpt have distinct denominators.

Oracle and JPMorgan explicitly report diluted income available to common
stockholders. That amount verifies their reported EPS numerator independently of
consolidated net income; it does not establish quoted-class or split compatibility
and does not replace the consolidated income consumed by existing FCFE inputs.
Current listing/issuer proofs, quotes, split histories, complete enterprise bridges,
operating working capital and AFFO are not supplied by this financial acquisition.

The offline `replay_financial_model_coverage.py --approved-excerpts` command uses
these eight issuer documents for nine separately gated securities (GOOG and
GOOGL share an issuer). It preserves the expired listing-proof clocks and publishes
no default estimate. Synthetic scope-contract tests remain a separate fixture.
