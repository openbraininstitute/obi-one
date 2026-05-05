import json
import sys
import uuid
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

ROUTE = "/declared/register-morphology-with-calculated-metrics"  # [cite: 2]

VIRTUAL_LAB_ID = "bf7d398c-b812-408a-a2ee-098f633f7798"  # [cite: 2]
PROJECT_ID = "100a9a8a-5229-4f3d-aef3-6a4184c59e74"  # [cite: 2]


@pytest.fixture(scope="module")
def monkeypatch_session():  # [cite: 2]
    m = MonkeyPatch()
    yield m
    m.undo()


@pytest.fixture(autouse=True, scope="module")
def mock_heavy_dependencies(_monkeypatch_session):  # [cite: 2]
    mock_neurom = MagicMock()
    mock_neurom.load_morphology.return_value = MagicMock()
    sys.modules["neurom"] = mock_neurom
    yield
    if "neurom" in sys.modules:
        del sys.modules["neurom"]


@pytest.fixture(autouse=True)
def mock_template_and_functions(monkeypatch):  # [cite: 2]
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
def mock_io_for_test(monkeypatch):  # [cite: 2]
    mock_file_handle = MagicMock()
    mock_file_handle.name = "/mock/temp_uploaded_file.swc"
    mock_file_handle.__enter__.return_value = mock_file_handle
    mock_file_handle.write.return_value = 100
    mock_file_handle.close.return_value = None

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.tempfile.NamedTemporaryFile",
        lambda *_args, **_kwargs: mock_file_handle,
    )

    mock_path_instance = MagicMock()
    mock_path_instance.unlink.return_value = None
    mock_path_instance.exists.return_value = True
    mock_path_instance.is_file.return_value = True
    mock_path_instance.suffix = ".swc"
    mock_path_instance.parent = mock_path_instance
    mock_path_instance.name = "mock_file.swc"
    mock_path_instance.__truediv__.return_value = mock_path_instance

    def mock_path_constructor_final(_path_str):
        return mock_path_instance

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.pathlib.Path", mock_path_constructor_final
    )
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.Path", mock_path_constructor_final
    )


@pytest.fixture
def mock_entity_payload():  # [cite: 2]
    return json.dumps(
        {
            "name": "Test Morphology",
            "description": "Mock desc",
            "subject_id": str(uuid.uuid4()),
            "brain_region_id": str(uuid.uuid4()),
            "brain_location": [100.0, 200.0, 300.0],
        }
    )


def test_morphology_registration_success(client, monkeypatch, mock_entity_payload):  # [cite: 2]
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
    [  # [cite: 1]
        ("test.swc", b"", "{}", "BAD_REQUEST"),
        ("test.txt", b"content", "{}", "BAD_REQUEST"),
        ("test.swc", b"content", "{invalid}", "INVALID_METADATA"),
    ],
)
def test_validation_errors(client, filename, content, metadata, expected_code):  # [cite: 1]
    response = client.post(ROUTE, data={"metadata": metadata}, files={"file": (filename, content)})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == expected_code


def test_internal_errors(client, monkeypatch, mock_entity_payload):  # [cite: 1]
    def mock_fail(*_args, **_kwargs):
        msg = "Neurom error"
        raise RuntimeError(msg)

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._run_morphology_analysis", mock_fail
    )

    response = client.post(
        ROUTE, data={"metadata": mock_entity_payload}, files={"file": ("test.swc", b"content")}
    )
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "MORPHOLOGY_ANALYSIS_ERROR"


def test_sdk_registration_failure(client, monkeypatch, mock_entity_payload):  # [cite: 1]
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


def test_meshing_failure_is_graceful(client, monkeypatch, mock_entity_payload):  # [cite: 1]
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


def test_register_morphology_logic_variants():  # [cite: 1]
    client = MagicMock()
    client.search_entity.side_effect = EntitySDKError("Search fail")

    # Test entity search failure and short brain location
    payload = {"brain_location": [1.0], "subject_id": "sub123", "name": "test"}
    result = register_morphology(client, payload)
    assert result is not None


def test_utility_branch_coverage():  # [cite: 1]
    # Cover _validate_file_extension empty filename
    with pytest.raises(HTTPException):
        _validate_file_extension("")

    # Cover _get_h5_analysis_path branch for .h5 extension
    path = _get_h5_analysis_path("original.h5", ".h5", "conv1.swc", "conv2.swc")
    assert path == "original.h5"
