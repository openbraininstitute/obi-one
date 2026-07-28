from types import SimpleNamespace
from unittest.mock import MagicMock

from app.dependencies.http_client import get_http_client


def test_get_http_client_returns_request_state_client():
    mock_client = MagicMock()
    request = SimpleNamespace(state=SimpleNamespace(http_client=mock_client))

    assert get_http_client(request) is mock_client
