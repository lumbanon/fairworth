"""End-to-end API contracts use synthetic providers, never external credentials."""
import json

import pytest
from sqlalchemy import func, select

from app.models import FinancialFact, FinancialSnapshot, MarketSnapshot
from test_api import client  # Shared isolated app/SQLite fixture, not a live API.


BASE = "/api/stocks/MSFT/valuation"


def test_defaults_models_sources_and_openapi(client):
    response = client.get(BASE + "/defaults")
    assert response.status_code == 200
    body = response.json()
    assert body["engine_version"] == "1.1.0"
    assert body["currency"] == "USD"
    assert body["financials"]["facts"]["revenue"]["value"] == 1000
    assert body["financials"]["facts"]["revenue"]["provenance"]
    assert len(body["scenarios"]["base"]["models"]) == 11
    assert body["defaults"]["base"]["values"]["target_pe"] is None
    assert body["defaults"]["base"]["metadata"]["cost_of_equity"]["source_type"] == "benchmark_assumption"
    assert body["scenarios"]["base"]["summary"]["fair_value"] is None
    spec = client.get("/openapi.json").json()
    route = spec["paths"]["/api/stocks/{ticker}/valuation/calculate"]["post"]
    assert route["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("ValuationRequest")
    assert route["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("ValuationResponse")


def test_calculation_scenarios_sensitivity_and_price_are_authoritative(client, fake_providers):
    body = {"assumptions": {"forward_eps": 5, "target_pe": 20}, "enabled_models": ["pe"], "weights": {"pe": 100},
            "manual_market_price": {"value": 80, "currency": "USD"},
            "sensitivity": {"model_id": "pe", "x_parameter": "forward_eps", "y_parameter": "target_pe"}}
    response = client.post(BASE + "/calculate", json=body)
    assert response.status_code == 200
    result = response.json()
    base = result["scenarios"]["base"]
    assert base["summary"]["fair_value"] == 100
    assert base["summary"]["upside"] == 25
    assert base["summary"]["margin_of_safety"] == 20
    assert result["scenarios"]["bear"]["summary"]["fair_value"] == 81
    assert result["scenarios"]["bull"]["summary"]["fair_value"] == pytest.approx(121)
    assert result["sensitivity"]["rows"][2]["cells"][2]["fair_value"] == 100
    assert result["market"]["source_type"] == "user"
    assert result["market"]["provider_price"] == 100
    assert client.get("/api/stocks/MSFT").json()["market"]["price"] == 100
    # Twenty transient recalculations reuse one normalized source ingestion.
    for multiple in range(10, 30):
        body["assumptions"]["target_pe"] = multiple
        assert client.post(BASE + "/calculate", json=body).status_code == 200
    assert fake_providers[0].facts_calls == 1
    assert fake_providers[1].quote_calls == 1
    assert client.post(BASE + "/scenarios", json=body).status_code == 200
    assert client.post(BASE + "/sensitivity", json=body).json()["model_id"] == "pe"
    assert client.get(BASE + "/eligibility").status_code == 200
    assert client.get(BASE + "/explain").status_code == 200


def test_missing_market_price_does_not_disable_intrinsic_value(client, fake_providers):
    fake_providers[1].fail = True
    request = {"assumptions": {"forward_eps": 6, "target_pe": 20}, "enabled_models": ["pe"]}
    result = client.post(BASE + "/calculate", json=request)
    assert result.status_code == 200
    body = result.json()
    assert body["scenarios"]["base"]["summary"]["fair_value"] == 120
    assert body["scenarios"]["base"]["summary"]["upside"] is None
    assert body["reverse_dcf"]["status"] == "unavailable"
    request["manual_market_price"] = {"value": 100, "currency": "USD"}
    body = client.post(BASE + "/calculate", json=request).json()
    assert body["market"]["label"] == "User-provided market price"
    assert body["scenarios"]["base"]["summary"]["upside"] == pytest.approx(20)


def test_manual_and_transient_assumptions_never_persist_market_or_financial_snapshots(client, session_factory):
    client.get(BASE + "/defaults")
    def counts():
        with session_factory() as session:
            return tuple(session.scalar(select(func.count()).select_from(model)) for model in (FinancialFact, FinancialSnapshot, MarketSnapshot))
    original = counts()
    for price in (100, 200, 300):
        response = client.post(BASE + "/calculate", json={"assumptions": {"forward_eps": price / 10, "target_pe": 20}, "manual_market_price": {"value": price, "currency": "USD"}})
        assert response.status_code == 200
    assert counts() == original


@pytest.mark.parametrize("payload", [
    {"assumptions": {"target_pe": -10}}, {"assumptions": {"shares": 0}},
    {"weights": {"reverse_dcf": 100}}, {"assumptions": {"url": "https://example.com"}},
    {"manual_market_price": {"value": 100, "currency": "EUR"}},
    {"sensitivity": {"model_id": "pe", "x_parameter": "wacc", "y_parameter": "terminal_growth"}},
])
def test_invalid_inputs_are_safe_structured_errors(client, payload):
    response = client.post(BASE + "/calculate", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] in {"invalid_request", "incompatible_currency", "invalid_sensitivity"}
    assert "traceback" not in response.text.lower()


def test_no_nonfinite_json_and_sensitive_values_not_exposed(client):
    response = client.post(BASE + "/calculate", content='{"assumptions":{"target_pe":NaN}}', headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    text = client.get(BASE + "/defaults").text
    json.loads(text, parse_constant=lambda value: pytest.fail(f"Nonfinite JSON: {value}"))
    assert "postgresql" not in text and "apikey=" not in text and "sec_user_agent" not in text


def test_post_cors_preflight_retains_explicit_origin_policy(client):
    response = client.options(BASE + "/calculate", headers={"Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Content-Type"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    blocked = client.options(BASE + "/calculate", headers={"Origin": "https://example.com", "Access-Control-Request-Method": "POST"})
    assert blocked.status_code == 400
