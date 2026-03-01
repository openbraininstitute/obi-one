from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Adjust this import to your actual module path
from app.dependencies import compute_cell as test_module
from app.errors import ApiError, ApiErrorCode


def test_get_compute_cell_success(monkeypatch):
    # Mock user context
    user_context = SimpleNamespace(
        virtual_lab_id="vlab-123",
        token=SimpleNamespace(credentials="fake-token"),
    )

    mock_http_client = MagicMock()
    request = SimpleNamespace(state=SimpleNamespace(http_client=mock_http_client))

    monkeypatch.setattr(
        test_module.settings.__class__,
        "get_virtual_lab_url",
        lambda _self, vlab_id: f"https://vlab.api/{vlab_id}",
    )

    # Mock make_http_request
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": {"virtual_lab": {"compute_cell": "cell_a"}}}

    monkeypatch.setattr(
        "app.dependencies.compute_cell.make_http_request",
        lambda *_args, **_kwargs: mock_response,
    )

    result = test_module.get_compute_cell(user_context, request)

    assert result == "cell_a"


def test_get_compute_cell_no_virtual_lab_id():
    user_context = SimpleNamespace(
        virtual_lab_id=None,
        token=SimpleNamespace(credentials="fake-token"),
    )

    request = SimpleNamespace(state=SimpleNamespace(http_client=MagicMock()))

    with pytest.raises(ApiError) as exc:
        test_module.get_compute_cell(user_context, request)

    assert exc.value.error_code == ApiErrorCode.INVALID_REQUEST
    assert exc.value.http_status_code == HTTPStatus.BAD_REQUEST
