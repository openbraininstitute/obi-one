from types import SimpleNamespace

import httpx
import pytest

from app.config import settings
from app.dependencies.launch_system import get_client


@pytest.fixture
def mock_user_context():
    return SimpleNamespace(token=SimpleNamespace(credentials="test-token"))


def test_get_client_returns_httpx_client(mock_user_context):
    client = get_client(mock_user_context)

    assert isinstance(client, httpx.Client)
    assert str(client.base_url) == settings.LAUNCH_SYSTEM_URL
    assert client.headers["Authorization"] == "Bearer test-token"


def test_get_client_sets_correct_headers(mock_user_context):
    client = get_client(mock_user_context)

    assert "Authorization" in client.headers
    assert client.headers["Authorization"] == "Bearer test-token"
