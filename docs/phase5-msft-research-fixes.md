# Phase 5 MSFT AI Research review and repairs

Reviewed on 2026-10-15. These repairs do not change financial formulas,
normalization, provider entitlements, model eligibility, or valuation inputs.
No commit or push was made.

## Numerical validation: cause and repair

The original validator rejected every numerical token in prose, including
spelled counts, even when the statement cited the correct financial evidence.
The separate quantitative-claim list could carry an exact number, but the
model had no supported way to include that value, a date, or a fiscal year
inside a readable sentence. The evidence context also lacked a prioritized
scalar contributing-model count and sole-model name.

The original user-observed rejected draft was not retained. Its exact assertion
cannot be recovered from the generic error, and this review does not invent it.
A deterministic MSFT reproduction identifies the precise false-positive:

| Diagnostic | Reproduced value |
| --- | --- |
| Draft | `Only one model contributes to this illustrative estimate.` |
| Rejected span | `one` |
| Rule / error | `unbound_numeric_prose` / `unsupported_ai_number` |
| Relevant evidence | `base_contributing_model_count = 1`, unit `models` |
| Provenance | Existing Python base scenario `summary.count`; only eligible, enabled models with positive effective weight contribute |

The prompt and strict output schema now require cited evidence bindings. The
server validates the complete raw draft, then replaces bindings with values
from the evidence registry. It constructs the corresponding quantitative claims
from exact source metadata. The model does not round or compute the values.

| Binding | Server-owned content |
| --- | --- |
| `{{value:e_id}}` | Finite scalar source value, formatted by its exact unit |
| `{{claim:0}}` | Legacy exact structured claim, independently checked |
| `{{date:e_id}}` | Valid source observation date, never retrieval date |
| `{{period:e_id}}` | Validated fiscal-period/date metadata |
| `{{model:e_id}}` | Trusted engine-owned scalar model name |

Dates, fiscal years and model identifiers therefore have a distinct path from
financial quantities. Form identifiers such as `10-K` are lexical labels. Unknown,
uncited or malformed bindings still fail. Free numerical prose, invented values,
nonfinite values, mismatched units/periods/derivations, and policy values labeled
as reported facts remain rejected. Integer claims retain integer precision;
booleans and numeric strings cannot be coerced into financial claims. A rounded
float cannot match a different exact integer source.

The context now includes and prioritizes the existing engine's
`base_contributing_model_count` and `base_model_name`, along with displayed
fair values, quote timestamps and the Forward P/E inputs. This selects existing
outputs; it does not recalculate a valuation. The exact source values and
provenance remain available beside formatted inline text.

Safe error diagnostics identify the failing field/span, validation rule and
bounded relevant scalar evidence, with secrets and contact details redacted.
They exclude settings, headers, chat history and full prompts. A rejected
binding ID is no longer mistaken for a numerical assertion merely because its
hash contains digits.

## The single bounded live MSFT chat

One live request used the existing configured `gpt-5-mini` model and server key,
the exact question **“Why is MSFT's valuation available or unavailable?”**, empty
history and default assumptions. It was capped at 5,000 output tokens, a
45-second provider timeout and zero automatic retries. No second live request
was made during this repair.

The request returned **HTTP 502, `conflicting_ai_category`, after 21.84 seconds**.
The model used the new bindings, but the category guard rejected the mixed
policy-valuation/factual-context finding. The retained redacted excerpt begins:

```text
Fairworth produced a policy-based base intrinsic value of
{{value:e_08a38cfcbd0ebf8f7e26541857636ba7}} per share using the sole
contributing model {{model:e_1654a4c638231ee03712a91c0eac51a6}} ...
```

The retained diagnostic cites these actual registry entries:

| Metric | Exact value | Basis |
| --- | --- | --- |
| `base_fair_value` | `619.5604742486083 USD/share` | Policy estimate; FY2026, 2025-07-01 to 2026-06-30; existing deterministic weighted engine result |
| `base_model_name` | `Forward P/E` | Engine `effective_weights` selection |
| `base_contributing_model_count` | `1 models` | Engine base `summary.count` |
| `market_price` | `533.69 USD/share` | FMP reported observation, 2026-10-14T20:00:01+00:00 |

The diagnostic at that point did not retain the draft's category or the entire
answer. It cannot establish the exact conflicting token. Its displayed rejected
span `08` was a diagnostic bug caused by digits inside the evidence ID, not an
unsupported financial claim. The subsequent repair identifies the full binding,
source category and finding category for future category failures.

