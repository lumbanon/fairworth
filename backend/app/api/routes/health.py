from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text

from app.core.database import Base, utcnow
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
def health(request: Request):
    ready = False
    try:
        with request.app.state.session_factory() as session:
            session.execute(text("SELECT 1"))
            ready = set(Base.metadata.tables).issubset(inspect(session.connection()).get_table_names())
    except Exception:
        # Readiness output exposes no connection strings or driver details.
        pass
    payload = HealthResponse(status="ok" if ready else "unavailable", database="ready" if ready else "unavailable",
                             timestamp=utcnow()).model_dump(mode="json")
    return JSONResponse(payload, status_code=200 if ready else 503)
