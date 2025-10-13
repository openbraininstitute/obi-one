import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Any

import httpx
from fastapi import APIRouter, Depends, FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.dependencies.auth import user_verified
from app.endpoints.declared_endpoints import activate_declared_endpoints
from app.endpoints.generated_endpoints import (
    activate_generated_endpoints,
)
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from app.schemas.base import ErrorResponse


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[dict[str, Any]]:
    """Execute actions on server startup and shutdown."""
    L.info(
        "Starting application [PID=%s, CPU_COUNT=%s, ENVIRONMENT=%s]",
        os.getpid(),
        os.cpu_count(),
        settings.ENVIRONMENT,
    )
    http_client = httpx.Client()
    try:
        yield {
            "http_client": http_client,
        }
    except asyncio.CancelledError as err:
        # this can happen if the task is cancelled without sending SIGINT
        L.info("Ignored %s in lifespan", err)
    finally:
        http_client.close()
        L.info("Stopping application")


async def api_error_handler(request: Request, exception: ApiError) -> Response:
    """Handle API errors to be returned to the client."""
    err_content = ErrorResponse(
        message=exception.message,
        error_code=exception.error_code,
        details=exception.details,
    )
    L.warning("API error in %s %s: %s", request.method, request.url, err_content)
    return Response(
        media_type="application/json",
        status_code=int(exception.http_status_code),
        content=err_content.model_dump_json(),
    )


async def validation_exception_handler(
    request: Request, exception: RequestValidationError
) -> Response:
    """Override the default handler for RequestValidationError."""
    details = jsonable_encoder(exception.errors(), exclude={"input"})
    err_content = ErrorResponse(
        message="Validation error",
        error_code=ApiErrorCode.INVALID_REQUEST,
        details=details,
    )
    L.warning("Validation error in %s %s: %s", request.method, request.url, err_content)
    return Response(
        media_type="application/json",
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        content=err_content.model_dump_json(),
    )


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION or "0.0.0",
    debug=settings.APP_DEBUG,
    lifespan=lifespan,
    exception_handlers={
        ApiError: api_error_handler,
        RequestValidationError: validation_exception_handler,
    },
    root_path=settings.ROOT_PATH,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict:
    """Root endpoint."""
    return {
        "message": (
            f"Welcome to {settings.APP_NAME} {settings.APP_VERSION}. "
            f"See {settings.ROOT_PATH}/docs for OpenAPI documentation."
        )
    }


@app.get("/health")
async def health() -> dict:
    """Health endpoint."""
    return {
        "status": "OK",
    }


@app.get("/version")
async def version() -> dict:
    """Version endpoint."""
    return {
        "app_name": settings.APP_NAME,
        "app_version": settings.APP_VERSION,
        "commit_sha": settings.COMMIT_SHA,
    }


declared_endpoints_router = APIRouter(
    prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)]
)
app.include_router(activate_declared_endpoints(declared_endpoints_router))

generated_router = APIRouter(
    prefix="/generated", tags=["generated"], dependencies=[Depends(user_verified)]
)
app.include_router(activate_generated_endpoints(generated_router))
