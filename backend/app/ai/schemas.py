"""Strict generation contracts separate model prose from server-owned facts."""
from typing import Any, Literal
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, model_validator
from pydantic_core import PydanticCustomError
from app.ai.classification import ALLOWED_UNCERTAINTIES, CLASSIFICATION_INSTRUCTIONS, valid_classification
from app.valuation.schemas import ValuationRequest


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class QuantitativeClaim(Strict):
    evidence_id: str = Field(max_length=100)
    metric: str = Field(max_length=200)
    value: StrictInt | StrictFloat
    unit: str = Field(max_length=80)
    period: str | None
    derivation: str | None


class Finding(Strict):
    title: str = Field(min_length=1, max_length=160, description="Qualitative title only; quantities and source references belong in the explanation.")
    explanation: str = Field(min_length=1, max_length=1600,
        description="Use {{value:evidence_id}} for financial quantities/counts and {{date:evidence_id}} or {{period:evidence_id}} for source metadata. The server inserts validated values. Never type or invent numerical prose.")
    evidence_ids: list[str] = Field(max_length=12)
    category: Literal["reported_fact", "historical_metric", "valuation_output", "policy_estimate", "user_assumption", "filing_excerpt", "company_profile", "interpretation", "unavailable"] = Field(
        description="Classify the finding's evidence basis. AI inference is interpretation; policy/user/model estimates are never reported facts.")
    uncertainty: Literal["documented", "analytical", "limited", "unavailable"] = Field(
        description="Must be valid for the selected category. Documented describes sourced observations, never an AI interpretation, policy estimate, user assumption or valuation output.")
    quantitative_claims: list[QuantitativeClaim] = Field(max_length=12,
        description="Prefer an empty list with value bindings; the server fills exact canonical claims from their cited registry entries. Legacy explicit claims must match every source field exactly.")

    @model_validator(mode="after")
    def category_uncertainty_pair(self):
        if not valid_classification(self.category, self.uncertainty):
            raise PydanticCustomError("category_uncertainty_mismatch",
                                      "The category and uncertainty combination is not permitted.",
                                      {"category": self.category, "uncertainty": self.uncertainty})
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        # Nested anyOf is supported by strict structured outputs. Keep all
        # finding fields flat; no discriminator, oneOf, if/then or API change.
        schema = handler(core_schema)
        groups = {}
        for category, uncertainties in ALLOWED_UNCERTAINTIES.items():
            groups.setdefault(uncertainties, []).append(category)
        branches = []
        for uncertainties, categories in groups.items():
            # Describe common fields once, keeping the evidence input budget
            # available for source records rather than repeated schema prose.
            properties = {name: {key: value for key, value in field.items() if key not in {"title", "description"}}
                          for name, field in schema["properties"].items()}
            properties["category"] = {"type": "string", "enum": categories}
            properties["uncertainty"] = {"type": "string", "enum": list(uncertainties)}
            branches.append({"type": "object", "properties": properties,
                             "required": schema["required"], "additionalProperties": False})
        instructions = (CLASSIFICATION_INSTRUCTIONS + "\n" + cls.model_fields["explanation"].description
                        + "\n" + cls.model_fields["quantitative_claims"].description)
        return {"title": schema.get("title", "Finding"), "description": instructions, "anyOf": branches}


class ReportSections(Strict):
    executive_summary: list[Finding] = Field(min_length=1, max_length=4)
    business_overview: list[Finding] = Field(min_length=1, max_length=4)
    financial_analysis: list[Finding] = Field(min_length=1, max_length=6)
    valuation_analysis: list[Finding] = Field(min_length=1, max_length=6)
    risks: list[Finding] = Field(min_length=1, max_length=6)
    catalysts: list[Finding] = Field(min_length=1, max_length=4)
    bull_case: list[Finding] = Field(min_length=1, max_length=4)
    bear_case: list[Finding] = Field(min_length=1, max_length=4)
    valuation_drivers: list[Finding] = Field(min_length=1, max_length=4)
    data_limitations: list[Finding] = Field(min_length=1, max_length=6)


class ReportDraft(Strict):
    sections: ReportSections


class ChatDraft(Strict):
    answer: list[Finding] = Field(min_length=1, max_length=6)


class ReportRequest(Strict):
    valuation: ValuationRequest | None = None
    regenerate: bool = False


class ChatTurn(Strict):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(Strict):
    question: str = Field(min_length=1, max_length=1500)
    history: list[ChatTurn] = Field(default_factory=list, max_length=8)
    valuation: ValuationRequest | None = None


class EvidenceItem(Strict):
    id: str
    category: str
    provider: str | None
    title: str
    ticker: str
    metric: str
    value: Any
    unit: str
    period: str | None
    observation_date: str | None
    retrieved_at: str | None
    source_url: str | None
    accession: str | None
    derivation: str | None
    quality_warnings: list[str]
    excerpt: str | None


class ResearchStatus(Strict):
    enabled: bool
    configured: bool
    available: bool
    message: str
    limitations: list[str]


class ResearchResponse(Strict):
    ticker: str
    company_name: str
    generated_at: datetime
    financial_snapshot_id: str
    valuation_snapshot_id: str
    snapshot_dates: dict[str, Any]
    evidence_references: list[EvidenceItem]
    snapshot_token: str


class ResearchReport(ResearchResponse):
    sections: ReportSections
    quality_warnings: list[str]
    cache_status: Literal["hit", "miss"]


class ResearchAnswer(ResearchResponse):
    answer: list[Finding]
    limitations: list[str]
