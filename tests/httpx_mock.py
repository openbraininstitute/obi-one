"""Shared HTTPX mocks for standard httpx and EntitySDK's httpx2 client."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import parse_qsl, urlparse

import respx
from respx.mocks import HTTPCoreMocker

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    import httpx


class HTTPCore2Mocker(HTTPCoreMocker):
    """Teach respx how to intercept httpx2's httpcore implementation."""

    name = "httpcore2"
    targets: ClassVar[list[str]] = [
        "httpcore2._sync.connection.HTTPConnection",
        "httpcore2._sync.connection_pool.ConnectionPool",
        "httpcore2._sync.http_proxy.HTTPProxy",
        "httpcore2._async.connection.AsyncHTTPConnection",
        "httpcore2._async.connection_pool.AsyncConnectionPool",
        "httpcore2._async.http_proxy.AsyncHTTPProxy",
    ]


class HTTPXMock:
    """Expose the pytest-httpx API through standard httpx and httpx2 routers."""

    def __init__(self, routers: tuple[respx.Router, respx.Router]) -> None:
        self._routers = routers

    def add_response(
        self,
        status_code: int = 200,
        *,
        json: Any = None,
        content: bytes | str | None = None,
        text: str | None = None,
        headers: dict[str, str] | None = None,
        **matchers: Any,
    ) -> None:
        route_kwargs = self._route_kwargs(matchers)
        respond_kwargs: dict[str, Any] = {"status_code": status_code}
        if json is not None:
            respond_kwargs["json"] = json
        if content is not None:
            respond_kwargs["content"] = content
        if text is not None:
            respond_kwargs["text"] = text
        if headers is not None:
            respond_kwargs["headers"] = headers
        for router in self._routers:
            router.route(**route_kwargs).respond(**respond_kwargs)

    def add_callback(
        self,
        callback: Callable[[Any], httpx.Response],
        **matchers: Any,
    ) -> None:
        route_kwargs = self._route_kwargs(matchers)
        for router in self._routers:
            router.route(**route_kwargs).mock(side_effect=callback)

    def add_exception(self, exception: BaseException, **matchers: Any) -> None:
        route_kwargs = self._route_kwargs(matchers)
        for router in self._routers:
            router.route(**route_kwargs).mock(side_effect=exception)

    def get_requests(self, **matchers: Any) -> list[Any]:
        requests = [call.request for router in self._routers for call in router.calls]
        if method := matchers.get("method"):
            requests = [request for request in requests if request.method == method]
        if url := matchers.get("url"):
            requests = [request for request in requests if str(request.url) == str(url)]
        return requests

    def get_request(self, **matchers: Any) -> Any:
        requests = self.get_requests(**matchers)
        if len(requests) != 1:
            request_count = len(requests)
            msg = f"Expected one matching request, got {request_count}"
            raise AssertionError(msg)
        return requests[0]

    @staticmethod
    def _route_kwargs(matchers: dict[str, Any]) -> dict[str, Any]:
        matchers = dict(matchers)
        method = matchers.pop("method", None)
        url = matchers.pop("url", None)
        match_headers = matchers.pop("match_headers", None)
        match_json = matchers.pop("match_json", None)
        match_data = matchers.pop("match_data", None)
        match_files = matchers.pop("match_files", None)
        match_params = matchers.pop("match_params", None)
        # These pytest-httpx options are not needed by the current test suite.
        matchers.pop("is_optional", None)
        matchers.pop("is_reusable", None)
        matchers.pop("match_content", None)
        matchers.pop("match_extensions", None)
        matchers.pop("proxy_url", None)

        route_kwargs: dict[str, Any] = {}
        if method is not None:
            route_kwargs["method"] = method
        if url is not None:
            parsed = urlparse(str(url))
            route_kwargs["url"] = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                match_params = match_params or dict(parse_qsl(parsed.query))
        if match_params is not None:
            route_kwargs["params"] = match_params
        if match_headers is not None:
            route_kwargs["headers"] = match_headers
        if match_json is not None:
            route_kwargs["json"] = match_json
        if match_data is not None:
            route_kwargs["data"] = match_data
        if match_files is not None:
            route_kwargs["files"] = match_files
        return route_kwargs


@contextmanager
def mock_httpx() -> Iterator[HTTPXMock]:
    """Mock requests made through both HTTPX implementations."""
    with (
        respx.mock(using="httpcore", assert_all_called=False) as standard_router,
        respx.mock(using="httpcore2", assert_all_called=False) as entitysdk_router,
    ):
        yield HTTPXMock((standard_router, entitysdk_router))
