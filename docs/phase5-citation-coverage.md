# Phase 5 typed-reference citation coverage repair

Reviewed 2026-10-17, Asia/Kuala_Lumpur. Prompt version:
`fairworth-research-8`. Verification is offline; no OpenAI requests, retries,
financial calculation changes, commits or pushes are part of this repair.

## Captured failure and diagnosis

The separately authorized v7 MSFT response completed at
`gpt-5-mini-2025-08-07` for the question
`Why is MSFT's valuation available or unavailable?`. Its structure,
classification pairs, declared citation identities and privacy checks passed.
The complete answer was withheld because the second finding's typed value
references were missing from that finding's separately authored citation list.

The four references selected `total_liabilities` once and `net_income` three
times. All four were registered in the exact frozen request, eligible for value
bindings and present in its request-scoped scalar catalog. These were supported
source values with missing duplicate citation declarations, not unknown IDs,
null debt/WACC values, invented quantities or references taken from another
finding. The original validator correctly rejected incomplete coverage.

The maintained fixture
`backend/tests/fixtures/ai/msft_v7_citation_coverage_failure.json` preserves the
exact retained output text and SHA-256, both findings, all four references and
the relevant public source records. Capture metadata identifies the original
request and its evidence scope. It contains no credentials, configuration,
headers, chat history or manual overrides. No missing live text was invented.

## Citation coverage is server-owned

`canonical_draft` now requires the registry from the exact serialized request.
The SDK adapter freezes that request before awaiting the provider, so caller
mutations cannot add another company's or snapshot's sources during generation.

For each finding independently, canonicalization:

1. Validates the model's additional qualitative citation IDs against the request.
2. Checks each explicitly selected typed reference against the same registry,
   its source identity and its current kind-specific eligibility.
3. Builds a stable, deduplicated union of that finding's additional citations
   and its validated typed references.
4. Rejects empty coverage or more than twelve distinct sources without clipping.
5. Constructs complete internal tokens and a canonical finding for the existing
   independent financial, numerical, category, citation and privacy validators.

Only explicit typed parts derive coverage. The backend never extracts IDs from
ordinary prose, raw binding strings, chat history, another finding or unused
catalog records. It rejects raw tokens in text even when a constructed model
bypasses Pydantic. Unknown IDs, incompatible source identities, unavailable or
non-scalar values, wrong binding kinds and inappropriate numerical source
categories remain invalid. A source may be selected explicitly in several
findings, but each finding receives only its own selected references.

The raw legacy finding validator still requires complete citations. No catch of
`unsupported_ai_binding` was added to repair arbitrary prose after validation.
Literal amounts, percentages, dates and spelled-out counts remain subject to
strict numerical validation. Adding a citation cannot legitimize such prose or
reclassify a policy estimate as a reported fact.

## Structured output and prompt

The public API remains unchanged. In the generation-only schema, `evidence_ids`
now selects **additional qualitative sources** and may be empty when typed
parts provide coverage. Each typed part still requires a source ID selected
from its eligible request-scoped enum. Its source is cited automatically.
This removes the requirement to declare the same selection twice.

The server-owned union makes coverage complete by construction. We do not use
cross-field conditions or enumerate combinations of binding/citation lists.
Objects remain strict, category pairs use nested `anyOf`, and shared enums stay
within the [official OpenAI Structured Outputs limits](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
Schema instructions carry the additional-citation semantics as well as the main
prompt; field descriptions stripped during classification-schema generation
are not the sole source of instructions.

Prompt v8 explains automatic typed-reference citations, request scope and the
twelve-source limit. It also asks for material values with named metrics and
discourages dangling or repeated quantities. The new prompt version invalidates
older report cache keys. No provider retry or automatic regeneration was added.

## Rendering and provenance

The captured first finding retains its five selected sources. The second has
six: its original four additional sources plus the two distinct typed value
sources. Repeated net-income references do not create duplicate source buttons
or quantitative claims. The complete response exposes ten unique evidence
records and five canonical numerical claims across both findings.

Every rendered quantitative value retains its original metric, exact value,
unit, fiscal period, observation date, provider, derivation and source metadata.
Formatting remains server-owned and the evidence capability includes the
derived sources. Frontend citation buttons and source dialogs use that final
canonical list; no runtime UI change is required.

The original text and repeated quantities are not removed, reworded or assigned
new meanings. The existing deterministic fair value, dated market quote,
low-quality warning, policy classification and concentrated-model limitations
remain unchanged.

## Offline verification and limitations

The exact retained response is tested unchanged through request-scoped schema
parsing, canonicalization, financial/prose/category/privacy checks and rendering
with mocked SDK responses. A separate actual FastAPI route regression with the
official SDK over MockTransport returns HTTP 200, two findings, five/six sources
per finding, and three/two exact numerical claims. Real HTTP transports are
blocked during backend verification.

Negative tests cover unknown and out-of-scope IDs, changing source eligibility,
raw token strings, ordinary numerical claims, cross-finding borrowing,
inappropriate categories, private output, caller mutation, duplicate sources and
the final source-count limit. Browser regressions check matching quantity/source
dialogs and retain unavailable debt as null. The captured response is also
replayed in the real production UI on desktop/mobile without provider traffic.

Final offline checks passed:

| Check | Result |
| --- | --- |
| Full backend suite, including dedicated PostgreSQL migration/persistence checks | 1,090 passed, no skips |
| New citation-coverage regression suite, included above | 44 passed |
| Real HTTP attempts during backend verification | Zero |
| Frontend unit tests | 47 passed |
| Full production browser suite | 102 passed: 51 desktop, 51 mobile |
| Captured-response production UI replay | Both viewports passed; all ten source dialogs checked |
| ESLint / production build / Python dependency check | Passed |
| Git whitespace and configured-secret audit | Passed; no new configured secrets detected |

One existing upstream Starlette TestClient/httpx deprecation warning remains.
The final audit found no changes to protected financial implementation paths,
no staged files, and the same Phase 4.5 parent commit. Historical live-test guards
and diagnostics remain intact; new verification artifacts are ignored locally.
See the main [Phase 5 implementation report](phase5-ai-research.md) for setup.

Citation coverage does not prove semantic relevance. In particular, the capture
appends repeated net-income values without useful surrounding labels. They are
traceable source facts, but the prose remains awkward. This repair does not
rewrite that historical response or claim comprehensive semantic entailment.
The new prompt's future live behavior has not been tested; no live request is
authorized for this repair. Future unsupported responses must still fail closed.
