"""Financial research numbers remain exact evidence, with server-owned display.

The MSFT examples retain deterministic Phase 4.5 outputs. No provider or model
call is made, and these examples do not imply that the dated quote is current.
"""
from copy import deepcopy
import json
import math

import pytest

from app.ai.schemas import ChatDraft, ChatRequest, Finding, QuantitativeClaim
from app.ai.validation import render_finding, validate_findings, validation_diagnostic
from app.core.exceptions import ApiError


def evidence(identifier="e_fair", **changes):
    item = {
        "id": identifier,
        "category": "policy_estimate",
        "provider": "Fairworth Python valuation engine",
        "title": "Base illustrative Forward P/E fair value",
        "ticker": "MSFT",
        "metric": "base_fair_value",
        "value": 619.5604742486083,
        "unit": "USD/share",
        "period": "FY2026; 2025-07-01 to 2026-06-30",
        "observation_date": "2026-07-29",
        "retrieved_at": "2026-10-15T00:00:00Z",
        "source_url": None,
        "accession": None,
        "derivation": "Deterministic weighted estimate from eligible enabled models; not an AI calculation.",
        "quality_warnings": ["Illustrative policy-based estimate; only a single model contributes."],
        "excerpt": None,
    }
    return {**item, **changes}


def registry():
    items = [
        evidence(),
        evidence("e_price", category="reported_fact", provider="permitted market provider",
                 title="Dated comparison market price", metric="market_price", value=533.69,
                 observation_date="2026-10-14T20:00:01Z", period=None, derivation=None),
        evidence("e_count", category="valuation_output", title="Contributing model count",
                 metric="base_contributing_model_count", value=1, unit="models",
                 derivation="Count of base models with a positive effective weight in the Python engine summary."),
        evidence("e_model", category="valuation_output", title="Contributing valuation method",
                 metric="pe_model_name", value="Forward P/E", unit="text",
                 derivation="Contributing valuation method name from the Python engine model registry."),
    ]
    return {item["id"]: item for item in items}


def claim(item):
    return QuantitativeClaim(**{key: item[key] for key in ("metric", "value", "unit", "period", "derivation")},
                             evidence_id=item["id"])


def finding(**changes):
    return Finding(**{
        "title": "Why the illustrative valuation is available",
        "explanation": "An illustrative valuation is available, with low valuation quality and no independent model confirmation.",
        "evidence_ids": ["e_fair"],
        "category": "interpretation",
        "uncertainty": "limited",
        "quantitative_claims": [],
        **changes,
    })


def test_msft_availability_answer_renders_exact_engine_price_count_and_dated_quote():
    items = registry()
    candidate = finding(
        explanation="The illustrative {{model:e_model}} estimate is {{claim:0}}, versus a dated market price of {{claim:1}} observed on {{date:e_price}}. Only {{claim:2}} model contributes; low quality and missing independent confirmation remain limitations.",
        evidence_ids=list(items),
        quantitative_claims=[claim(items[key]) for key in ("e_fair", "e_price", "e_count")],
    )
    original, original_items = candidate.model_dump(), deepcopy(items)
    assert validate_findings([candidate], items) == sorted(items)
    rendered = render_finding(candidate, items)
    assert "Forward P/E estimate is $619.56" in rendered["explanation"]
    assert "$533.69 observed on 2026-10-14" in rendered["explanation"]
    assert "Only 1 model contributes" in rendered["explanation"]
    assert "illustrative" in rendered["explanation"] and "low quality" in rendered["explanation"]
    assert rendered["quantitative_claims"][0]["value"] == 619.5604742486083
    assert rendered["evidence_ids"] == list(items)
    assert candidate.model_dump() == original and items == original_items


@pytest.mark.parametrize("category", ["policy_estimate", "valuation_output"])
def test_msft_mixed_policy_value_quote_and_model_count_keep_specific_policy_basis(category):
    items = registry()
    candidate = finding(category=category, explanation="Fairworth produced a policy-based intrinsic value of {{value:e_fair}} per share using {{model:e_model}}. Only {{value:e_count}} model contributes, versus a dated quote of {{value:e_price}} observed on {{date:e_price}}; valuation quality remains low.", evidence_ids=list(items))
    original = candidate.model_dump()
    result = render_finding(candidate, items)
    assert result["category"] == "policy_estimate"
    assert result["uncertainty"] in {"limited", "analytical"}
    assert "$619.56" in result["explanation"] and "$533.69" in result["explanation"]
    assert "Only 1 model" in result["explanation"]
    assert result["quantitative_claims"][0]["value"] == 619.5604742486083
    assert candidate.model_dump() == original


