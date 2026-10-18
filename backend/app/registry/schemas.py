"""Strict local import contract. A directory reference is not listing proof."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.providers.base import ProviderError, normalize_cik, validate_ticker


InstrumentType = Literal["unknown", "common_stock", "foreign_ordinary", "adr", "reit",
                         "financial_institution", "insurance", "etf", "closed_end_fund",
                         "preferred", "warrant", "right", "unit", "other"]


class RegistryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issuer_key: str | None = Field(default=None, max_length=180)
    instrument_key: str | None = Field(default=None, max_length=180)
    listing_key: str | None = Field(default=None, max_length=180)
    ticker: str = Field(max_length=16)
    name: str = Field(min_length=1, max_length=300)
    cik: str | None = None
    exchange: str | None = Field(default=None, max_length=100)
    exchange_mic: str | None = Field(default=None, max_length=12)
    instrument_type: InstrumentType = "unknown"
    listing_status: Literal["active", "inactive", "delisted", "unknown"] = "unknown"
    identity_status: Literal["verified", "reference_only", "ambiguous"] = "reference_only"
    share_class: str | None = Field(default=None, max_length=100)
    # Company aliases aid discovery. They are never security-symbol evidence.
    aliases: list[str] = Field(default_factory=list, max_length=100)
    symbol_aliases: list[str] = Field(default_factory=list, max_length=100)
    provider_symbols: dict[str, str] = Field(default_factory=dict)
    classification_evidence: dict = Field(default_factory=dict)
    adr_metadata: dict = Field(default_factory=dict)
    source_refs: list[dict] = Field(default_factory=list)
    valid_from: date | None = None
    valid_to: date | None = None

    @field_validator("ticker")
    @classmethod
    def canonical_ticker(cls, value):
        try:
            return validate_ticker(value)
        except ProviderError as error:
            raise ValueError(error.message) from None

    @field_validator("cik")
    @classmethod
    def canonical_cik(cls, value):
        try:
            return normalize_cik(value) if value else None
        except ProviderError as error:
            raise ValueError(error.message) from None

    @field_validator("aliases")
    @classmethod
    def clean_aliases(cls, values):
        return sorted({str(value).strip() for value in values if str(value).strip() and len(str(value)) <= 300})

    @field_validator("symbol_aliases")
    @classmethod
    def valid_symbol_aliases(cls, values):
        try:
            return sorted({validate_ticker(value) for value in values})
        except ProviderError as error:
            raise ValueError(error.message) from None


class RegistryProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=100)
    as_of: date
    source_url: str | None = None
    retrieved_at: datetime | None = None
    complete_scope: bool = False
    scope: str = "Reference records; active US equity coverage is not established."
    rights: str = "Importer must confirm permitted access and use."
    version: str = "1"
    notes: list[str] = Field(default_factory=list)
