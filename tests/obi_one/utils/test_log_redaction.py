import io
import logging

import httpx2
from entitysdk.exception import EntitySDKError
from entitysdk.utils.http import make_db_api_request

from obi_one.utils.log_redaction import RedactUrlQueries, redact_url_queries

SIGNED = "https://s3.example/circuit/a.hoc?X-Amz-Credential=AKIAX&X-Amz-Signature=secret"


def test_redact_url_queries_keeps_host_and_path():
    text = f"Client error '404 Not Found' for url '{SIGNED}'"
    assert redact_url_queries(text) == (
        "Client error '404 Not Found' for url 'https://s3.example/circuit/a.hoc?<redacted>'"
    )


def test_logged_storage_failure_has_no_signature():
    """entitysdk chains the HTTP error of the storage URL it was redirected to."""

    def storage(request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "entitycore":
            return httpx2.Response(307, headers={"location": SIGNED})
        return httpx2.Response(404)

    token_manager = type("TokenManager", (), {"get_token": lambda _: "token"})()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("test_log_redaction")
    logger.addHandler(handler)
    logger.addFilter(RedactUrlQueries())
    try:
        make_db_api_request(
            "http://entitycore/api/download",
            method="GET",
            token_manager=token_manager,
            http_client=httpx2.Client(transport=httpx2.MockTransport(storage)),
        )
    except EntitySDKError:
        logger.warning("Could not read %s", SIGNED, exc_info=True)
    finally:
        logger.removeHandler(handler)

    logged = stream.getvalue()
    assert "s3.example/circuit/a.hoc?<redacted>" in logged
    assert "HTTPStatusError" in logged
    assert "secret" not in logged
    assert "AKIAX" not in logged