def test_misclassified_policy_diagnostic_identifies_binding_not_digits_inside_evidence_id():
    items = registry()
    candidate = finding(category="reported_fact", explanation="The reported value is {{value:e_fair}}.")
    diagnostic = validation_diagnostic([candidate], items)
    assert diagnostic["rule"] == "claim_evidence_category_mismatch"
    assert diagnostic["finding_category"] == "reported_fact"
    assert diagnostic["evidence_category"] == "policy_estimate"
    assert diagnostic["rejected_span"] == "{{value:e_fair}}"


def test_large_integer_claim_keeps_source_precision_and_rejects_a_rounded_float():
    items = registry()
    items["e_fair"]["value"] = 9007199254740993
    rendered = render_finding(finding(explanation="The source value is {{value:e_fair}}."), items)
    assert "$9,007,199,254,740,993.00" in rendered["explanation"]
    assert rendered["quantitative_claims"][0]["value"] == 9007199254740993
    assert isinstance(rendered["quantitative_claims"][0]["value"], int)
    rounded = claim(items["e_fair"]).model_copy(update={"value": float(items["e_fair"]["value"])})
    with pytest.raises(ApiError) as rejected:
        validate_findings([finding(quantitative_claims=[rounded])], items)
    assert rejected.value.code == "unsupported_ai_claim"


@pytest.mark.parametrize("invalid", [True, False, "619.56"])
def test_quantitative_claim_never_coerces_non_numeric_types(invalid):
    from pydantic import ValidationError
    payload = claim(registry()["e_fair"]).model_dump()
    with pytest.raises(ValidationError):
        QuantitativeClaim.model_validate({**payload, "value": invalid})


def test_fiscal_period_and_form_name_do_not_become_financial_quantity_claims():
    items = registry()
    candidate = finding(explanation="The SEC 10-K covers {{period:e_fair}}. Its illustrative Forward P/E estimate remains policy-dependent.")
    rendered = render_finding(candidate, items)
    assert "SEC 10-K" in rendered["explanation"]
    assert "FY2026; 2025-07-01 to 2026-06-30" in rendered["explanation"]
    assert candidate.explanation.count("{{period:e_fair}}") == 1


@pytest.mark.parametrize("form", ["10-K", "10-Q", "10\u2011K", "10\u2011Q", "10\u2013K"])
def test_official_form_identifiers_are_not_quantities(form):
    items = registry()
    assert validate_findings([finding(explanation=f"The SEC {form} is a dated financial source.")], items) == ["e_fair"]


@pytest.mark.parametrize("value,unit,display", [
    (0.12, "fraction", "12.00%"),
    (12.0, "percent", "12.00%"),
    (29.40123247853427, "multiple", "29.40\u00d7"),
    (1.10, "ratio", "1.10"),
    (1, "count", "1"),
    (1, "models", "1"),
    (1234.56, "USD", "$1,234.56"),
    (21.072602133293124, "USD/shares", "$21.07"),
    (0, "USD/share", "$0.00"),
    (-5.25, "percent", "-5.25%"),
])
def test_unit_owned_rendering_does_not_change_stored_evidence(value, unit, display):
    item = evidence(value=value, unit=unit)
    candidate = finding(explanation="The evidence-backed observation is {{claim:0}}.", quantitative_claims=[claim(item)])
    result = render_finding(candidate, {item["id"]: item})
    assert result["explanation"] == f"The evidence-backed observation is {display}."
    assert result["quantitative_claims"][0]["value"] == value
    assert item["value"] == value and item["unit"] == unit


@pytest.mark.parametrize("text", [
    "The fair value is $619.56.",
    "The market price is $533.69.",
    "Only one model contributes.",
    "The source covers FY2026.",
    "The quote was observed on 2026-10-14.",
    "The assumed growth is twelve percent.",
    "Revenue was nine billion USD.",
    "Revenue was billions of USD.",
    "Revenue grew a dozen percent.",
    "Revenue doubled over the period.",
    "The stock has a 50% probability of a higher valuation.",
    "The fair value is \uff16\uff11\uff19.\uff15\uff16 USD.",
    "The valuation uses \u00bd of the eligible models.",
])
def test_raw_financial_numbers_are_not_accepted_just_because_digits_appear_in_sources(text):
    items = registry()
    candidate = finding(explanation=text, evidence_ids=list(items), quantitative_claims=[claim(items["e_fair"])])
    with pytest.raises(ApiError):
        render_finding(candidate, items)


