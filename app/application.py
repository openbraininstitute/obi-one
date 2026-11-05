import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Any

import httpx
from entitysdk.exception import EntitySDKError
from entitysdk.utils.http import HTTPClient as EntitySDKHTTPClient
from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.endpoints import (
    circuit_connectivity,
    circuit_customization,
    circuit_properties,
    circuit_registration,
    circuit_visualization,
    config_validation,
    contributor,
    count_scan_coordinates,
    distance_function_validation,
    electrical_cell_recording_properties,
    ephys_metrics,
    extracellular_locations,
    ion_channel_properties,
    mesh_registration,
    mesh_validation,
    morphology_locations,
    morphology_metrics,
    morphology_metrics_calculation,
    morphology_section_types,
    morphology_validation,
    multi_values,
    publication,
    scan_config,
    subject,
    task,
    validate_electrophysiology_protocol_nwb,
)
from app.endpoints.scan_config import activate_scan_config_endpoints
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from app.schemas.base import ErrorResponse
from obi_one.utils.log_redaction import RedactUrlQueries

# Configure logging here (not only in app/__main__) so the level applies in the uvicorn worker
# process too: under --reload the app runs in a spawned worker where __main__'s basicConfig never
# executed, leaving the root logger at WARNING and dropping DEBUG logs.
logging.basicConfig(level=settings.LOG_LEVEL, force=True)
# Presigned storage URLs carry their signature in the query string, and they reach the logs
# from more than one logger: httpx2 logs every request URL at INFO, and entitysdk's errors
# quote the URL they were redirected to. One filter on the root handler covers them all.
for root_handler in logging.getLogger().handlers:
    root_handler.addFilter(RedactUrlQueries())


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[dict[str, Any], None]:
    """Execute actions on server startup and shutdown."""
    L.info(
        "Starting application [PID=%s, CPU_COUNT=%s, ENVIRONMENT=%s]",
        os.getpid(),
        os.cpu_count(),
        settings.ENVIRONMENT,
    )
    http_client = httpx.Client()
    entitysdk_http_client = EntitySDKHTTPClient()
    try:
        yield {
            "http_client": http_client,
            "entitysdk_http_client": entitysdk_http_client,
        }
    except asyncio.CancelledError as err:
        # this can happen if the task is cancelled without sending SIGINT
        L.info("Ignored %s in lifespan", err)
    finally:
        entitysdk_http_client.close()
        http_client.close()  # ruff: ignore[blocking-http-call-httpx-in-async-function]
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


async def entity_sdk_error_handler(request: Request, exc: EntitySDKError) -> None:
    """Handle database client errors globally.

    Allows using the sdk anywhere in the service without having to handle EntitySDKError that are
    emitted explicitly if not needed.
    """
    L.exception(
        "EntitySDKError in %s %s",
        request.method,
        request.url,
    )
    raise ApiError(
        message=str(exc),
        error_code=ApiErrorCode.DATABASE_CLIENT_ERROR,
        http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
    ) from exc


def _error_response_for_http_detail(detail: Any) -> ErrorResponse:
    """Map an HTTPException detail into the shared ErrorResponse envelope.

    Endpoints often raise ``HTTPException`` with ``detail={"code": ..., "detail": ...}``.
    Prefer that structured code when it matches ``ApiErrorCode``; otherwise fall back to
    entitycore's GENERIC_ERROR + raw details shape.
    """
    if isinstance(detail, dict) and "code" in detail:
        try:
            error_code = ApiErrorCode(detail["code"])
        except ValueError:
            error_code = ApiErrorCode.GENERIC_ERROR
        message = str(detail.get("detail") or "HTTP error")
        return ErrorResponse(message=message, error_code=error_code, details=detail)

    return ErrorResponse(
        message="HTTP error",
        error_code=ApiErrorCode.GENERIC_ERROR,
        details=detail,
    )


async def http_exception_handler(request: Request, exception: StarletteHTTPException) -> Response:
    """Handle HTTP exceptions with the shared ErrorResponse envelope.

    Modeled on entitycore's StarletteHTTPException handler: log the failure and return a
    structured body instead of FastAPI's default ``{"detail": ...}`` payload.
    """
    err_content = _error_response_for_http_detail(exception.detail)
    L.warning("HTTP error in %s %s: %s", request.method, request.url, err_content)
    return Response(
        media_type="application/json",
        status_code=int(exception.status_code),
        content=err_content.model_dump_json(),
    )


async def unhandled_exception_handler(request: Request, exception: Exception) -> Response:
    """Return a structured 500 for otherwise-unhandled exceptions.

    Lets endpoints propagate server failures (for example ``OSError`` during file conversion)
    instead of catching them only to rebuild an HTTP 500 by hand.
    """
    message = str(exception) or exception.__class__.__name__
    err_content = ErrorResponse(
        message=message,
        error_code=ApiErrorCode.INTERNAL_ERROR,
        details=[{"type": "value_error", "loc": ["body"], "msg": message}],
    )
    L.exception("Unhandled error in %s %s: %s", request.method, request.url, err_content)
    return Response(
        media_type="application/json",
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
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
        EntitySDKError: entity_sdk_error_handler,
        StarletteHTTPException: http_exception_handler,
        Exception: unhandled_exception_handler,
    },  # ty:ignore[invalid-argument-type]
    root_path=settings.ROOT_PATH,
    strict_content_type=False,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
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


app.include_router(circuit_visualization.router)
app.include_router(circuit_connectivity.router)
app.include_router(circuit_customization.router)
app.include_router(circuit_registration.router)
app.include_router(circuit_properties.router)
app.include_router(config_validation.router)
app.include_router(distance_function_validation.router)
app.include_router(count_scan_coordinates.router)
app.include_router(electrical_cell_recording_properties.router)
app.include_router(ephys_metrics.router)
app.include_router(extracellular_locations.router)
app.include_router(ion_channel_properties.router)
app.include_router(circuit_visualization.memodel_router)
app.include_router(mesh_registration.router)
app.include_router(mesh_validation.router)
app.include_router(morphology_locations.router)
app.include_router(morphology_metrics.router)
app.include_router(morphology_section_types.router)
app.include_router(morphology_validation.router)
app.include_router(morphology_metrics_calculation.router)
app.include_router(multi_values.router)
app.include_router(validate_electrophysiology_protocol_nwb.router)
activate_scan_config_endpoints()
app.include_router(scan_config.router)
app.include_router(subject.router)
app.include_router(task.router)
app.include_router(publication.router)
app.include_router(contributor.router)
