"""The inventory reports evidence status without supplying missing model inputs."""
from copy import deepcopy

from app.valuation.completeness import build_data_completeness


def inventory(inputs=None, metadata=None, models=None, market=None):
    return build_data_completeness(inputs or {}, {"metadata": metadata or {}}, models or [], market or {})


def test_exact_zero_false_and_missing_remain_distinct_without_mutating_evidence():
    inputs = {"normalization_version": 4, "facts": {
        "cash": {"value": 0, "unit": "USD", "source_type": "reported", "provenance": [{"source": "sec", "accn": "original"}]},
        "common_equity_confirmed": {"value": False, "source_type": "user"},
        "debt": {"value": None, "source_type": "unavailable"}}}
    before = deepcopy(inputs)
    result = inventory(inputs)
    assert {"cash", "common_equity_confirmed"} <= set(result["groups"]["available"])
    assert "debt" in result["groups"]["missing"]
    assert result["fields"]["cash"]["value"] == 0
    assert result["fields"]["cash"]["provider"] == "sec-edgar"
    assert result["normalization_version"] == 4
    result["fields"]["cash"]["provenance"][0]["accn"] = "changed copy"
    assert inputs == before


def test_effective_user_override_keeps_original_and_explicit_null_provenance():
    inputs = {"facts": {"cash": {"value": 100, "unit": "USD", "source_type": "reported"}}}
    metadata = {"cash": {"value": 80.123456789, "unit": "USD", "source_type": "user_override", "overridden": True},
                "debt": {"value": None, "source_type": "user", "overridden": True}}
    result = inventory(inputs, metadata)
    assert result["fields"]["cash"]["reported_value"] == 100
    assert result["fields"]["cash"]["value"] == 80.123456789
    assert {"cash", "debt"} <= set(result["groups"]["user"])
    assert "debt" in result["groups"]["missing"]
    assert inputs["facts"]["cash"]["value"] == 100


def test_groups_overlap_and_do_not_convert_warnings_or_policy_into_reported_facts():
    inputs = {"data_status": "stale", "facts": {
        "lease": {"value": 12, "unit": "USD", "source_type": "derived", "provenance": [
            {"source": "sec", "accn": "accession", "derivation": "Compatible current + noncurrent lease liabilities"}]},
        "bad_debt": {"value": None, "source_type": None, "provenance": None, "warnings": ["Debt scope unverified"]}}}
    metadata = {"target_pe": {"value": 20.1234567, "unit": "multiple", "source_type": "policy", "evidence_type": "policy", "derivation_method": "Explicit research policy"}}
    result = inventory(inputs, metadata)
    assert "lease" in result["groups"]["available"] and "lease" in result["groups"]["derived"]
    assert "lease" in result["groups"]["stale"]
    assert "target_pe" in result["groups"]["policy"]
    assert "target_pe" not in result["groups"]["derived"]
    assert "bad_debt" in result["groups"]["incompatible"]
    assert result["fields"]["bad_debt"]["source_type"] == "unavailable"
    assert result["fields"]["lease"]["source_identifiers"] == ["accession"]


def test_quote_observation_is_not_retrieval_and_restricted_capabilities_stay_null():
    inputs = {"currency": "USD", "automatic_evidence": {"provider_status": {
        "balance_sheet": "provider_subscription_required", "broken": {"status": {"unexpected": "record"}}}}}
    market = {"price": 123.456789, "price_timestamp": "2026-10-13T20:00:00Z", "retrieved_at": "2026-10-16T12:00:00Z",
              "provider": "fixture", "status": "stale"}
    result = inventory(inputs, market=market)
    quote = result["fields"]["market_price"]
    assert quote["observation_date"] == result["quote_observation_date"] == market["price_timestamp"]
    assert quote["retrieved_at"] == market["retrieved_at"]
    assert quote["value"] == market["price"]
    assert "market_price" in result["groups"]["stale"]
    assert result["groups"]["restricted"] == ["provider_balance_sheet"]
    assert result["fields"]["provider_balance_sheet"]["value"] is None
    assert "provider_broken" not in result["fields"]


def test_access_denied_is_a_restriction_instead_of_a_missing_fact_substitute():
    result = inventory({"automatic_evidence": {"provider_status": {"balance_sheet": "provider_access_denied"}}})
    assert result["groups"]["restricted"] == ["provider_balance_sheet"]
    assert result["fields"]["provider_balance_sheet"]["value"] is None


def test_manual_price_never_inherits_the_provider_quote_source_or_retrieval():
    from app.valuation.engine import comparison_market
    from app.valuation.schemas import ManualPrice
    inputs = {"currency": "USD", "market": {"price": 100, "currency": "USD", "provider": "fixture-market",
        "price_timestamp": "2026-10-13T20:00:00Z", "retrieved_at": "2026-10-16T00:00:00Z", "status": "partial"}}
    market = comparison_market(inputs, ManualPrice(value=90, currency="USD"))
    result = inventory(inputs, market=market)
    manual = result["fields"]["market_price"]
    assert manual["value"] == 90 and manual["provider"] == "User"
    assert manual["retrieved_at"] is None and manual["observation_date"] is None
    assert result["quote_observation_date"] is None
    assert "market_price" in result["groups"]["user"]
    assert manual["original_provider_observation"] == {"value": 100, "currency": "USD", "provider": "fixture-market",
        "observation_date": "2026-10-13T20:00:00Z", "retrieved_at": "2026-10-16T00:00:00Z"}


def test_model_blockers_do_not_receive_fallback_values_and_dates_remain_explicit():
    models = [{"eligibility": {"missing_inputs": ["wacc", "debt"]}}]
    inputs = {"financial_retrieved_at": "2026-10-16T00:00:00Z", "reporting_period": {"end_date": "2026-06-30"}}
    result = inventory(inputs, models=models)
    assert {"wacc", "debt"} <= set(result["groups"]["missing"])
    assert result["fields"]["wacc"]["value"] is None
    assert result["as_of"] == inputs["financial_retrieved_at"]
    assert result["reporting_period"] == inputs["reporting_period"]
    assert result["quote_observation_date"] is None
    assert not any("percent" in key for key in result)


def test_rejected_stored_amount_remains_inspectable_without_becoming_available():
    inputs = {"facts": {"total_debt": {"value": None, "reported_value": 120,
        "source_type": "unavailable", "warnings": ["Incomplete conventional debt scope"]}}}
    result = inventory(inputs)
    assert result["fields"]["total_debt"]["value"] is None
    assert result["fields"]["total_debt"]["reported_value"] == 120
    assert "total_debt" in result["groups"]["missing"]
    assert "total_debt" not in result["groups"]["available"]
