"""Tests for job proxy endpoints under /declared/task."""

import json
from http import HTTPStatus
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx

from app.application import app
from app.dependencies.launch_system import get_async_client
from app.errors import ApiError, ApiErrorCode

JOB_ID = uuid4()
PROJECT_ID = uuid4()
USER_ID = uuid4()

JOB_JSON = {
    "id": str(JOB_ID),
    "project_id": str(PROJECT_ID),
    "user_id": str(USER_ID),
    "status": "running",
    "error_reason": None,
    "start_time": "2024-01-01T00:00:00Z",
    "end_time": None,
    "logs": None,
    "inputs": None,
    "meta": None,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
}

_BASE = "/declared/task"


def _make_httpx_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    """Build a real httpx.Response with JSON content."""
    return httpx.Response(
        status_code=status_code,
        content=json.dumps(json_data).encode(),
        headers={"content-type": "application/json"},
    )


async def _async_line_generator(lines: list[str]):
    for line in lines:
        yield line


def _make_mock_async_client(mock_response):
    """Build a mock async client with send and build_request."""
    mock_client = AsyncMock()
    mock_client.send = AsyncMock(return_value=mock_response)
    mock_client.build_request = httpx.Request
    return mock_client


def test_read_job_success(client):
    """GET /declared/task/{job_id} returns 200 with correct JobRead fields."""
    mock_response = _make_httpx_response(JOB_JSON)

    with patch(
        "app.services.job.make_http_request",
        return_value=mock_response,
        autospec=True,
    ):
        resp = client.get(f"{_BASE}/{JOB_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(JOB_ID)
    assert data["project_id"] == str(PROJECT_ID)
    assert data["user_id"] == str(USER_ID)
    assert data["status"] == "running"


def test_read_job_launch_system_error(client):
    """GET /declared/task/{job_id} returns 500 when launch-system raises ApiError."""
    with patch(
        "app.services.job.make_http_request",
        side_effect=ApiError(
            message="HTTP status error 500",
            error_code=ApiErrorCode.GENERIC_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        ),
        autospec=True,
    ):
        resp = client.get(f"{_BASE}/{JOB_ID}")

    assert resp.status_code == 500
    data = resp.json()
    assert data["error_code"] == "GENERIC_ERROR"


def test_stream_job_success(client, monkeypatch):
    """GET /declared/task/{job_id}/stream returns 200 with NDJSON lines."""
    ndjson_lines = ['{"type":"log","msg":"hello"}', '{"type":"status","msg":"done"}']

    mock_response = AsyncMock()
    mock_response.is_success = True
    mock_response.status_code = 200
    mock_response.aiter_lines = lambda: _async_line_generator(ndjson_lines)
    mock_response.aclose = AsyncMock()

    async def override_get_async_client():
        yield _make_mock_async_client(mock_response)

    monkeypatch.setitem(app.dependency_overrides, get_async_client, override_get_async_client)

    resp = client.get(f"{_BASE}/{JOB_ID}/stream")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/x-ndjson"

    body_lines = resp.text.strip().split("\n")
    assert len(body_lines) == 2
    assert body_lines[0] == ndjson_lines[0]
    assert body_lines[1] == ndjson_lines[1]


def test_stream_job_launch_system_error(client, monkeypatch):
    """GET /declared/task/{job_id}/stream returns 502 when launch-system returns non-success."""
    mock_response = AsyncMock()
    mock_response.is_success = False
    mock_response.status_code = 500
    mock_response.aclose = AsyncMock()

    async def override_get_async_client():
        yield _make_mock_async_client(mock_response)

    monkeypatch.setitem(app.dependency_overrides, get_async_client, override_get_async_client)

    resp = client.get(f"{_BASE}/{JOB_ID}/stream")
    assert resp.status_code == 502
    data = resp.json()
    assert data["error_code"] == "GENERIC_ERROR"


def test_read_job_unauthenticated(client_no_auth):
    """GET /declared/task/{job_id} without auth headers returns 401 or 403."""
    resp = client_no_auth.get(f"{_BASE}/{JOB_ID}")
    assert resp.status_code in {401, 403}