@pytest.mark.parametrize("field,wrong", [
    ("value", 619.56),
    ("metric", "market_price"),
    ("unit", "EUR/share"),
    ("period", "FY2025"),
    ("derivation", "AI-calculated discounted cash flow"),
])
def test_placeholder_cannot_make_rounded_or_mislabelled_claims_valid(field, wrong):
    items = registry()
    typed = claim(items["e_fair"]).model_dump()
    typed[field] = wrong
    candidate = finding(explanation="The estimate is {{claim:0}}.", quantitative_claims=[QuantitativeClaim(**typed)])
    with pytest.raises(ApiError):
        render_finding(candidate, items)


def test_policy_claim_cannot_borrow_reported_fact_classification_from_another_citation():
    items = registry()
    candidate = finding(explanation="The estimate is {{claim:0}}.", evidence_ids=["e_fair", "e_price"],
                        category="reported_fact", uncertainty="documented", quantitative_claims=[claim(items["e_fair"])])
    with pytest.raises(ApiError):
        render_finding(candidate, items)


@pytest.mark.parametrize("text", [
    "The estimate is {{claim:1}}.",
    "The estimate is {{claim:-1}}.",
    "The estimate is {{claim:01}}.",
    "The estimate is {{claim:\uff10}}.",
    "The estimate is {claim:0}.",
    "The estimate is {{claim:0}.",
    "The estimate is {{claim:0}} plus {{unknown:e_fair}}.",
    "The estimate is {{value:missing}}.",
    "The period is {{period:missing}}.",
    "The observation is {{date:missing}}.",
    "The estimate uses {{model:e_fair}}.",
])
def test_unknown_malformed_or_mistyped_tokens_fail_closed(text):
    items = registry()
    candidate = finding(explanation=text, quantitative_claims=[claim(items["e_fair"])])
    with pytest.raises(ApiError):
        render_finding(candidate, items)


@pytest.mark.parametrize("text", ["{{period:e_price}}", "{{date:e_price}}", "{{model:e_model}}"])
def test_uncited_metadata_cannot_be_inserted_from_elsewhere_in_registry(text):
    with pytest.raises(ApiError):
        render_finding(finding(explanation=f"The source detail is {text}."), registry())


@pytest.mark.parametrize("date", [None, "not-a-date", "2026-02-30", "2026-10-14 extra invented assertion"])
def test_observation_date_requires_actual_valid_source_metadata(date):
    items = registry()
    items["e_fair"]["observation_date"] = date
    candidate = finding(explanation="The observation date is {{date:e_fair}}.")
    with pytest.raises(ApiError):
        render_finding(candidate, items)


def test_retrieval_date_cannot_substitute_for_missing_observation_date():
    items = registry()
    items["e_fair"]["observation_date"] = None
    items["e_fair"]["retrieved_at"] = "2026-10-15"
    with pytest.raises(ApiError):
        render_finding(finding(explanation="The observation date is {{date:e_fair}}."), items)


@pytest.mark.parametrize("value", [True, False, None, "619.56", {"fair_value": 619.56}, [619.56], math.inf, math.nan])
def test_non_numeric_or_non_finite_evidence_cannot_back_numeric_tokens(value):
    items = registry()
    good_claim = claim(items["e_fair"])
    items["e_fair"]["value"] = value
    candidate = finding(explanation="The estimate is {{claim:0}}.", quantitative_claims=[good_claim])
    with pytest.raises(ApiError):
        render_finding(candidate, items)


def test_valid_quantity_does_not_allow_an_extra_invented_quantity_in_same_finding():
    items = registry()
    candidate = finding(explanation="The illustrative estimate is {{claim:0}}, with a guaranteed 99% probability.",
                        quantitative_claims=[claim(items["e_fair"])])
    with pytest.raises(ApiError):
        render_finding(candidate, items)


