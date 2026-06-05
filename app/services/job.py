import asyncio
import json
from collections.abc import AsyncIterator
from http import HTTPStatus
from uuid import UUID

import httpx

from app.errors import ApiError, ApiErrorCode
from app.logger import L
from app.schemas.job import JobRead
from app.utils.http import deserialize_response, make_http_request
from app.utils.redact import redact_sensitive

# stream retry settings: the launch-system stream may not be available
# immediately after job creation (Redis key not yet set up)
_STREAM_RETRY_DELAY_S = 2.0
_STREAM_MAX_RETRIES = 5  # up to ~10s of waiting

# launch-system error code indicating the stream metadata hasn't been
# created in Redis yet, this is a transient condition worth retrying
_LS_STREAM_NOT_FOUND = "STREAM_NOT_FOUND"


def read_job(job_id: UUID, ls_client: httpx.Client) -> JobRead:
    """Proxy GET /{job_id} to the launch-system and return deserialized job data."""
    response = make_http_request(
        url=f"/job/{job_id}",
        method="GET",
        http_client=ls_client,
    )
    return deserialize_response(response, model_class=JobRead)


def _parse_ls_error_code(body: str) -> str | None:
    """Extract the error_code from a launch-system JSON error response."""
    try:
        return json.loads(body).get("error_code")
    except (json.JSONDecodeError, AttributeError):
        return None


async def stream_job(job_id: UUID, ls_async_client: httpx.AsyncClient) -> AsyncIterator[bytes]:
    """Proxy GET /{job_id}/stream from the launch-system as NDJSON bytes.

    the launch-system stream endpoint returns STREAM_NOT_FOUND (404) when the
    redis stream metadata hasn't been created yet, this is transient and retried
    any other 404 (e.g. job doesn't exist) is returned immediately as NOT_FOUND
    """

    async def _open_stream() -> httpx.Response:
        """Try to open the stream, retrying only on STREAM_NOT_FOUND."""
        for attempt in range(_STREAM_MAX_RETRIES):
            try:
                response = await ls_async_client.send(
                    ls_async_client.build_request("GET", f"/job/{job_id}/stream"),
                    stream=True,
                )
            except httpx.RequestError as e:
                L.warning("Stream connection error for job %s: %r", job_id, e)
                raise ApiError(
                    message="Stream connection error",
                    error_code=ApiErrorCode.GENERIC_ERROR,
                    http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                ) from e

            if response.status_code == HTTPStatus.NOT_FOUND:
                body = (await response.aread()).decode(errors="replace")
                await response.aclose()
                ls_error_code = _parse_ls_error_code(body)

                if ls_error_code == _LS_STREAM_NOT_FOUND:
                    # stream metadata not in Redis yet, transient, retry
                    L.info(
                        "Stream not ready for job %s (attempt %d/%d)",
                        job_id,
                        attempt + 1,
                        _STREAM_MAX_RETRIES,
                    )
                    await asyncio.sleep(_STREAM_RETRY_DELAY_S)
                    continue

                # any other 404 (job not found, route not found), fail immediately
                raise ApiError(
                    message=f"Stream not found for job {job_id}",
                    error_code=ApiErrorCode.NOT_FOUND,
                    http_status_code=HTTPStatus.NOT_FOUND,
                    details=body,
                )

            if not response.is_success:
                await response.aclose()
                raise ApiError(
                    message=f"Launch-system stream error: {response.status_code}",
                    error_code=ApiErrorCode.GENERIC_ERROR,
                    http_status_code=HTTPStatus.BAD_GATEWAY,
                )

            return response

        # exhausted retries, stream never became available
        raise ApiError(
            message=f"Stream not ready for job {job_id} after {_STREAM_MAX_RETRIES} retries",
            error_code=ApiErrorCode.NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )

    response = await _open_stream()
    L.info("Stream opened for job %s (status %s)", job_id, response.status_code)

    async def _iter_lines() -> AsyncIterator[bytes]:
        try:
            async for line in response.aiter_lines():
                if line:
                    redacted = redact_sensitive(line)
                    yield redacted.encode("utf-8") + b"\n"
            L.info("Stream ended for job %s", job_id)
        finally:
            await response.aclose()

    return _iter_lines()
