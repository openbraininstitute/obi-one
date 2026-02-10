from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest

from app.dependencies.launchsystem import _resolve_launch_system_url

VIRTUAL_LAB_ID = UUID("9c6fba01-2c6f-4eac-893f-f0dc665605c5")
LAUNCH_SYSTEM_URL = "https://staging.cell-a.openbraininstitute.org/api/launch-system"
VIRTUAL_LAB_API_URL = "http://my-vlab-api"


def _make_user_context(*, virtual_lab_id=None, token_credentials="fake-token"):
    token = SimpleNamespace(credentials=token_credentials)
    return SimpleNamespace(virtual_lab_id=virtual_lab_id, token=token)


class TestResolveLaunchSystemUrl:
    """Tests for _resolve_launch_system_url."""

    def test_no_virtual_lab_id(self, monkeypatch):
        """When virtual_lab_id is not set, the default URL is returned."""
        monkeypatch.setattr(
            "app.dependencies.launchsystem.settings",
            SimpleNamespace(
                LAUNCH_SYSTEM_URL=LAUNCH_SYSTEM_URL,
                VIRTUAL_LAB_API_URL=VIRTUAL_LAB_API_URL,
            ),
        )
        user_context = _make_user_context(virtual_lab_id=None)
        result = _resolve_launch_system_url(user_context, httpx.Client())
        assert result == LAUNCH_SYSTEM_URL

    def test_compute_cell_a(self, monkeypatch, httpx_mock):
        """When compute_cell is CELL_A, the default URL (cell-a) is returned."""
        monkeypatch.setattr(
            "app.dependencies.launchsystem.settings",
            SimpleNamespace(
                LAUNCH_SYSTEM_URL=LAUNCH_SYSTEM_URL,
                VIRTUAL_LAB_API_URL=VIRTUAL_LAB_API_URL,
            ),
        )
        httpx_mock.add_response(
            url=f"{VIRTUAL_LAB_API_URL}/virtual-labs/{VIRTUAL_LAB_ID}",
            method="GET",
            json={
                "message": "Virtual lab",
                "data": {
                    "virtual_lab": {
                        "compute_cell": "CELL_A",
                    }
                },
            },
        )
        user_context = _make_user_context(virtual_lab_id=VIRTUAL_LAB_ID)
        result = _resolve_launch_system_url(user_context, httpx.Client())
        assert result == LAUNCH_SYSTEM_URL

    @pytest.mark.parametrize("compute_cell_value", ["CELL_B", "cell_b"])
    def test_compute_cell_b(self, monkeypatch, httpx_mock, compute_cell_value):
        """When compute_cell is CELL_B, cell-a is replaced with cell-b in the URL."""
        monkeypatch.setattr(
            "app.dependencies.launchsystem.settings",
            SimpleNamespace(
                LAUNCH_SYSTEM_URL=LAUNCH_SYSTEM_URL,
                VIRTUAL_LAB_API_URL=VIRTUAL_LAB_API_URL,
            ),
        )
        httpx_mock.add_response(
            url=f"{VIRTUAL_LAB_API_URL}/virtual-labs/{VIRTUAL_LAB_ID}",
            method="GET",
            json={
                "message": "Virtual lab",
                "data": {
                    "virtual_lab": {
                        "compute_cell": compute_cell_value,
                    }
                },
            },
        )
        user_context = _make_user_context(virtual_lab_id=VIRTUAL_LAB_ID)
        result = _resolve_launch_system_url(user_context, httpx.Client())
        assert result == "https://staging.cell-b.openbraininstitute.org/api/launch-system"

    def test_compute_cell_not_set(self, monkeypatch, httpx_mock):
        """When compute_cell is missing from the response, the default URL is returned."""
        monkeypatch.setattr(
            "app.dependencies.launchsystem.settings",
            SimpleNamespace(
                LAUNCH_SYSTEM_URL=LAUNCH_SYSTEM_URL,
                VIRTUAL_LAB_API_URL=VIRTUAL_LAB_API_URL,
            ),
        )
        httpx_mock.add_response(
            url=f"{VIRTUAL_LAB_API_URL}/virtual-labs/{VIRTUAL_LAB_ID}",
            method="GET",
            json={
                "message": "Virtual lab",
                "data": {
                    "virtual_lab": {},
                },
            },
        )
        user_context = _make_user_context(virtual_lab_id=VIRTUAL_LAB_ID)
        result = _resolve_launch_system_url(user_context, httpx.Client())
        assert result == LAUNCH_SYSTEM_URL

    def test_api_failure_returns_default_url(self, monkeypatch, httpx_mock):
        """When the virtual-lab-api call fails, the default URL is returned."""
        monkeypatch.setattr(
            "app.dependencies.launchsystem.settings",
            SimpleNamespace(
                LAUNCH_SYSTEM_URL=LAUNCH_SYSTEM_URL,
                VIRTUAL_LAB_API_URL=VIRTUAL_LAB_API_URL,
            ),
        )
        httpx_mock.add_response(
            url=f"{VIRTUAL_LAB_API_URL}/virtual-labs/{VIRTUAL_LAB_ID}",
            method="GET",
            status_code=500,
        )
        user_context = _make_user_context(virtual_lab_id=VIRTUAL_LAB_ID)
        result = _resolve_launch_system_url(user_context, httpx.Client())
        assert result == LAUNCH_SYSTEM_URL

    def test_network_error_returns_default_url(self, monkeypatch):
        """When there's a network error, the default URL is returned."""
        monkeypatch.setattr(
            "app.dependencies.launchsystem.settings",
            SimpleNamespace(
                LAUNCH_SYSTEM_URL=LAUNCH_SYSTEM_URL,
                VIRTUAL_LAB_API_URL="http://unreachable:9999",
            ),
        )
        user_context = _make_user_context(virtual_lab_id=VIRTUAL_LAB_ID)
        result = _resolve_launch_system_url(user_context, httpx.Client())
        assert result == LAUNCH_SYSTEM_URL
