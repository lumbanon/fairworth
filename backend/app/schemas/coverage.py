"""Coverage means independent capabilities, never a universal support claim."""
from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field

from app.schemas.common import ApiModel


class CoverageStage(ApiModel):
    model_config = ConfigDict(extra="allow")
    status: Literal["available", "missing_evidence", "provider_restricted", "not_supported",
                    "financially_inapplicable", "temporarily_unavailable", "identity_ambiguous"]
    reason: str
    reason_codes: list[str] = Field(default_factory=list)


class CoverageStages(ApiModel):
    symbol_resolution: CoverageStage
    classification: CoverageStage
    profile: CoverageStage
    statements: CoverageStage
    normalization: CoverageStage
    freshness: CoverageStage
    valuation: CoverageStage
    ai_research: CoverageStage


class CoverageResponse(ApiModel):
    identity: dict | None
    as_of: datetime
    methodology_version: str
    stages: CoverageStages
