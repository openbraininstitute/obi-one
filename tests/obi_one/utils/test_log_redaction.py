import io
import logging
from collections.abc import Iterator

import httpx2
import pytest
from entitysdk.exception import EntitySDKError
from entitysdk.utils.http import make_db_api_request

from obi_one.utils.log_redaction import RedactUrlQueries, redact_url_queries

SIGNED = "https://s3.example/circuit/a.hoc?X-Amz-Credential=AKIAX&X-Amz-Signature=secret"


def test_redact_url_queries_keeps_host_and_path():
    text = f"Client error '404 Not Found' for url '{SIGNED}'"
    assert redact_url_queries(text) == (
        "Client error '404 Not Found' for url 'https://s3.example/circuit/a.hoc?<redacted>'"
    )


@pytest.fixture
def redacted_handler() -> Iterator[tuple[logging.Logger, io.StringIO]]:
    """A root handler with the filter, as ``app.application`` installs it; yields a logger
    that propagates to it, and the text the handler wrote."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RedactUrlQueries())
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield logging.getLogger("test_log_redaction"), stream
    finally:
        root.removeHandler(handler)


def test_logged_storage_failure_has_no_signature(redacted_handler):
    """entitysdk chains the HTTP error of the storage URL it was redirected to."""
    logger, stream = redacted_handler

    def storage(request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "entitycore":
            return httpx2.Response(307, headers={"location": SIGNED})
        return httpx2.Response(404)

    token_manager = type("TokenManager", (), {"get_token": lambda _: "token"})()
    try:
        make_db_api_request(
            "http://entitycore/api/download",
            method="GET",
            token_manager=token_manager,
            http_client=httpx2.Client(transport=httpx2.MockTransport(storage)),
        )
    except EntitySDKError:
        logger.warning("Could not read %s", SIGNED, exc_info=True)

    logged = stream.getvalue()
    assert "s3.example/circuit/a.hoc?<redacted>" in logged
    assert "HTTPStatusError" in logged
    assert "secret" not in logged
    assert "AKIAX" not in logged


def test_httpx2_request_log_has_no_signature(redacted_handler):
    """httpx2 logs every request URL at INFO on its own logger, including range reads."""
    _logger, stream = redacted_handler
    httpx2_logger = logging.getLogger("httpx2")
    level = httpx2_logger.level
    httpx2_logger.setLevel(logging.INFO)
    try:
        client = httpx2.Client(transport=httpx2.MockTransport(lambda _: httpx2.Response(206)))
        client.get(SIGNED, headers={"Range": "bytes=0-3"})
    finally:
        httpx2_logger.setLevel(level)

    logged = stream.getvalue()
    assert 'HTTP Request: GET https://s3.example/circuit/a.hoc?<redacted> "HTTP/1.1 206' in logged
    assert "secret" not in logged
