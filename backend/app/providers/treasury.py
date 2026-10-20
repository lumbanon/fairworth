"""Dated US Treasury nominal ten-year par yields from the official XML feed.

Public GET feed documentation:
https://home.treasury.gov/treasury-daily-interest-rate-xml-feed
The ten-year maturity is a disclosed long-lived USD equity convention, not the
yield of a zero-coupon bond exactly matching each forecast cash flow.
"""
from datetime import UTC, date, datetime, timedelta
import math
from xml.etree import ElementTree

from app.providers.base import JsonHttpProvider, ProviderError


class TreasuryYieldProvider(JsonHttpProvider):
    name = "us-treasury"
    URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
    D = "{http://schemas.microsoft.com/ado/2007/08/dataservices}"
    M = "{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}"

    @classmethod
    def parse(cls, payload: str, as_of: date) -> list[dict]:
        if "<!DOCTYPE" in payload.upper() or "<!ENTITY" in payload.upper():
            raise ProviderError("invalid_provider_response", "The Treasury feed contains unsupported XML declarations.", 502)
        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError:
            raise ProviderError("invalid_provider_response", "The Treasury feed returned invalid XML.", 502) from None
        observations = {}
        for properties in root.iter(cls.M + "properties"):
            day_node, value_node = properties.find(cls.D + "NEW_DATE"), properties.find(cls.D + "BC_10YEAR")
            if day_node is None or value_node is None or value_node.get(cls.M + "null") == "true":
                continue
            try:
                day = date.fromisoformat((day_node.text or "")[:10])
                percent = float(value_node.text or "")
            except (ValueError, OverflowError):
                continue
            if day > as_of or not math.isfinite(percent) or not -5 <= percent <= 25:
                continue
            value = percent / 100
            if day in observations and observations[day]["value"] != value:
                raise ProviderError("invalid_provider_response", "The Treasury feed contains conflicting yields for one observation date.", 502)
            observations[day] = {"value": value, "unit": "fraction", "observation_date": day.isoformat(),
                                 "provider": cls.name, "source_provider": cls.name,
                                 "source_url": cls.URL, "source_type": "market_observation", "kind": "fact",
                                 "source_description": "US Treasury daily nominal ten-year par yield (BC_10YEAR).",
                                 "derivation_formula": "Published percentage yield / 100.",
                                 "methodology": "Ten-year nominal par yield used as a long-lived USD equity risk-free convention.",
                                 "maturity_years": 10, "applicable_market": "US", "currency": "USD"}
        return [observations[key] for key in sorted(observations)]

    async def risk_free_rate(self, as_of: date | None = None) -> dict:
        as_of = as_of or datetime.now(UTC).date()
        # A month-boundary weekend/holiday may have no observations yet.
        months = [as_of.replace(day=1), (as_of.replace(day=1) - timedelta(days=1)).replace(day=1)]
        for month in months:
            text = await self._text(self.URL,
                                    params={"data": "daily_treasury_yield_curve", "field_tdr_date_value_month": month.strftime("%Y%m")},
                                    headers={"Accept": "application/xml"})
            rows = self.parse(text, as_of)
            if rows:
                result = rows[-1]
                result["retrieved_at"] = datetime.now(UTC).isoformat()
                age = (as_of - date.fromisoformat(result["observation_date"])).days
                result["warnings"] = ["Treasury observation is older than seven calendar days."] if age > 7 else []
                result["state"] = "verified_zero" if result["value"] == 0 else "verified_value"
                return result
        raise ProviderError("missing_risk_free_rate", "No usable dated ten-year Treasury observation is available.", 503)
