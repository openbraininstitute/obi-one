"""Tests for app.services.job — covers retry logic, error paths, and helpers."""

import json
from http import HTTPStatus
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from app.errors import ApiError, ApiErrorCode
from app.services.job import _parse_ls_error_code, stream_job

JOB_ID = uuid4()


def _mock_response(*, status_code=200, body="", is_success=True):
    """Build a mock httpx response for stream tests."""
    resp = AsyncMock()
    resp.status_code = status_code
    resp.is_success = is_success
    resp.aread = AsyncMock(return_value=body.encode())
    resp.aclose = AsyncMock()
    return resp


def _mock_client(send_side_effect):
    """Build a mock async client with a given send side effect."""
    client = AsyncMock()
    client.send = AsyncMock(side_effect=send_side_effect)
    client.build_request = httpx.Request
    return client


def test_parse_ls_error_code_valid():
    body = json.dumps({"error_code": "STREAM_NOT_FOUND", "message": "not found"})
    assert _parse_ls_error_code(body) == "STREAM_NOT_FOUND"


def test_parse_ls_error_code_missing_key():
    assert _parse_ls_error_code(json.dumps({"message": "oops"})) is None


def test_parse_ls_error_code_invalid_json():
    assert _parse_ls_error_code("not json") is None


def test_parse_ls_error_code_empty():
    assert _parse_ls_error_code("") is None


@pytest.mark.anyio
async def test_stream_job_connection_error():
    """RequestError raises ApiError with 500."""
    client = _mock_client(send_side_effect=httpx.ConnectError("refused"))

    with pytest.raises(ApiError) as exc_info:
        await stream_job(JOB_ID, client)

    assert exc_info.value.http_status_code == HTTPStatus.INTERNAL_SERVER_ERROR


@pytest.mark.anyio
async def test_stream_job_404_not_stream_not_found():
    """A 404 with a different error_code fails immediately (no retry)."""
    body = json.dumps({"error_code": "NOT_FOUND", "message": "job not found"})
    resp = _mock_response(status_code=404, body=body, is_success=False)
    client = _mock_client(send_side_effect=[resp])

    with pytest.raises(ApiError) as exc_info:
        await stream_job(JOB_ID, client)

    assert exc_info.value.http_status_code == HTTPStatus.NOT_FOUND
    assert exc_info.value.error_code == ApiErrorCode.NOT_FOUND
    # should only have been called once (no retry)
    assert client.send.call_count == 1


@pytest.mark.anyio
@patch("app.services.job._STREAM_RETRY_DELAY_S", 0)  # no sleep in tests
async def test_stream_job_retry_then_success():
    """STREAM_NOT_FOUND 404 is retried, then succeeds."""
    not_ready = _mock_response(
        status_code=404,
        body=json.dumps({"error_code": "STREAM_NOT_FOUND"}),
        is_success=False,
    )

    async def _lines():
        yield '{"msg":"hello"}'

    ready = AsyncMock()
    ready.status_code = 200
    ready.is_success = True
    ready.aiter_lines = _lines
    ready.aclose = AsyncMock()

    client = _mock_client(send_side_effect=[not_ready, ready])

    line_iter = await stream_job(JOB_ID, client)
    lines = [chunk async for chunk in line_iter]

    assert len(lines) == 1
    assert b"hello" in lines[0]
    assert client.send.call_count == 2


@pytest.mark.anyio
@patch("app.services.job._STREAM_MAX_RETRIES", 2)
@patch("app.services.job._STREAM_RETRY_DELAY_S", 0)
async def test_stream_job_retries_exhausted():
    """All retries return STREAM_NOT_FOUND — raises NOT_FOUND."""
    client = _mock_client(
        send_side_effect=[
            _mock_response(
                status_code=404,
                body=json.dumps({"error_code": "STREAM_NOT_FOUND"}),
                is_success=False,
            )
            for _ in range(2)
        ]
    )

    with pytest.raises(ApiError) as exc_info:
        await stream_job(JOB_ID, client)

    assert exc_info.value.http_status_code == HTTPStatus.NOT_FOUND
    assert client.send.call_count == 2
