# Phase 5 typed evidence binding repair

Reviewed 2026-10-16. Prompt version: `fairworth-research-7`.
This repair is offline. No live OpenAI generation, retry, commit or push is part
of it. The deterministic valuation formulas and model eligibility are unchanged.

Subsequent status: the separately authorized v7 live retry exposed missing
per-finding citation declarations for otherwise eligible typed references. The
[citation coverage repair](phase5-citation-coverage.md) describes prompt v8 and
server-owned coverage. The contract and test counts below document the earlier
v7 repair.

## Captured failure and root cause

The retained v6 draft passed structured shape, category/uncertainty, citation
identity and privacy checks, then failed financial binding validation. Its first
title occupied the full 160-character allowance and ended with the incomplete
token `{{date:e_c667a7d34c`. The retained text does not establish whether a model
deliberately shortened that token; the backend must reject it either way.
An old diagnostic mistakenly identified `667`, digits within that malformed ID,
as a numerical assertion. That was not an invented financial amount.

Across the two findings, five complete value references were invalid:

| Source metric | Reason a numeric binding is invalid |
| --- | --- |
| `debt`, `wacc` | Values are null/unavailable |
| `base_model_results`, `confidence` | Values are structured objects |
| `valuation_methodology` | Value is narrative text |

The explanation also asserted `Only one model` without binding that count,
despite referring to the actual count later. A valid numerical assertion
elsewhere does not validate an unbound quantity.

V6 constrained the response shape and classification pairs but left binding
tokens inside arbitrary strings. The model could select unsuitable records and
put a long token inside a short title. The prompt did not provide an explicit,
machine-constrained eligibility catalog. Rejection was correct; making those
assertions pass would weaken validation.

`backend/tests/fixtures/ai/msft_v6_binding_failure.json` preserves the exact
retained response text and its SHA-256, twelve cited public evidence records,
and the independently reviewed failure inventory. It contains no request
headers, configuration, credentials, chat history or manual overrides. Unlike
the earlier partially captured category failure, this draft is complete; no
missing live prose was reconstructed. It remains explicitly failed research.

## Eligibility and generation contract

`backend/app/ai/bindings.py` supplies shared eligibility predicates and
`binding_catalog` before generation:

| Binding kind | Eligible source |
| --- | --- |
| `value` | Available, compatible, finite non-boolean scalar in an allowed financial category and supported unit |
| `date` | Valid observation date/timestamp on an eligible scalar, engine model-name or filing record; never retrieval time |
| `period` | Valid fiscal/form/date period with real calendar dates and ordered date ranges on those same source types |
| `model` | Safe scalar model-name field owned by the Fairworth Python engine |
| `citation_only` | Other records, including unavailable values, descriptions, methodology text and structured aggregates |

A record can support several reference kinds. Citation-only means it supports
no inserted value or metadata; it can still be cited conservatively and inspected
in full. Arbitrary profile/narrative records do not acquire binding eligibility
from inherited reporting-period metadata. Source adapters still control
financial compatibility; explicit unavailable/incompatible metadata cannot be
restored by AI. Zero and negative supported values remain eligible. Dated,
single-model, policy and low-quality warnings remain attached and do not
automatically invalidate their own otherwise supported scalar.

The request-scoped generation model keeps the existing finding fields but
requires `explanation` to be an ordered array of typed parts. For example:

```json
[
  {"kind": "text", "text": "Only "},
  {"kind": "value", "evidence_id": "a_verified_count_id"},
  {"kind": "text", "text": " model contributes."}
]
```

