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
