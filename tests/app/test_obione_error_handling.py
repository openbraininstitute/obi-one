"""An OBIONEError raised while parsing a request body must not become a bare 500.

Block validators run during pydantic's parsing of the request body, before an endpoint's own
function body starts. An endpoint's own `try/except OBIONEError` around its own logic cannot see
these, and pydantic does not wrap `OBIONEError` into `RequestValidationError` the way it does
`ValueError`. Without the app-level handler this falls through to Starlette's default 500.
"""

from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from app.application import app

from tests.utils import AUTH_HEADER_USER_1, PROJECT_HEADERS


@pytest.fixture
def client(_override_check_user_info):
    """Test client with the real app, so the registered exception handler is exercised."""
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _grid_scan_config_with_invalid_recording_window() -> dict:
    """A CircuitSimulationSingleConfig whose recording fails `check_start_end_time`."""
    return {
        "type": "CircuitSimulationScanConfig",
        "initialize": {"circuit": None},
        "recordings": {
            "Window": {
                "type": "TimeWindowSomaVoltageRecording",
                "start_time": 60.0,
                "end_time": 20.0,
            }
        },
    }


def test_an_invalid_recording_window_is_reported_as_a_client_error(client):
    response = client.post(
        "/declared/scan_config/grid-scan-coordinate-count",
        json=_grid_scan_config_with_invalid_recording_window(),
        headers={**AUTH_HEADER_USER_1, **PROJECT_HEADERS},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    body = response.json()
    assert "End time must be later than start time" in body["message"]
