"""No arbitrary URLs, tools, database writes, or caller-selected AI models."""
from fastapi import APIRouter, Depends, Query, Request
from app.api.dependencies import Ticker
from app.ai.schemas import ReportRequest, ChatRequest, ResearchStatus, ResearchReport, ResearchAnswer, EvidenceItem

router = APIRouter(prefix="/stocks", tags=["AI research"])


def service(request: Request):
    return request.app.state.research_service


def owner(request: Request, research=Depends(service)):
    address = request.client.host if request.client else "unknown"
    identity = research.limits.identity(request.headers.get("x-fairworth-session"), address)
    research.limits.throttle(identity, address)
    return identity


@router.get("/{ticker}/ai/status", response_model=ResearchStatus)
async def status(ticker: Ticker, research=Depends(service)):
    return research.status()


@router.post("/{ticker}/ai/report", response_model=ResearchReport)
async def report(ticker: Ticker, body: ReportRequest, identity=Depends(owner), research=Depends(service),
                 instrument_id: str | None = Query(default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9:_-]+$"),
                 listing_id: str | None = Query(default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9:_-]+$")):
    scope = {key: value for key, value in (("instrument_id", instrument_id), ("listing_id", listing_id)) if value is not None}
    return await research.report(ticker.upper(), body, identity, **scope)


@router.post("/{ticker}/ai/chat", response_model=ResearchAnswer)
async def chat(ticker: Ticker, body: ChatRequest, identity=Depends(owner), research=Depends(service),
               instrument_id: str | None = Query(default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9:_-]+$"),
               listing_id: str | None = Query(default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9:_-]+$")):
    scope = {key: value for key, value in (("instrument_id", instrument_id), ("listing_id", listing_id)) if value is not None}
    return await research.chat(ticker.upper(), body, identity, **scope)


@router.get("/{ticker}/ai/evidence/{evidence_id}", response_model=EvidenceItem)
async def evidence(ticker: Ticker, evidence_id: str, snapshot_token: str = Query(min_length=20, max_length=100), identity=Depends(owner), research=Depends(service),
                   instrument_id: str | None = Query(default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9:_-]+$"),
                   listing_id: str | None = Query(default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9:_-]+$")):
    scope = {key: value for key, value in (("instrument_id", instrument_id), ("listing_id", listing_id)) if value is not None}
    return research.evidence(ticker.upper(), evidence_id, snapshot_token, identity, **scope)
