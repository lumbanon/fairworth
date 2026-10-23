"""Immutable normalization survives object-key reordering, including real JSONB.

The small examples always run offline. The eight full original SEC captures are
optional local acceptance inputs, not downloaded or copied into the repository.
PostgreSQL tests use SELECT expressions in a read-only dedicated *_test database;
they do not create tables, import facts, or connect to the development database.
"""
from collections import Counter
from copy import deepcopy
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.repositories.financial_repository import content_hash
from app.services.financial_import_audit import _observation_key, load_approved_sec_source
from app.services.normalization import NORMALIZATION_VERSION, extract_observations, normalize_company_facts


ROOT = Path(__file__).resolve().parents[2]
RETAINED_DIRECTORY = Path(os.getenv("FAIRWORTH_RETAINED_SEC_DIRECTORY", ROOT / ".phase67.local"))
# Frozen original-byte and normalized-payload identities from the approved
# eight-source import. Warning lists remain part of each normalized digest.
RETAINED_SOURCES = (
    ("MSFT", "0000789019", "f8aae2965b20ad0df44bdf7ccbedf797d275b6b8dc030154a7a311361bb7246f", "05d79b42c15f64b2ba6b6549e15eaa0770c4e62938b3bc7c46d0f53992895015"),
    ("NVDA", "0001045810", "19ef503a5770f5660964b3c3aea6937579d9b359da344afe6a9adf59c63d26ff", "1379edda5aefbd4d905b30a9aaa87e2ffc8b12fc18df3da70005cb1dbb8e2853"),
    ("ORCL", "0001341439", "65523545f040abaea1dfcf321da2a5aec85e7f34387244b0ffcb26e4c8707f7d", "4c3a929bd2fc4e2f32cd6f6c1c46e51b0303bd6821b1e7020903752168c32fdd"),
    ("JPM", "0000019617", "284d6f3ce6364f94216dddb45172203a825475f0bd75b633a2036b903181e902", "0e58fcdf9ccfbbad0c4c7ffd46c7ef0bbe7d030792af028d412c443163eabc72"),
    ("AMZN", "0001018724", "7549fb68446eee40e1f50a166fa06b2d2ee6349e07c8553a4828757e032d3cd4", "d6f7b3fe4375673a9e9c4ac697302398e7f85ab94fd2e17615a245dc75015ea6"),
    ("GOOGL", "0001652044", "a017f26ee88cb4a639d1c1ddb06d53b4afe22f0ac89cabec7cd67c88919fe1c5", "1d45148df0946ce7cc47efb0497a16cc146337ed8a594fba041bced101a71a58"),
    ("O", "0000726728", "676caac36e22f0d1087ec209f80728d2ab38536a1851d1f226daf27aaef44acb", "2f3d7f1e330b1a608a9a1b457aed61e33d9819a68e301ffb0217c7f808d39a0c"),
    ("PGR", "0000080661", "36a3229d38dd5d6c67968c481a413230070c351002f06350995a9cb113cf4d37", "a14e9f4127cab233372a53d8bcb69156ffc637bdfafc50bdfac195c7100e32d5"),
)


def reverse_object_keys(value):
    """Change JSON object insertion order without changing any source arrays."""
    if isinstance(value, dict):
        return {key: reverse_object_keys(item) for key, item in reversed(value.items())}
    if isinstance(value, list):
        return [reverse_object_keys(item) for item in value]
    return value


def warning_source():
    """Small independent sign/unit/ownership example with no usable period."""
    def fact(value, *, duration=False):
        result = {"val": value, "end": "2024-12-31", "fy": 2024, "fp": "FY",
                  "form": "10-K", "filed": "2025-02-15", "accn": "0000000001-25-000001"}
        if duration:
            result["start"] = "2024-01-01"
        return result

    return {"cik": 1, "entityName": "Synthetic warning-order fixture", "facts": {
        "dei": {},
        "us-gaap": {
            "CashAndCashEquivalentsAtCarryingValue": {"units": {
                "EUR": [fact(-10)], "USD": [fact(-20), fact(-30)]}},
            "ProfitLoss": {"units": {"USD": [fact(200, duration=True)]}},
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": {
                "units": {"USD": [fact(1000)]}},
            "WeightedAverageNumberOfDilutedSharesOutstanding": {
                "units": {"shares": [fact(0, duration=True)]}},
        },
    }}


def observation_identities(raw):
    # Multiplicity matters: equal observations must not disappear in a set.
    return Counter(_observation_key(observation) for observation in extract_observations(raw))