def test_title_and_explanation_are_checked_independently_and_never_mutated():
    items = registry()
    candidate = finding(title="Illustrative estimate", explanation="The illustrative estimate is {{claim:0}}; low quality limits confidence.",
                        quantitative_claims=[claim(items["e_fair"])])
    original = candidate.model_dump()
    assert render_finding(candidate, items)["explanation"] == "The illustrative estimate is $619.56; low quality limits confidence."
    assert candidate.model_dump() == original
    candidate.title += " with 99% confidence"
    with pytest.raises(ApiError):
        render_finding(candidate, items)


def test_title_references_are_forbidden_even_when_complete_and_cited():
    items = registry()
    candidate = finding(title="Illustrative estimate: {{value:e_fair}}")
    with pytest.raises(ApiError) as rejected:
        render_finding(candidate, items)
    assert rejected.value.code == "unsupported_ai_binding"
    assert rejected.value.details["rule"] == "title_binding_forbidden"


def test_direct_value_binding_constructs_exact_server_owned_claim_and_keeps_input_immutable():
    items = registry()
    candidate = finding(explanation="The illustrative {{model:e_model}} estimate is {{value:e_fair}}, versus {{value:e_price}} as observed on {{date:e_price}}.",
                        evidence_ids=["e_fair", "e_price", "e_model"])
    original = candidate.model_dump()
    result = render_finding(candidate, items)
    assert "Forward P/E estimate is $619.56, versus $533.69" in result["explanation"]
    assert result["quantitative_claims"] == [claim(items[key]).model_dump() for key in ("e_fair", "e_price")]
    assert candidate.model_dump() == original


@pytest.mark.parametrize("value", [None, True, "619.56", {"fair_value": 619.56}, math.inf, math.nan])
def test_direct_value_binding_requires_a_finite_scalar_source(value):
    items = registry()
    items["e_fair"]["value"] = value
    with pytest.raises(ApiError):
        render_finding(finding(explanation="The estimate is {{value:e_fair}}."), items)


def test_direct_value_binding_requires_citation_and_does_not_relabel_policy_as_fact():
    items = registry()
    for candidate in (
        finding(explanation="The price is {{value:e_price}}."),
        finding(explanation="The estimate is {{value:e_fair}}.", category="reported_fact", uncertainty="documented"),
    ):
        with pytest.raises(ApiError):
            render_finding(candidate, items)


@pytest.mark.asyncio
@pytest.mark.parametrize("question", [
    "Why is MSFT's valuation available or unavailable?",
    "How does the illustrative fair value compare with the dated market price?",
    "Why is low valuation quality still shown when Forward P/E is available?",
])
async def test_realistic_msft_chat_keeps_traceable_display_values_without_another_model_call(question):
    from test_ai_research_service import package, service

    research = service()
    context = package(ticker="MSFT")
    context["registry"] = registry()
    research.assembler.assemble.return_value = context
    research.client.generate.return_value = ChatDraft(answer=[finding(
        explanation="The illustrative {{model:e_model}} estimate is {{value:e_fair}}, compared with {{value:e_price}} observed on {{date:e_price}}. Only {{value:e_count}} model contributes, so low quality and missing independent confirmation remain limitations.",
        evidence_ids=list(context["registry"]),
    )])
    original = deepcopy(context)
    result = await research.chat("MSFT", ChatRequest(question=question), "test-owner")
    answer = result["answer"][0]
    assert "$619.56" in answer["explanation"] and "$533.69" in answer["explanation"]
    assert "Only 1 model contributes" in answer["explanation"]
    assert "2026-10-14" in answer["explanation"]
    assert len(answer["quantitative_claims"]) == 3
    cited = {item["id"]: item for item in result["evidence_references"]}
    assert set(answer["evidence_ids"]) == set(cited) == set(original["registry"])
    for quantity in answer["quantitative_claims"]:
        assert quantity == claim(cited[quantity["evidence_id"]]).model_dump()
    assert research.assembler.assemble.return_value == original
    research.client.generate.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [52000, 12000])
