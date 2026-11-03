"""Tests for application-wide exception handlers."""

from http import HTTPStatus

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.application import (
    http_exception_handler,
    unhandled_exception_handler,
)
from app.errors import ApiErrorCode
from app.schemas.base import ErrorResponse


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "path": "/health",
            "raw_path": b"/health",
            "root_path": "",
            "scheme": "http",
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
    )


class TestHttpExceptionHandler:
    @pytest.mark.anyio
    async def test_structured_detail_preserves_error_code(self):
        response = await http_exception_handler(
            _request(),
            HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail={"code": ApiErrorCode.INVALID_REQUEST, "detail": "bad file"},
            ),
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        body = ErrorResponse.model_validate_json(bytes(response.body))
        assert body.error_code == ApiErrorCode.INVALID_REQUEST
        assert body.message == "bad file"
        assert body.details == {"code": ApiErrorCode.INVALID_REQUEST, "detail": "bad file"}

    @pytest.mark.anyio
    async def test_unknown_structured_code_falls_back_to_generic(self):
        detail = {"code": "NOT_AN_API_ERROR_CODE", "detail": "custom failure"}
        response = await http_exception_handler(
            _request(),
            HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=detail),
        )

        body = ErrorResponse.model_validate_json(bytes(response.body))
        assert body.error_code == ApiErrorCode.GENERIC_ERROR
        assert body.message == "custom failure"
        assert body.details == detail

    @pytest.mark.anyio
    async def test_structured_detail_without_message_uses_http_error(self):
        detail = {"code": ApiErrorCode.NOT_FOUND}
        response = await http_exception_handler(
            _request(),
            HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=detail),
        )

        body = ErrorResponse.model_validate_json(bytes(response.body))
        assert body.error_code == ApiErrorCode.NOT_FOUND
        assert body.message == "HTTP error"
        assert body.details == detail

    @pytest.mark.anyio
    async def test_plain_detail_uses_generic_error(self):
        response = await http_exception_handler(
            _request(),
            HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="missing"),
        )

        assert response.status_code == HTTPStatus.NOT_FOUND
        body = ErrorResponse.model_validate_json(bytes(response.body))
        assert body.error_code == ApiErrorCode.GENERIC_ERROR
        assert body.message == "HTTP error"
        assert body.details == "missing"


class TestUnhandledExceptionHandler:
    @pytest.mark.anyio
    async def test_returns_structured_internal_error(self):
        response = await unhandled_exception_handler(_request(), RuntimeError("boom"))

        assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        body = ErrorResponse.model_validate_json(bytes(response.body))
        assert body.error_code == ApiErrorCode.INTERNAL_ERROR
        assert body.message == "boom"
        assert body.details[0]["msg"] == "boom"

    @pytest.mark.anyio
    async def test_empty_exception_message_uses_class_name(self):
        response = await unhandled_exception_handler(_request(), RuntimeError())

        body = ErrorResponse.model_validate_json(bytes(response.body))
        assert body.error_code == ApiErrorCode.INTERNAL_ERROR
        assert body.message == "RuntimeError"
        assert body.details[0]["msg"] == "RuntimeError"
