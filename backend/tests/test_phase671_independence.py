"""Dependence disclosures do not invent independent estimates or change weights."""
from copy import deepcopy
from app.valuation.independence import build_independence


def model(identifier, used):
    return {"id": identifier, "status": "valid", "source_quality": {"used_inputs": used}}


def test_shared_earnings_assumptions_and_exact_sources_are_visible():
    evidence = {"concept": "EarningsPerShareDiluted", "accn": "fixture-source", "unit": "USD/shares", "start": "2025-01-01", "end": "2025-12-31"}
    inputs = {"facts": {"diluted_eps": {"value": 5, "source_type": "reported", "provenance": [evidence]}}}
    assumptions = {"metadata": {"forward_eps": {"value": 6, "evidence_type": "estimate", "dependency_fields": ["trailing_eps", "earnings_growth"]},
                                 "earnings_growth": {"value": .2, "evidence_type": "policy"}}}
    summary = {"effective_weights": {"pe": .8, "peg": .2}}
    original = deepcopy((inputs, assumptions, summary))
    result = build_independence(inputs, [model("pe", ["forward_eps"]), model("peg", ["forward_eps"])], summary, assumptions)
    assert (inputs, assumptions, summary) == original
    assert result["method_family_count"] == 1 and result["contributing_model_count"] == 2
    assert result["pairs"][0]["shared_assumptions"] == ["earnings_growth", "forward_eps"]
    assert result["pairs"][0]["shared_source_records"] == [evidence]
    assert result["corroboration"]["status"] == "unverified"


def test_distinct_families_and_disjoint_records_never_prove_independence():
    inputs = {"facts": {"diluted_eps": {"value": 5}, "book_equity": {"value": 500}}}
    result = build_independence(inputs, [model("pe", ["trailing_eps"]), model("pb", ["book_equity"])], {"effective_weights": {"pe": .5, "pb": .5}}, {"metadata": {}})
    assert result["method_family_count"] == 2
    assert result["pairs"][0]["shared_assumptions"] == []
    assert result["corroboration"]["status"] == "unverified"


def test_disabled_and_invalid_models_do_not_count_as_corroboration():
    result = build_independence({}, [model("pe", []), {"id": "pb", "status": "unavailable"}], {"effective_weights": {"pe": 1, "pb": 0}}, {"metadata": {}})
    assert result["contributing_models"] == ["pe"]
    assert result["pairs"] == []
    assert result["corroboration"]["status"] == "unavailable"


def test_user_override_does_not_claim_unused_original_filing_or_dependencies():
    evidence = {"concept": "EarningsPerShareDiluted", "accn": "unused-original", "unit": "USD/shares", "end": "2025-12-31"}
    inputs = {"facts": {"diluted_eps": {"value": 5, "source_type": "reported", "provenance": [evidence]}}}
    assumptions = {"metadata": {"trailing_eps": {"value": 8, "source_type": "user_assumption", "provenance": [evidence],
        "dependency_fields": ["unused_reported_metric"]}}}
    result = build_independence(inputs, [model("pe", ["trailing_eps"]), model("peg", ["trailing_eps"])],
        {"effective_weights": {"pe": .5, "peg": .5}}, assumptions)
    assert result["pairs"][0]["shared_assumptions"] == ["trailing_eps"]
    assert result["pairs"][0]["shared_source_records"] == []
    assert result["pairs"][0]["shared_observed_inputs"] == []
    assert inputs["facts"]["diluted_eps"]["provenance"] == [evidence]
