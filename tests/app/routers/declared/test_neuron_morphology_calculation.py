import json
import pathlib
import sys
import uuid
from http import HTTPStatus
from pathlib import Path
from unittest.mock import MagicMock, create_autospec

import pytest
import requests
from _pytest.monkeypatch import MonkeyPatch
from entitysdk.exception import EntitySDKError
from fastapi import HTTPException

from app.dependencies.entitysdk import get_client
from app.endpoints.morphology_metrics_calculation import (
    _get_h5_analysis_path,
    _validate_file_extension,
    register_morphology,
)
from app.services.morphology import validate_and_convert_morphology

ROUTE = "/declared/register-morphology-with-calculated-metrics"

VIRTUAL_LAB_ID = "bf7d398c-b812-408a-a2ee-098f633f7798"
PROJECT_ID = "100a9a8a-5229-4f3d-aef3-6a4184c59e74"


@pytest.fixture(scope="module")
def _monkeypatch_session():
    """Session-wide monkeypatch for module-scoped fixtures."""
    m = MonkeyPatch()
    yield m
    m.undo()


@pytest.fixture(autouse=True, scope="module")
def mock_heavy_dependencies(_monkeypatch_session):
    """
    Mock neurom to avoid heavy imports and potential environment issues.
    """
    mock_neurom = MagicMock()
    mock_neurom.load_morphology.return_value = MagicMock()
    sys.modules["neurom"] = mock_neurom
    yield
    if "neurom" in sys.modules:
        del sys.modules["neurom"]


@pytest.fixture(autouse=True)
def mock_template_and_functions(monkeypatch):
    """Mocks file system reads and core analysis functions."""
    fake_template = {
        "data": [
            {
                "entity_id": None,
                "entity_type": "reconstruction_morphology",
                "measurement_kinds": [
                    {
                        "structural_domain": "soma",
                        "pref_label": "mock_metric",
                        "measurement_items": [{"name": "raw", "unit": "μm", "value": 42.0}],
                    }
                ],
            }
        ],
        "pagination": {"page": 1, "page_size": 100, "total_items": 1},
        "facets": None,
    }

    original_read_text = Path.read_text

    def mock_read_text(self, *args, **kwargs):
        if "morphology_template.json" in str(self):
            return json.dumps(fake_template)
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", mock_read_text)

    def mock_create_analysis_dict(_template):
        return {"soma": {"mock_metric": lambda _: 42.0}}

    monkeypatch.setattr(
        "app.endpoints.useful_functions.useful_functions.create_analysis_dict",
        mock_create_analysis_dict,
    )

    mock_validate_and_convert_morphology = create_autospec(
        validate_and_convert_morphology, return_value=[Path("path0.h5"), Path("path1.swc")]
    )
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.validate_and_convert_morphology",
        mock_validate_and_convert_morphology,
    )


@pytest.fixture(autouse=True)
def mock_io_for_test(monkeypatch):
    """Mocks IO operations to prevent actual file creation during testing."""
    mock_file_handle = MagicMock()
    mock_file_handle.name = "/mock/temp_uploaded_file.swc"
    mock_file_handle.__enter__.return_value = mock_file_handle
    mock_file_handle.__exit__ = MagicMock(return_value=False)
    mock_file_handle.write.return_value = 100
    mock_file_handle.close.return_value = None

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.tempfile.NamedTemporaryFile",
        lambda *_args, **_kwargs: mock_file_handle,
    )

    real_path = pathlib.Path

    def _make_mock_path(path_str):
        real = real_path(path_str)
        mock_inst = MagicMock()
        mock_inst.unlink.return_value = None
        mock_inst.exists.return_value = True
        mock_inst.is_file.return_value = True
        mock_inst.suffix = real.suffix
        mock_inst.stem = real.stem
        mock_inst.name = real.name
        mock_inst.__str__ = lambda _self: str(real)
        mock_inst.__truediv__ = lambda _self, other: _make_mock_path(str(real / other))

        parent_mock = MagicMock()
        parent_mock.__str__ = lambda _self: str(real.parent)
        mock_inst.parent = parent_mock

        return mock_inst

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.pathlib.Path", _make_mock_path
    )
    monkeypatch.setattr("app.endpoints.morphology_metrics_calculation.Path", _make_mock_path)