def assert_warning_contract(result):
    assert [(warning["field"], warning["code"]) for warning in result["warnings"]] == [
        ("cash_and_cash_equivalents", "incompatible_currency"),
        ("cash_and_cash_equivalents", "invalid_negative_value"),
        ("net_income", "unverified_ownership_basis"),
        ("shareholders_equity", "unverified_ownership_basis"),
        ("weighted_average_diluted_shares", "invalid_share_count"),
        ("financials", "missing_financial_data"),
    ]
    assert result["annual"] == result["quarterly"] == []


def test_first_seen_warnings_have_stable_order_across_object_permutations():
    raw = warning_source()
    original = deepcopy(raw)
    permuted = reverse_object_keys(raw)
    expected = normalize_company_facts(raw, cik="0000000001")
    actual = normalize_company_facts(permuted, cik="0000000001")
    assert_warning_contract(expected)
    assert actual == expected  # Includes exact warning order and multiplicity.
    assert content_hash(actual) == content_hash(expected)
    assert raw == original  # Normalization never rewrites original evidence.
    assert observation_identities(raw) == observation_identities(permuted)
    cash = raw["facts"]["us-gaap"]["CashAndCashEquivalentsAtCarryingValue"]["units"]["USD"]
    assert [fact["val"] for fact in cash] == [-20, -30]


def test_source_fact_array_order_remains_unchanged():
    raw = warning_source()
    before = deepcopy(raw)
    observations = extract_observations(raw)
    normalize_company_facts(raw)
    assert raw == before
    assert extract_observations(raw) == observations
    assert [observation["value"] for observation in observations[:3]] == [-10, -20, -30]


@pytest.fixture
def readonly_postgres():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Requires the existing dedicated PostgreSQL *_test database.")
    url = make_url(database_url)
    if (url.get_backend_name() != "postgresql" or not (url.database or "").endswith("_test")
            or url.host not in {"localhost", "127.0.0.1"}):
        pytest.fail("TEST_DATABASE_URL must identify a local dedicated PostgreSQL *_test database.")
    engine = create_engine(url, connect_args={
        "connect_timeout": 5, "options": "-c default_transaction_read_only=on -c statement_timeout=15000"})
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SHOW transaction_read_only")).scalar_one() == "on"
            yield connection
            connection.rollback()
    finally:
        engine.dispose()


def jsonb_roundtrip(connection, value):
    # Actual PostgreSQL JSONB object-key ordering; no table or source mutation.
    return connection.execute(text("SELECT CAST(:payload AS JSONB)"),
                              {"payload": json.dumps(value)}).scalar_one()


def test_small_warning_source_real_postgres_jsonb_roundtrip(readonly_postgres):
    raw = warning_source()
    roundtripped = jsonb_roundtrip(readonly_postgres, raw)
    assert list(roundtripped["facts"]["us-gaap"]) != list(raw["facts"]["us-gaap"])
    assert content_hash(roundtripped) == content_hash(raw)
    expected = normalize_company_facts(raw, cik="0000000001")
    actual = normalize_company_facts(roundtripped, cik="0000000001")
    assert_warning_contract(actual)
    assert actual == expected
    assert content_hash(actual) == content_hash(expected)
    assert observation_identities(roundtripped) == observation_identities(raw)


@pytest.mark.parametrize("ticker,cik,source_sha256,normalized_sha256", RETAINED_SOURCES,
                         ids=[row[0] for row in RETAINED_SOURCES])
def test_complete_retained_sec_source_real_jsonb_snapshot_integrity(
        readonly_postgres, ticker, cik, source_sha256, normalized_sha256):
    path = RETAINED_DIRECTORY / f"approved-sec-{ticker}-{cik}.json"
    manifest = RETAINED_DIRECTORY / "approved-sec-acquisition.json"
    if not path.is_file() or not manifest.is_file():
        pytest.skip("Optional original approved SEC capture is not retained on this machine.")
    raw, source = load_approved_sec_source(path, manifest)
    assert source["cik"] == cik
    assert source["sha256"] == source_sha256
    original = deepcopy(raw)
    expected = normalize_company_facts(raw, cik=cik)
    assert NORMALIZATION_VERSION == expected["normalization_version"] == 6
    assert content_hash(expected) == normalized_sha256

    roundtripped = jsonb_roundtrip(readonly_postgres, raw)
    assert content_hash(roundtripped) == source["canonical_payload_sha256"]
    assert observation_identities(roundtripped) == observation_identities(raw)
    actual = normalize_company_facts(roundtripped, cik=cik)
    assert actual == expected
    assert actual["warnings"] == expected["warnings"]
    assert actual["source_references"] == expected["source_references"]
    assert content_hash(actual) == normalized_sha256
    assert content_hash(jsonb_roundtrip(readonly_postgres, actual)) == normalized_sha256
    assert raw == original

