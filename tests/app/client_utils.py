import functools

from httpx import Headers
from starlette.testclient import TestClient


class ClientProxy:
    """Proxy TestClient to pass default headers without creating a new instance.

    This can be used to avoid running the lifespan event multiple times.
    """

    def __init__(self, client: TestClient, headers: dict | None = None) -> None:
        self._client = client
        self._headers = headers
        self._methods = {"request", "get", "options", "head", "post", "put", "patch", "delete"}

    def __getattr__(self, name: str):
        def decorator(f):
            @functools.wraps(f)
            def wrapper(*args, headers=None, **kwargs):
                merged_headers = Headers(self._headers)
                merged_headers.update(headers)
                return f(*args, headers=merged_headers, **kwargs)

            return wrapper

        method = getattr(self._client, name)
        return decorator(method) if name in self._methods else method
