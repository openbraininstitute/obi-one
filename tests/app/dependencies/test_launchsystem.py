from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest

from app.dependencies.launchsystem import _resolve_launch_system_url
from app.errors import ApiError

VIRTUAL_LAB_ID = UUID("9c6fba01-2c6f-4eac-893f-f0dc665605c5")
LAUNCH_SYSTEM_URL = "https://staging.cell-X.openbraininstitute.org/api/launch-system"
LAUNCH_SYSTEM_URL_CELL_A = "https://staging.cell-a.openbraininstitute.org/api/launch-system"
LAUNCH_SYSTEM_URL_CELL_B = "https://staging.cell-b.openbraininstitute.org/api/launch-system"
VIRTUAL_LAB_API_URL = "http://my-vlab-api"


def _make_settings(launch_system_url=LAUNCH_SYSTEM_URL, vlab_api_url=VIRTUAL_LAB_API_URL):
    ns = SimpleNamespace(
        LAUNCH_SYSTEM_URL=launch_system_url,
        VIRTUAL_LAB_API_URL=vlab_api_url,
    )
    ns.get_virtual_lab_url = lambda vid: f"{ns.VIRTUAL_LAB_API_URL}/virtual-labs/{vid}"
    return ns


SETTINGS = _make_settings()


def _make_user_context(*, virtual_lab_id=None, token_credentials="fake-token"):
    token = SimpleNamespace(credentials=token_credentials)
    return SimpleNamespace(virtual_lab_id=virtual_lab_id, token=token)


def _vlab_response(compute_cell):
    """Build a virtual-lab-api response with the given compute_cell value."""
    return {
        "message": "Virtual lab",
        "data": {"virtual_lab": {"compute_cell": compute_cell}},
    }


class TestResolveLaunchSystemUrl:
    """Tests for _resolve_launch_system_url."""

    def test_no_placeholder_in_url(self, monkeypatch):
        """When the URL has no cell-X placeholder, it is returned as-is."""
        monkeypatch.setattr(
            "app.dependencies.launchsystem.settings",
            _make_settings(launch_system_url="http://127.0.0.1:8001"),
        )
        user_context = _make_user_context(virtual_lab_id=VIRTUAL_LAB_ID)
        result = _resolve_launch_system_url(user_context, httpx.Client())
        assert result == "http://127.0.0.1:8001"

    def test_no_virtual_lab_id_raises(self, monkeypatch):
        """When virtual_lab_id is not set and URL has placeholder, an error is raised."""
        monkeypatch.setattr("app.dependencies.launchsystem.settings", SETTINGS)
        user_context = _make_user_context(virtual_lab_id=None)
        with pytest.raises(ApiError, match="No virtual lab ID found"):
            _resolve_launch_system_url(user_context, httpx.Client())

    def test_compute_cell_a(self, monkeypatch, httpx_mock):
        """When compute_cell is CELL_A, the placeholder resolves to cell-a."""
        monkeypatch.setattr("app.dependencies.launchsystem.settings", SETTINGS)
        httpx_mock.add_response(
            url=f"{VIRTUAL_LAB_API_URL}/virtual-labs/{VIRTUAL_LAB_ID}",
            method="GET",
            json=_vlab_response("CELL_A"),
        )
        user_context = _make_user_context(virtual_lab_id=VIRTUAL_LAB_ID)
        result = _resolve_launch_system_url(user_context, httpx.Client())
        assert result == LAUNCH_SYSTEM_URL_CELL_A

    def test_compute_cell_b(self, monkeypatch, httpx_mock):
        """When compute_cell is CELL_B, the placeholder resolves to cell-b."""
        monkeypatch.setattr("app.dependencies.launchsystem.settings", SETTINGS)
        httpx_mock.add_response(
            url=f"{VIRTUAL_LAB_API_URL}/virtual-labs/{VIRTUAL_LAB_ID}",
            method="GET",
            json=_vlab_response("CELL_B"),
        )
        user_context = _make_user_context(virtual_lab_id=VIRTUAL_LAB_ID)
        result = _resolve_launch_system_url(user_context, httpx.Client())
        assert result == LAUNCH_SYSTEM_URL_CELL_B

    def test_unknown_compute_cell_raises(self, monkeypatch, httpx_mock):
        """When compute_cell is unrecognised, an error is raised."""
        monkeypatch.setattr("app.dependencies.launchsystem.settings", SETTINGS)
        httpx_mock.add_response(
            url=f"{VIRTUAL_LAB_API_URL}/virtual-labs/{VIRTUAL_LAB_ID}",
            method="GET",
            json=_vlab_response("UNKNOWN"),
        )
        user_context = _make_user_context(virtual_lab_id=VIRTUAL_LAB_ID)
        with pytest.raises(ApiError, match="Unknown compute cell: UNKNOWN"):
            _resolve_launch_system_url(user_context, httpx.Client())

    def test_api_failure_raises(self, monkeypatch, httpx_mock):
        """When the virtual-lab-api returns an error, it propagates."""
        monkeypatch.setattr("app.dependencies.launchsystem.settings", SETTINGS)
        httpx_mock.add_response(
            url=f"{VIRTUAL_LAB_API_URL}/virtual-labs/{VIRTUAL_LAB_ID}",
            method="GET",
            status_code=500,
        )
        user_context = _make_user_context(virtual_lab_id=VIRTUAL_LAB_ID)
        with pytest.raises(ApiError, match="HTTP status error 500"):
            _resolve_launch_system_url(user_context, httpx.Client())
