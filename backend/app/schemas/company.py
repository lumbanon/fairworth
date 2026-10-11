from pydantic import Field

from app.schemas.common import ApiModel, Envelope
from app.schemas.market import MarketQuote


class CompanyProfile(ApiModel):
    ticker: str
    name: str
    cik: str
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


class SearchResult(ApiModel):
    ticker: str
    name: str
    cik: str
    exchange: str | None = None


class SearchResponse(Envelope):
    results: list[SearchResult]
