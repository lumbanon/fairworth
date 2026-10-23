"""Interpret the exact common-share declaration, never issuer cash totals.

The disclosure is a dated dividend baseline. It does not establish cash paid,
future payout sustainability, a current quote share basis, or a default DDM.
"""
from copy import deepcopy
from datetime import date
import math
import re

VERSION = "common-dividend-disclosure-1"
CONCEPT = "CommonStockDividendsPerShareDeclared"


def _day(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def common_dividend_disclosures(observations, annual_periods, cik):
    """Select full-year USD/common-share declarations with filing alignment.

    Latest unambiguous exact-period observations follow the existing normalized
    statement precedence. A selected accession must also support that annual
    statement; another fiscal period or an unrelated filing cannot fill a gap.
    """
    result = []
    identifier = str(cik or "").zfill(10)
    if not re.fullmatch(r"\d{10}", identifier):
        return {"version": VERSION, "cik": None, "annual_common_dividends": []}
    for period in annual_periods:
        if period.get("currency", "USD") != "USD":
            continue
        accessions = {record.get("accn") for records in period.get("provenance", {}).values()
                      for record in records if isinstance(record, dict)}
        selected = []
        for observation in observations:
            value, filed = observation.get("value"), _day(observation.get("filed"))
            if (observation.get("taxonomy") != "us-gaap" or observation.get("concept") != CONCEPT
                    or observation.get("unit") != "USD/shares" or observation.get("form") not in {"10-K", "10-K/A"}
                    or observation.get("start") != period.get("start_date")
                    or observation.get("end") != period.get("end_date")
                    or observation.get("accn") not in accessions
                    or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", str(observation.get("accn") or ""))
                    or filed is None or _day(observation.get("end")) is None
                    or filed < _day(observation["end"])
                    or isinstance(value, bool) or not isinstance(value, (float, int))
                    or not math.isfinite(value) or value < 0):
                continue
            selected.append(observation)
        if not selected:
            continue
        latest = max(record["filed"] for record in selected)
        candidates = [record for record in selected if record["filed"] == latest]
        amended = [record for record in candidates if record["form"] == "10-K/A"]
        candidates = amended or candidates
        if len({record["value"] for record in candidates}) != 1:
            continue
        value = candidates[0]["value"]
        sources = [dict(record, source="sec", cik=identifier,
                        economic_scope="declared_cash_dividend_per_common_share")
                   for record in candidates]
        result.append({"value": value, "unit": "USD/shares", "source_type": "reported",
                       "economic_scope": "declared_cash_dividend_per_common_share",
                       "period": {key: period.get(key) for key in ("fiscal_year", "fiscal_period", "start_date", "end_date")},
                       "provenance": deepcopy(sources),
                       "limitations": ["Declared common dividends are not a measurement of cash paid.",
                                        "Sustainability and future payment remain explicit scenario assumptions; buybacks are excluded."]})
    return {"version": VERSION, "cik": identifier, "annual_common_dividends": result}
