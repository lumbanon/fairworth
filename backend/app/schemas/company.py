from pydantic import Field

from app.schemas.common import ApiModel, Envelope
from app.schemas.market import MarketQuote


class SecurityIdentity(ApiModel):
    issuer_id: str | None = None
    instrument_id: str | None = None
    listing_id: str | None = None
    display_symbol: str | None = Field(default=None, max_length=40)
    security_description: str | None = Field(default=None, max_length=1000)
    source_security_identifier: str | None = Field(default=None, max_length=300)
    exchange_mic: str | None = None
    instrument_type: str | None = None
    security_form: str | None = None
    issuer_business_category: str | None = None
    issuer_classification_evidence: dict = Field(default_factory=dict)
    listing_verification: dict = Field(default_factory=dict)
    issuer_linkage: dict = Field(default_factory=dict)
    filing_regime: str | None = None
    listing_status: str | None = None
    identity_status: str | None = None
    share_class: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    symbol_reassigned: bool = False
    registry_as_of: str | None = None
    registry_retrieved_at: str | None = None
    registry_version: str | None = None
    registry_status: str | None = None
    registry_warnings: list[dict] = Field(default_factory=list)
    aliases: list = Field(default_factory=list)
    symbol_aliases: list[str] = Field(default_factory=list)
    provider_symbols: dict = Field(default_factory=dict)
    classification_evidence: dict = Field(default_factory=dict)
    adr_metadata: dict = Field(default_factory=dict)
    source_refs: list[dict] = Field(default_factory=list)


class CompanyProfile(SecurityIdentity):
    ticker: str
    name: str
    cik: str | None = None
    exchange: str | None = None
    sector: str | None = None
    industry: str | None = None
    description: str | None = None
    currency: str | None = None
    is_bank: bool | None = None
    is_reit: bool | None = None
    has_multiple_share_classes: bool | None = None
    share_class_basis_verified: bool | None = None


class CompanyResponse(Envelope):
    company: CompanyProfile
    market: MarketQuote | None = None
    source_references: list[dict] = Field(default_factory=list)


class SearchResult(SecurityIdentity):
    ticker: str
    name: str
    cik: str | None = None
    exchange: str | None = None


class SearchResponse(Envelope):
    results: list[SearchResult]
    limit: int | None = None
    offset: int | None = None
    has_more: bool = False
    next_offset: int | None = None
    registry_as_of: str | None = None
    as_of: str | None = None
    registry_version: str | None = None
    registry_empty: bool = False
    registry_source: str | None = None
    coverage_scope: str | None = None
