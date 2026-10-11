from typing import Annotated

from fastapi import Path, Request

Ticker = Annotated[str, Path(min_length=1, max_length=10, pattern=r"^[A-Za-z][A-Za-z0-9]*(?:[.-][A-Za-z0-9]+)?$")]


def company_service(request: Request):
    return request.app.state.company_service


def financial_service(request: Request):
    return request.app.state.financial_service
