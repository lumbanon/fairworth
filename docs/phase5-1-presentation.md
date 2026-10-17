# Phase 5.1: AI Research presentation and narrative polish

Implemented October 17, 2026 (Asia/Kuala_Lumpur). Active prompt version:
`fairworth-research-9`. No live OpenAI or financial-provider request was made
for this phase. Financial formulas, input selection and model eligibility are
unchanged.

## Typed segment rendering

`bindings.py` joins already checked typed parts with missing word/sentence-boundary
spaces. Examples from the actual retained v8 response now read `value $619.56 and`,
`price $539.44. Only` and `Forward P/E. Many`. Tokens remain atomic; no identifier,
financial value, prose word, category, uncertainty or citation is replaced. Existing
spacing, parentheses, quotation punctuation, slashes and intentional text fragments
are preserved. The public length checks still fail closed rather than truncating.

The canonical draft still undergoes the original independent category, reference,
citation, financial, numerical and privacy validation before source-owned values
are rendered. Spacing does not create an exemption for numeric free text or make
ineligible/unavailable evidence usable.

## Financial figures and source dates

Financial figures are in a native expandable disclosure. Its cards use readable
metric labels, display-only currency/percentage/multiple/count formatting and rounded
values. Very small nonzero values retain significant digits instead of displaying
as zero. The source record and quantitative claim remain exact, including
`619.5604742486083 USD/share`; neither validation nor calculations consume a
formatted string. Each citation still opens its complete original value, units,
fiscal period, source date, retrieval timestamp, provider and derivation.

A cited market-price claim has a visible price/observation row. The retained capture
shows `$539.44 / share · Observed Oct 15, 2026`. This comes exclusively from the quote
record's `observation_date`, not `retrieved_at`, the generation timestamp or the
browser timezone. An absent/invalid observation date is explicitly unavailable.

## Readability and relevance

Finding separators, restrained line lengths and source labels improve scanning
within the existing financial dashboard design. Key policy, single-model and dated
observation caveats remain visible. All source/data notices remain accessible in
an expandable list, including historical diagnostics and source-coverage gaps.

Prompt v9 asks for directly relevant, concise findings; avoids repeating financial
figures; and limits hypothetical-editor guidance to questions about changing
assumptions. It requires model-specific missing-input terminology and explicitly
distinguishes EBITDA margin from EBITDA and debt from liabilities. The version
bump also changes report cache keys, avoiding reuse of earlier presentation output.

The original v8 wording is not retrospectively rewritten. For its broad phrase
`EBITDA/EBITDA margin`, a source-owned UI clarification appears only when that finding
cites an engine eligibility record explicitly listing `ebitda_margin` as missing
and not listing `ebitda`, with the engine provider and valuation-output classification.
The clarification identifies the actual model and precise
input. It is omitted if matching evidence is absent; no data is inferred.

## Exact capture and offline verification

`backend/tests/fixtures/ai/msft_v8_success.json` retains the exact successful
authorized provider output (SHA-256
`e5ede61fd4602197a661e0adfd9258f3b7acc05108159552a5a0402c262c2a79`),
its seven cited public records, original request-scoped IDs/catalog, original
published findings and expected whitespace-only presentation. It contains no API
key, personal data, session capability, history or manual override. Its observed
financial values are historical test data, not current-market expectations.

The backend regression sends that unchanged provider text through the actual
SDK parser with `MockTransport`, the strict service and FastAPI route. HTTP 200
retains two findings, three exact numerical claims, seven sources and matching
source endpoints. Assertions compare original wording with whitespace removed,
and exact equality of all financial values, units, periods, derivations,
classifications and citation IDs. Real HTTP is blocked in these regressions.

Browser tests replay the backend-verified result on desktop/mobile, inspect all
citations, and compare rounded cards with exact source dialogs. Tests cover the
observation/retrieval distinction, missing observation dates, collapsible notices,
terminology clarification and preserved low-quality/single-model warnings.
A separate network-isolated production replay of the actual FastAPI result also
checked all seven source dialogs per viewport at 1440px and 390px: 14px prose,
no runtime errors and no horizontal overflow. Background dashboard data is explicitly
a deterministic fixture; no new backend generation is triggered by UI verification.

Validation results:

| Check | Result |
| --- | --- |
| Complete backend suite | 1,103 passed; PostgreSQL initially timed out because the existing container was stopped |
| PostgreSQL plus final captured-response regressions after container restart | 15 passed; all 1,104 backend cases passed across these runs |
| Real provider/OpenAI HTTP attempts in guarded backend verification | 0 |
| Frontend unit tests | 51 passed |
| Full production desktop/mobile browser suite | 106 passed |
| Focused research desktop/mobile checks after final terminology-source guard | 30 passed |
| ESLint and production build | Passed |

The existing upstream Starlette TestClient/httpx deprecation warning remains.
The existing PostgreSQL container was restarted without deleting or replacing its
volume; migration/persistence checks used only the dedicated `_test` database.

Run `python -m pytest backend/tests -q`, `npm run test:unit`, `npm run test:e2e`,
`npm run lint` and `npm run build`. The PostgreSQL case needs the existing dedicated
empty `*_test` database as described in README. No OpenAI credentials are needed
for the deterministic/mocked tests.

## Remaining limits

The old capture intentionally retains its methodology/hypothetical-editor paragraph
so the regression proves wording preservation; new prompt behavior has only been
checked offline. Prompt instructions cannot establish semantic correctness or
guarantee future model concision. Human source review remains necessary. Existing
dated-snapshot, policy-only/single-model and SEC passage-coverage limitations remain.
Physical mobile devices and Safari were not tested. No commit or push was made.
