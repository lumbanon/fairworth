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
