from unittest.mock import Mock

import pytest


@pytest.fixture
def mock_db_client():
    return Mock()
