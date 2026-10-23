"""Fail closed at shared/public boundaries; personal broker data stays local.

Derived records must retain their original source/permitted-use metadata. This
guard never strips a label to make a private record publishable.
"""
from collections.abc import Mapping

from app.providers.base import ProviderError


def require_public_data(value, provider=None):
    """Reject private observations, including nested evidence and derivations."""
    if str(provider or "").lower() in {"ibkr", "interactive_brokers"}:
        raise ProviderError("personal_market_data_restricted", "Personally licensed IBKR evidence is available only in the separate local research workflow.", 403)
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, Mapping):
            if (any(str(item.get(field, "")).lower() in {"ibkr", "interactive_brokers"} for field in ("provider", "source_provider"))
                    or item.get("permitted_use") == "personal_local_only"
                    or item.get("data_origin") in {"actual_ibkr", "simulated_ibkr"}
                    or item.get("public_redistribution_allowed") is False):
                require_public_data(None, "ibkr")
            pending.extend(item.values())
        elif isinstance(item, (list, tuple)):
            pending.extend(item)
    return value
