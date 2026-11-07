from collections.abc import Generator

import pytest

from tests.httpx_mock import HTTPXMock, mock_httpx


@pytest.fixture
def httpx_mock() -> Generator[HTTPXMock, None, None]:
    with mock_httpx() as mock:
        yield mock