@pytest.fixture
def mock_entity_payload():
    """Generates a valid metadata payload."""
    return json.dumps(
        {
            "name": "Test Morphology",
            "description": "Mock desc",
            "subject_id": str(uuid.uuid4()),
            "brain_region_id": str(uuid.uuid4()),
            "brain_location": [100.0, 200.0, 300.0],
        }
    )


def test_morphology_registration_success(client, monkeypatch, mock_entity_payload):
    mock_id = str(uuid.uuid4())
    entitysdk_client_mock = MagicMock()
    entitysdk_client_mock.register_entity.return_value = MagicMock(id=mock_id)
    entitysdk_client_mock.search_entity.return_value.one.return_value = None

    client.app.dependency_overrides[get_client] = lambda: entitysdk_client_mock
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._run_morphology_analysis", lambda _: []
    )

    response = client.post(
        ROUTE, data={"metadata": mock_entity_payload}, files={"file": ("test.swc", b"content")}
    )

    assert response.status_code == 200
    assert response.json()["entity_id"] == mock_id
    client.app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("filename", "content", "metadata", "expected_code"),
    [
        ("test.swc", b"", "{}", "BAD_REQUEST"),
        ("test.txt", b"content", "{}", "BAD_REQUEST"),
        ("test.swc", b"content", "{invalid}", "INVALID_METADATA"),
    ],
)
def test_validation_errors(client, filename, content, metadata, expected_code):
    response = client.post(ROUTE, data={"metadata": metadata}, files={"file": (filename, content)})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == expected_code


def test_internal_errors(client, monkeypatch, mock_entity_payload):
    def mock_fail(*_args, **_kwargs):
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": "MORPHOLOGY_ANALYSIS_ERROR",
                "detail": "Error during morphology analysis: Neurom error",
            },
        )

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._run_morphology_analysis", mock_fail
    )

    response = client.post(
        ROUTE, data={"metadata": mock_entity_payload}, files={"file": ("test.swc", b"content")}
    )

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "MORPHOLOGY_ANALYSIS_ERROR"


def test_sdk_registration_failure(client, monkeypatch, mock_entity_payload):
    mock_client = MagicMock()
    mock_client.register_entity.return_value = MagicMock(id="123")
    mock_client.upload_file.side_effect = requests.exceptions.RequestException("Upload fail")
    client.app.dependency_overrides[get_client] = lambda: mock_client
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._run_morphology_analysis", lambda _: []
    )

    response = client.post(
        ROUTE, data={"metadata": mock_entity_payload}, files={"file": ("test.swc", b"content")}
    )
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "ENTITYSDK_API_FAILURE"
    client.app.dependency_overrides.clear()


def test_meshing_failure_is_graceful(client, monkeypatch, mock_entity_payload):
    monkeypatch.setattr("app.endpoints.morphology_metrics_calculation.HAS_MESHING", True)
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._mesh_and_register",
        MagicMock(side_effect=Exception("Mesh error")),
    )
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._run_morphology_analysis", lambda _: []
    )

    mock_client = MagicMock()
    mock_client.register_entity.return_value = MagicMock(id=str(uuid.uuid4()))
    client.app.dependency_overrides[get_client] = lambda: mock_client

    response = client.post(
        ROUTE, data={"metadata": mock_entity_payload}, files={"file": ("test.swc", b"content")}
    )
    assert response.status_code == 200
    assert response.json()["mesh_asset_id"] is None
    client.app.dependency_overrides.clear()


def test_register_morphology_logic_variants():
    client = MagicMock()
    client.search_entity.side_effect = EntitySDKError("Search fail")

    payload = {"brain_location": [1.0], "subject_id": "sub123", "name": "test"}
    result = register_morphology(client, payload)
    assert result is not None


def test_utility_branch_coverage():
    with pytest.raises(HTTPException):
        _validate_file_extension("")

    path = _get_h5_analysis_path("original.h5", ".h5", "conv1.swc", "conv2.swc")
    assert path == "original.h5"