The final guard permits factual quote/count context within a policy finding.
An umbrella `valuation_output` finding containing a bound policy estimate is
deterministically returned as `policy_estimate` with limited uncertainty. The
source records keep their individual classifications. A policy/user/model
quantity still cannot be relabeled as a reported fact. Regressions cover both
mixed policy and umbrella valuation categories, incorrect reported-fact labels,
the exact MSFT question and two related comparison/quality questions.

**The correction passed deterministic mocked tests.** A later, separately
authorized single live request completed but failed a different classification
rule: its second finding combined `interpretation` with `documented`
uncertainty. It used 15,867 input and 2,825 output tokens, including 2,176
reasoning tokens, at a usage-based estimated cost of $0.00961675. That failed
response is not a successful end-to-end verification. The subsequent
[category-contract repair](phase5-category-validation.md) is verified offline
only, preserves the exact partial diagnostic fixture, and makes no further
live request. The original call above did not retain token usage. Ignored local
summaries contain only public, redacted diagnostics.

## Research UI

Historical FY/quarter compatibility notices are collapsed by default and
grouped by issue type, affected periods and fields. The summary reports issue
and original-notice counts. Each group exposes every original diagnostic,
including source metadata, in a nested disclosure. Current material notices,
missing fields, low-quality classification and single-model warnings remain
visible. The data-quality panel uses the same grouping system.

Company descriptions use a word-boundary preview of at most 280 characters,
with an accessible full-description disclosure. Research Insights no longer
duplicates the description or says AI is a later-phase feature. It is labeled
as a static research checklist and links to the actual company AI workspace.
Existing layouts, typography, valuation controls and calculations are preserved.

The real MSFT dashboard check at 1440px and 390px grouped 209 historical engine
notices into nine issue types, with all 209 originals inspectable. The company
preview contained 273 characters versus 2,738 in its expandable full description.
Both widths retained the value and quality warnings, had no horizontal overflow
or runtime exceptions, and showed the configured AI controls ready. All AI POSTs
were blocked during these browser checks; no generation was requested.

## MSFT shares, debt and preserved valuation

The [source audit](phase5-msft-data-audit.md) documents the retained SEC/FMP
evidence and the small deterministic fixture. SEC has a dated filing-cover
share count of **7,425,545,491**, observed 2026-07-23, which the automatic engine
already uses. The quote does not supply verified current-day shares. A rounded
FMP shares-float count references the same July filing; its processing timestamp
does not establish a fresh share observation. Period-end and weighted EPS share
denominators remain distinct.

Current maturities plus noncurrent long-term debt reconcile to **$40.294 billion**
at 2026-06-30. That aggregate includes current maturities already. Missing
FY2026 short-term borrowing coverage prevents it from proving complete total
debt. Older explicit zeros, gross instrument amounts and lease liabilities are
not compatible substitutes. Supplemental FMP statement access remained
restricted in the retained audit. No restriction was bypassed and no missing
amount was inferred as zero.

The default illustrative Forward P/E value remains
**619.5604742486083 USD/share ($619.56)** versus the dated **$533.69** quote.
Only `pe` contributes at effective weight 1, with `policy_based` classification.
Low-quality and single-model warnings remain; filling debt alone would not
resolve all independent model blockers.

## Verification

Standard tests mock external financial providers and OpenAI. Successful mocked
chat responses have traceable cited evidence and exact quantity metadata. They
are not claims of successful live model generation.

| Check | Result |
| --- | --- |
| Full backend suite after the category-contract repair, including dedicated PostgreSQL migration/persistence tests | 834 passed, no skips |
| New numeric validation/audit regressions | 99 cases included in backend suite |
| New deterministic MSFT source audit | 4 cases included in backend suite |
| Category/uncertainty regressions | 101 cases included in backend suite; all 36 pairs covered |
| Frontend unit tests | 47 passed |
| Production Chromium desktop/mobile browser suite | 100 passed |
| Real local MSFT dashboard at 1440px / 390px, generation blocked | Passed, no runtime errors or horizontal overflow |
| ESLint / production build | Passed |
| Bounded live MSFT chat | Failed as described above; final category repair verified offline |

One existing upstream Starlette TestClient/httpx deprecation warning remains.
Complex qualitative entailment is still not proven by a matching citation;
source review and the existing visible interpretation warning remain necessary.
Chromium mobile emulation does not establish physical-device or Safari behavior.
Secrets, full provider caches, screenshots and generated diagnostics remain
ignored local files. The Git index is unchanged; nothing was committed or pushed.
