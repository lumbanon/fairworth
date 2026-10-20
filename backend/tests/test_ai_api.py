from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.config import Settings
from test_ai_research_service import configured, service, package

SESSION = {"X-Fairworth-Session": "test-browser-session-token"}


@pytest.fixture
def ai_client(engine, fake_providers):
    app = create_app(configured(database_url="sqlite://"), engine=engine, providers=fake_providers)
    with TestClient(app) as client:
        app.state.research_service = service()
        yield client, app.state.research_service


def test_status_disabled_does_not_call_providers_or_expose_configuration(engine, fake_providers):
    app = create_app(Settings(_env_file=None, database_url="sqlite://"), engine=engine, providers=fake_providers)
    with TestClient(app) as client:
        response = client.get("/api/stocks/AAPL/ai/status")
        assert response.status_code == 200 and response.json()["available"] is False
        assert "api_key" not in response.text and "database_url" not in response.text
        assert client.post("/api/stocks/AAPL/ai/report", json={}, headers=SESSION).status_code == 503
        assert fake_providers[0].facts_calls == 0


def test_report_evidence_session_and_unknown_fields(ai_client):
    client, research = ai_client
    assert client.post("/api/stocks/AAPL/ai/report", json={}).status_code == 400
    report = client.post("/api/stocks/aapl/ai/report", json={}, headers=SESSION)
    assert report.status_code == 200
    body = report.json()
    assert body["ticker"] == "AAPL" and body["cache_status"] == "miss"
    path = "/api/stocks/AAPL/ai/evidence/e_revenue?snapshot_token=" + body["snapshot_token"]
    assert client.get(path, headers=SESSION).json()["value"] == 100
    assert client.get(path, headers={"X-Fairworth-Session": "another-browser-session"}).status_code == 404
    assert client.post("/api/stocks/AAPL/ai/chat", json={"question": "question", "model": "unapproved"}, headers=SESSION).status_code == 422
    assert research.client.generate.await_count == 1


def test_rate_limit_and_body_size_enforced_before_generation(ai_client):
    client, research = ai_client
    research.settings.ai_client_requests_per_minute = 1
    assert client.post("/api/stocks/AAPL/ai/report", json={}, headers=SESSION).status_code == 200
    second = client.post("/api/stocks/AAPL/ai/report", json={}, headers=SESSION)
    assert second.status_code == 429 and second.json()["error"]["code"] == "ai_rate_limited"
    assert client.post("/api/stocks/AAPL/ai/chat", content=b"x" * 32769, headers=SESSION).status_code == 413
    assert research.client.generate.await_count == 1


def test_cors_allows_session_header_only_for_configured_frontend(ai_client):
    client, _ = ai_client
    response = client.options("/api/stocks/AAPL/ai/report", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "X-Fairworth-Session,Content-Type"})
    assert response.status_code == 200
    assert "x-fairworth-session" in response.headers["access-control-allow-headers"].lower()


@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "NVDA", "ORCL"])
def test_mocked_ai_report_chat_company_scoping_for_four_companies(ai_client, ticker):
    from app.ai.schemas import ChatDraft
    from test_ai_research_service import finding
    client, research = ai_client
    research.assembler.assemble.return_value = package(ticker)
    response = client.post(f"/api/stocks/{ticker}/ai/report", json={}, headers=SESSION)
    assert response.status_code == 200 and response.json()["ticker"] == ticker
    research.client.generate.return_value = ChatDraft(answer=[finding()])
    chat = client.post(f"/api/stocks/{ticker}/ai/chat", json={"question": f"Explain {ticker}'s dated evidence."}, headers=SESSION)
    assert chat.status_code == 200 and chat.json()["ticker"] == ticker
    assert all(item["ticker"] == ticker for item in chat.json()["evidence_references"])