async def test_retained_msft_context_keeps_displayed_prices_and_contributing_count_ahead_of_old_history(budget):
    from test_ai_evidence_context import Valuations, assembler, find
    from app.valuation.engine import calculate_valuation

    valuations = Valuations("MSFT")
    original = deepcopy(valuations.data)
    engine = calculate_valuation(valuations.data)
    context = await assembler(valuations, budget=budget).assemble("MSFT")
    fair = find(context, "base_fair_value")
    price = find(context, "market_price")
    count = find(context, "base_contributing_model_count")
    assert fair["value"] == engine["scenarios"]["base"]["summary"]["fair_value"]
    assert fair["value"] == 619.5604742486083
    assert fair["category"] == "policy_estimate" and fair["derivation"]
    assert price["value"] == engine["market"]["price"]
    assert price["observation_date"] == engine["market"]["price_timestamp"]
    assert count["value"] == engine["scenarios"]["base"]["summary"]["count"] == 1
    assert count["provider"] == "Fairworth Python valuation engine" and count["derivation"]
    assert any(item["metric"].endswith("_model_name") and item["value"] == "Forward P/E"
               for item in context["registry"].values())
    assert valuations.data == original


def test_safe_rejection_diagnostic_identifies_exact_span_rule_and_relevant_source():
    items = registry()
    candidate = finding(explanation="Only one model contributes to this illustrative estimate.", evidence_ids=["e_count"])
    result = validation_diagnostic([candidate], items)
    assert result["finding_index"] == 0 and result["field"] == "explanation"
    assert result["rejected_span"] == "one" and "Only one model" in result["excerpt"]
    assert result["error_code"] == "unsupported_ai_number"
    assert result["rule"] == "unbound_numeric_prose"
    assert result["evidence"][0]["metric"] == "base_contributing_model_count"
    assert result["evidence"][0]["value"] == 1


def test_diagnostic_redacts_private_values_and_contacts_even_in_source_metadata():
    private = "private_diagnostic_marker_for_offline_test"
    items = registry()
    items["e_fair"]["derivation"] = f"An untrusted annotation contains {private} and analyst@example.com."
    candidate = finding(explanation=f"The annotation {private} says one model contributes; contact analyst@example.com.")
    result = validation_diagnostic([candidate], items, private_values=[private])
    serialized = json.dumps(result)
    assert private not in serialized and "analyst@example.com" not in serialized
    assert result["rejected_span"] == "one"
    assert "[redacted]" in serialized and "[contact redacted]" in serialized


@pytest.mark.parametrize("value", [1e40, 1e308])
def test_huge_finite_values_render_or_fail_with_a_controlled_api_error(value):
    items = registry()
    items["e_fair"]["value"] = value
    candidate = finding(explanation="The source observation is {{value:e_fair}}.")
    original = candidate.model_dump()
    try:
        result = render_finding(candidate, items)
    except ApiError as error:
        assert error.status_code >= 400
    else:
        assert result["explanation"].startswith("The source observation is $")
        assert result["explanation"].endswith(".00.")
        assert "e+" not in result["explanation"].lower()
        assert len(result["explanation"]) > 50
        assert result["quantitative_claims"][0]["value"] == value
    assert candidate.model_dump() == original and items["e_fair"]["value"] == value


@pytest.mark.parametrize("period", [
    "FY2026; 2025-07-01 to 2026-02-30",
    "FY2026; 2025-13-01 to 2026-06-30",
    "2026-02-30",
    "2025-07-01 to 2026-06-31",
])
def test_period_bindings_reject_impossible_calendar_dates(period):
    items = registry()
    items["e_fair"]["period"] = period
    with pytest.raises(ApiError):
        render_finding(finding(explanation="The source period is {{period:e_fair}}."), items)


@pytest.mark.parametrize("kind,field,value", [
    ("period", "period", "FY2026; 2025-07-01 to 2026-06-30 99%"),
    ("period", "period", "FY2026; 2025-07-01 to 2026-06-30 <script>unsafe</script>"),
    ("date", "observation_date", "2026-10-14 99%"),
    ("date", "observation_date", "2026-10-14 https://example.com"),
    ("model", "value", "Forward P/E at 99% guaranteed returns"),
    ("model", "value", "Forward P/E <script>unsafe</script>"),
])
def test_metadata_bindings_cannot_smuggle_percentages_or_unvalidated_text(kind, field, value):
    items = registry()
    identifier = "e_model" if kind == "model" else "e_fair"
    items[identifier][field] = value
    candidate = finding(explanation=f"The source detail is {{{{{kind}:{identifier}}}}}.", evidence_ids=[identifier])
    with pytest.raises(ApiError):
        render_finding(candidate, items)
