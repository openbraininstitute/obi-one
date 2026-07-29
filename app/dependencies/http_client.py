from typing import Annotated

import httpx
from fastapi import Depends
from starlette.requests import Request


def get_http_client(request: Request) -> httpx.Client:
    """Get http_client."""
    return request.state.http_client


HttpClientDep = Annotated[httpx.Client, Depends(get_http_client)]