Each reference kind has an enum containing only eligible IDs from that exact
request. Missing groups have no branch; they never produce empty enums.
Citation IDs also use an enum. Shared `$defs` prevent duplication across the
four permitted category/uncertainty alternatives. All objects require every
property and forbid extras. The root stays an object; there are no conditional
schemas, discriminators or `oneOf` branches. This uses the
[official OpenAI Structured Outputs subset](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
The request accepts at most 180 selected records plus the server methodology
record, with bounded ASCII identifiers. Worst-case enum counts and schema bounds
are checked offline.

Titles contain short qualitative prose, without quantities or references.
Text parts forbid braces; the model cannot write a partial or legacy raw token
inside them. `quantitative_claims` must be empty in model output. The server,
rather than the model, constructs exact value/metric/unit/period/derivation
claims from the selected records.

`ResearchService` includes the catalog before generation and checks the actual
combined prompt, task, payload and dynamic schema against the existing input
budget. Older conversation turns and then whole lower-priority evidence records
can be omitted with an explicit limitation. The catalog is rebuilt after every
record omission. Displayed valuation values, contributing count/name, model
eligibility, debt/WACC status and methodology are protected. If essential evidence
cannot fit, generation fails before an SDK request. No financial value,
provenance field, warning, text or identifier is clipped to force a fit.

## Independent validation and rendering

Typed parts are parsed with Pydantic, then converted deterministically into
complete internal references. Those references pass the existing independent
checks before any response is published:

1. Category and uncertainty must form a permitted pair.
2. Every reference must be registered and declared in the finding's citations.
3. Its source must still be eligible for the requested reference kind.
4. Numeric source categories cannot be relabeled as reported facts.
5. All remaining prose, including joined adjacent text parts, is checked for
   unbound digits, Unicode quantities, percentages and common spelled-out numbers.
6. Privacy, unsafe markup/links, recommendations and exact financial metadata
   checks remain active.

Financial shorthand such as `Revenue was 10K` also fails. The lexical exception
for SEC form labels now requires a hyphenated form in an explicit SEC/form
context; it cannot excuse an ordinary financial quantity.

Only after these checks does the backend format values by their original units:
USD values as dollars, fractions as percentages, percent values without another
conversion, multiples as multiples, and counts without rounding into new counts.
Canonical claims retain the exact original numerical precision and source
metadata. Dates display the actual observation day, with the original timestamp
remaining in the evidence reference. Public API findings remain flat strings;
no frontend contract or financial calculation changed. All length limits fail
closed instead of truncating tokens or rendered prose. Malformed-token diagnostics
identify the actual field/fragment rather than digits inside an evidence ID.

The captured engine fair value remains `619.5604742486083` USD/share, displayed
as `$619.56`. The frozen v6 quote is `$539.44`, observed on `2026-10-15`; it is a
later dated quote than the originally reported `$533.69`. The repair does not
change either snapshot or treat a dated quote as current. Low-quality,
policy-based and concentrated-model limitations remain.

## Offline verification and limits

Regressions cover the exact captured title and all five invalid bindings,
unbound `one`, null/boolean/non-finite/structured/text sources, invalid dates and
periods, title/part/render limits, all classification pairs, schema bounds,
context budgets, uncited references and privacy/category failures after valid
typed numbers. The exact question `Why is MSFT's valuation available or
unavailable?` succeeds through a mocked SDK request and full service validation,
with traceable prices, observation date and model count. No invalid answer is
cached or published in rejection tests.

Final offline verification passed:

| Check | Result |
| --- | --- |
| Full backend suite, including dedicated PostgreSQL migration/persistence checks | 1,047 passed, no skips |
| New typed binding / eligibility / budget regressions, included above | 66 / 114 / 32 passed |
| Numerical audit and classification suites, included above | 100 / 101 passed |
| Real HTTP attempts during the full backend run | Zero |
| Frontend unit tests | 47 passed |
| Production browser tests | 100 passed: 50 desktop, 50 mobile |
| ESLint and production build | Passed |
| Python dependency check / Git whitespace check | Passed |

The backend retains one existing upstream Starlette TestClient/httpx deprecation
warning. The test run blocks real HTTP transports and uses only a dedicated
PostgreSQL test database. Frontend and browser tests use deterministic API mocks.
The final source/build audit found no new configured secret material, no changes
to protected financial implementation paths, and no staged files. The branch
and Phase 4.5 parent commit remain unchanged.

This establishes offline contract and regression correctness. It does not prove
that a future live model response will complete or pass; no live request is
authorized for this repair. Unsupported responses remain rejected without a
repair retry. Financial source coverage and semantic limitations on complex
qualitative interpretations remain; citations do not prove semantic entailment.
