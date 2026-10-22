"""Currency requires exact dated source evidence; exchange membership is insufficient."""
from copy import deepcopy
from datetime import datetime

import pytest

from app.providers.currency import make_currency_evidence, resolve_quote_currency

CLOCK = "2026-10-21T14:30:00+00:00"
IDENTITY = {"ticker": "AAPL", "cik": "0000320193", "issuer_id": "synthetic-issuer", "instrument_id": "synthetic-instrument",
            "listing_id": "synthetic-listing", "exchange_mic": "XNAS"}


def inputs(currency="USD"):
    metadata = {"symbol": "AAPL", "cik": "0000320193", "exchange": "NASDAQ", "currency": currency}
    evidence = make_currency_evidence(metadata, IDENTITY, source_kind="provider_security_metadata", retrieved_at=CLOCK)
    quote = {"ticker": "AAPL", "provider": "fmp", "exchange": "NASDAQ", "price": 100, "currency": None, "price_timestamp": CLOCK, "retrieved_at": CLOCK}
    return quote, evidence


def test_exact_security_metadata_resolves_currency_without_changing_price_or_clocks():
    quote, evidence = inputs()
    original = deepcopy(quote)
    result = resolve_quote_currency(quote, IDENTITY, [evidence], as_of=CLOCK)
    assert result["currency"] == "USD" and result["currency_resolution"]["status"] == "verified"
    assert all(result[field] == original[field] for field in ("price", "price_timestamp", "retrieved_at"))
    assert quote == original


@pytest.mark.parametrize("change", ["listing", "venue", "hash", "stale", "issuer"])
def test_incompatible_or_expired_original_currency_is_not_accepted(change):
    quote, evidence = inputs()
    if change == "listing": evidence["listing_id"] = "wrong-listing"
    if change == "venue": evidence["mic"] = "XNYS"
    if change == "hash": evidence["original_record"]["currency"] = "EUR"
    if change == "stale": evidence.update(retrieved_at="2026-10-19T14:30:00+00:00", source_version_date="2026-10-19")
    if change == "issuer": evidence["issuer_id"] = "wrong-issuer"
    result = resolve_quote_currency(quote, IDENTITY, [evidence], as_of=CLOCK)
    assert result["currency"] is None and result["currency_resolution"]["status"] == "quote_currency_unverified"


def test_explicit_quote_unit_conflict_preserves_both_sources():
    quote, metadata = inputs("EUR")
    quote["currency"] = "USD"
    quote["currency_evidence"] = make_currency_evidence({"symbol": "AAPL", "currency": "USD", "exchange": "NASDAQ", "price": 100,
        "timestamp": datetime.fromisoformat(CLOCK).timestamp()}, IDENTITY, source_kind="provider_quote", retrieved_at=CLOCK)
    result = resolve_quote_currency(quote, IDENTITY, [metadata], as_of=CLOCK)
    assert result["currency"] is None and result["currency_resolution"]["status"] == "conflict"
    assert len(result["currency_resolution"]["evidence"]) == 2


def test_us_listing_and_usd_financials_never_supply_missing_quote_currency():
    quote, _ = inputs()
    result = resolve_quote_currency(quote, {**IDENTITY, "reporting_currency": "USD"}, as_of=CLOCK)
    assert result["currency"] is None and result["price"] == 100


@pytest.mark.parametrize("change", ["provider", "ticker", "exchange", "original_cik", "original_exchange"])
def test_direct_quote_currency_cannot_hide_incompatible_price_identity(change):
    quote, metadata = inputs()
    quote["currency"] = "USD"
    raw = {"symbol": "AAPL", "currency": "USD", "exchange": "NASDAQ", "cik": "0000320193", "price": 100,
           "timestamp": datetime.fromisoformat(CLOCK).timestamp()}
    if change == "provider": quote["provider"] = "unreviewed-provider"
    if change == "ticker": quote["ticker"] = "MSFT"
    if change == "exchange": quote["exchange"] = "NYSE"
    if change == "original_cik": raw["cik"] = "0000789019"
    if change == "original_exchange": raw["exchange"] = "NYSE"
    quote["currency_evidence"] = make_currency_evidence(raw, IDENTITY, source_kind="provider_quote", retrieved_at=CLOCK)
    result = resolve_quote_currency(quote, IDENTITY, [metadata], as_of=CLOCK)
    assert result["currency"] is None and result["currency_resolution"]["status"] == "quote_currency_unverified"
