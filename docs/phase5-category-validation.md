# Phase 5 category and uncertainty contract repair

Reviewed on 2026-10-16. This repair uses offline tests only. No live OpenAI
request, financial calculation change, commit or push is part of this repair.

Subsequent status: the separately authorized v6 live test passed this category
contract but failed evidence bindings. The later
[typed binding repair](phase5-binding-validation.md) records that retained draft,
prompt v7 and its complete offline verification. The counts below describe the
earlier category repair.

## Root cause and captured evidence

The last explicitly authorized MSFT chat completed at the provider but the
second finding failed `conflicting_ai_category`: `category=interpretation`
with `uncertainty=documented`. The exact captured error was
`An interpretation cannot be presented as a documented fact.` Its cited record
was Fairworth's public `valuation_methodology` description.

The old Pydantic model declared category and uncertainty as independent enums.
Its JSON schema therefore allowed this contradictory pair. A subsequent
evidence validator rejected the pair, while the prompt instructed the model to
use interpretation without explicitly listing its allowed uncertainty values.
Structured output could satisfy the schema and still fail the application.

The small maintained fixture
`backend/tests/fixtures/ai/msft_category_uncertainty_failure.json` preserves the
exact redacted diagnostic, zero-based finding index, question and methodology
evidence. It records the known labels and how the captured validator branch
establishes them. The original finding title, explanation and complete answer
were not retained. They cannot be reconstructed, and synthetic regression
wording is explicitly not presented as captured live output.

## Complete supported combinations

`backend/app/ai/classification.py` is the shared contract for the prompt,
generated JSON schema, Pydantic model and runtime evidence validator.
All unlisted combinations are invalid: eighteen allowed pairs out of thirty-six.

| Category | Allowed uncertainty | Meaning |
| --- | --- | --- |
| `reported_fact` | `documented`, `limited` | Direct sourced observation, with its original dates and coverage |
| `historical_metric` | `documented`, `analytical`, `limited` | Traceable historical observation or deterministic derivation |
| `valuation_output` | `analytical`, `limited` | Deterministic engine output; not a reported financial fact |
| `policy_estimate` | `analytical`, `limited` | Estimate dependent on a disclosed research policy |
| `user_assumption` | `analytical`, `limited` | Explicit user input, not independently established evidence |
| `filing_excerpt` | `documented`, `limited` | Directly supported SEC source content |
| `company_profile` | `documented`, `limited` | Directly supported provider profile content |
| `interpretation` | `analytical`, `limited` | AI inference, conditional scenario or cross-category comparison |
| `unavailable` | `unavailable` | Missing evidence, without a replacement assertion |

`documented` identifies a traceable source observation or derivation. It does
not certify the truth of a valuation or inference. Category labels continue to
identify the evidence basis separately from uncertainty.

The finding schema uses four nested `anyOf` branches, grouping categories that
share the same allowed uncertainty values. The report and chat root schemas
remain objects; finding fields and response shapes remain unchanged. The schema
uses no `oneOf`, discriminator, conditional keywords or unsupported composition.
This follows the [official Structured Outputs schema subset](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
Shared field instructions appear once to preserve room for financial evidence
under the existing input budget.

A Pydantic model validator enforces the same combinations for local/mocked
inputs. The evidence validator independently checks them, including mutated or
constructed objects that bypass Pydantic creation. Safe errors identify the
category, uncertainty, permitted values and failing field without returning raw
model prose. The SDK adapter reports an invalid pair specifically instead of
discarding its identity inside a generic structured-output error.

Prompt version `fairworth-research-6` lists every allowed pair and explains
direct facts, historical metrics, policy estimates, user inputs and AI
interpretations. An explanation of the methodology is explicitly an
interpretation with analytical or limited uncertainty. Changing the prompt
version also invalidates old report cache entries.

## Normalization and independent financial validation

No new automatic category/uncertainty normalization was added. A valid source
ID cannot prove that unknown generated wording is a factual paraphrase, and
the captured original text is unavailable. An unsupported interpretation must
not become a documented fact. Invalid pairs are prevented by the schema and
still rejected if they reach the backend.

The existing narrow normalization remains: an engine `valuation_output`
consuming a checked policy-based quantity is returned as `policy_estimate`
with limited uncertainty. That classification follows the bound source value;
it does not upgrade a claim into a reported fact or change any financial value.

After a pair passes, citation existence, binding scope, finite/exact values,
metric, units, period, derivation, source-category compatibility, privacy and
recommendation rules remain independent checks. Regressions exercise valid
classification together with invalid numerical claims and citations, rather
than using a category correction to skip the financial validators.

## Verification and remaining limitations

Final offline verification passed:

| Check | Result |
| --- | --- |
| Full backend suite, including dedicated PostgreSQL migrations/persistence | 834 passed, no skips |
| New classification regression suite, included above | 101 passed; all 36 category/uncertainty pairs covered |
| Frontend unit tests | 47 passed |
| Production desktop/mobile Chromium browser suite | 100 passed |
| ESLint and fresh production build | Passed |
| Real HTTP transport guard during the full backend suite | Zero attempted requests |
| Four-company full request budgets | Report 62,989–63,414 bytes; chat 61,539–61,964 bytes, within the unchanged 64,000-byte conservative input budget |
| Source/build secret scan and Git index | No new configured secrets; index empty |

Docker was initially stopped, causing the optional PostgreSQL check to time out.
The existing Docker/PostgreSQL service was started; the complete bounded rerun
passed, with database tests confined to the dedicated `fairworth_test` database.
One existing upstream Starlette TestClient/httpx deprecation warning remains.

The existing four-company test fixtures retain their financial values and now
label policy/user estimates with limited uncertainty instead of incorrectly
marking every non-interpretation finding as documented.

Matching labels and citations do not establish semantic entailment for arbitrary
qualitative prose. Human source review and the visible AI interpretation warning
remain necessary. No successful live answer is claimed for this repair; the
last authorized live response failed as described above. A new live test would
require a separate explicit request and authorization.
