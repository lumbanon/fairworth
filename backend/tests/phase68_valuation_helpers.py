"""Small actual public SEC observations, isolated registry and explicit clocks."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from types import SimpleNamespace

from app.models import CacheEntry
from app.registry.repository import SecurityRegistryRepository
from app.registry.service import SecurityRegistryService
from app.repositories.financial_repository import content_hash
from app.services.normalization import normalize_company_facts
from app.valuation.inputs import build_valuation_inputs
from app.valuation.schemas import ValuationRequest

FIXTURE = Path(__file__).parent / "fixtures/valuation/phase68_msft_real_dividend.json"


def real_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def import_registry(factory, fixture=None):
    fixture = fixture or real_fixture()
    repository = SecurityRegistryRepository(factory)
    for source in sorted(fixture["registry"], key=lambda source: source["provenance"]["source"] != "sec-edgar-reference"):
        repository.import_snapshot(deepcopy(source["records"]), deepcopy(source["provenance"]))
    registry = SecurityRegistryService(factory, SimpleNamespace(registry_bootstrap_enabled=False, registry_cache_ttl_seconds=86400))
    return registry


def retain_profile(factory, fixture=None):
    record = (fixture or real_fixture())["profile"]
    assert content_hash(record["payload"]) == record["sha256"]
    with factory.begin() as session:
        session.add(CacheEntry(key=record["key"], provider=record["provider"], payload=deepcopy(record["payload"]),
            retrieved_at=datetime.fromisoformat(record["retrieved_at"]), expires_at=datetime.fromisoformat(record["expires_at"])))


def real_inputs(factory, fixture=None):
    fixture = fixture or real_fixture()
    registry = import_registry(factory, fixture)
    company = registry._with_freshness(registry.repository.resolve("MSFT"))
    company = {**fixture["profile"]["payload"], **company}
    normalized = normalize_company_facts(fixture["raw"], cik=company["cik"])
    inputs = build_valuation_inputs({"company": company, "market": None}, normalized, fixture["source"]["retrieved_at"])
    inputs["dated_share_basis_evidence"] = {"source_type": "retained_sec_adapter_profile", "source_hash": fixture["profile"]["sha256"],
        "retrieved_at": fixture["profile"]["retrieved_at"], "ticker": "MSFT", "cik": company["cik"], "has_multiple_share_classes": False}
    inputs["financial_source_status"] = {"status": "stale"}
    return inputs


def request(**edits):
    return ValuationRequest.model_validate({"context": "dated_intrinsic", "evidence_as_of": real_fixture()["evidence_as_of"],
        "enabled_models": ["dividend"], "assumptions": {"dividend_growth": 0.03, "cost_of_equity": 0.10, "stable_dividend_confirmed": True}, **edits})
