import json
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
from _pytest.monkeypatch import MonkeyPatch
from fastapi import UploadFile

from app.dependencies.entitysdk import get_client

ROUTE = "/declared/morphology-metrics-entity-registration"

VIRTUAL_LAB_ID = "bf7d398c-b812-408a-a2ee-098f633f7798"
PROJECT_ID = "100a9a8a-5229-4f3d-aef3-6a4184c59e74"


# Add session-scoped monkeypatch fixture
@pytest.fixture(scope="module")
def monkeypatch_session():
    m = MonkeyPatch()
    yield m
    m.undo()


@pytest.fixture(autouse=True, scope="module")
def mock_heavy_dependencies(monkeypatch_session):  # noqa: ARG001
    """Mock heavy dependencies at module level before any imports."""
    # Mock neurom module
    mock_neurom = MagicMock()
    mock_neurom.load_morphology.return_value = MagicMock()
    sys.modules['neurom'] = mock_neurom
    
    yield
    
    # Cleanup
    if 'neurom' in sys.modules:
        del sys.modules['neurom']


@pytest.fixture(autouse=True)
def mock_template_and_functions(monkeypatch):
    """Mock template file and analysis functions."""
    fake_template = {
        "data": [
            {
                "entity_id": None,
                "entity_type": "reconstruction_morphology",
                "measurement_kinds": [
                    {
                        "structural_domain": "soma",
                        "pref_label": "mock_metric",
                        "measurement_items": [{"name": "raw", "unit": "μm", "value": None}],
                    }
                ],
            }
        ],
        "pagination": {"page": 1, "page_size": 100, "total_items": 1},
        "facets": None,
    }

    # Mock Path.read_text
    original_read_text = Path.read_text
    
    def mock_read_text(self, *args, **kwargs):  # noqa: ARG001
        if "morphology_template.json" in str(self):
            return json.dumps(fake_template)
        return original_read_text(self, *args, **kwargs)
    
    monkeypatch.setattr(Path, "read_text", mock_read_text)

    # Mock create_analysis_dict
    def mock_create_analysis_dict(_template):  # noqa: ARG001
        return {"soma": {"mock_metric": lambda _: 42.0}}

    monkeypatch.setattr(
        "app.endpoints.useful_functions.useful_functions.create_analysis_dict",
        mock_create_analysis_dict,
    )

    # Mock file processing
    async def mock_process_and_convert(temp_file_path, file_extension):  # noqa: ARG001
        return "/mock/fake.swc", None

    monkeypatch.setattr(
        "app.endpoints.morphology_validation.process_and_convert_morphology",
        mock_process_and_convert,
    )


# Add session-scoped monkeypatch fixture
@pytest.fixture(scope="module")
def monkeypatch_session():
    m = MonkeyPatch()
    yield m
    m.undo()


# --- Fixtures ---
@pytest.fixture
def mock_entity_payload():
    payload_data = {
        "name": "Test Morphology Analysis Name",
        "description": "Mock description for test run.",
        "subject_id": str(uuid.uuid4()),
        "brain_region_id": str(uuid.uuid4()),
        "brain_location": [100.0, 200.0, 300.0],
        "cell_morphology_protocol_id": str(uuid.uuid4()),
    }
    return json.dumps(payload_data)


@pytest.fixture
def mock_measurement_list():
    return [
        {"name": "total_length", "value": 500.0, "unit": "um", "domain": "soma"},
        {"name": "n_sections", "value": 10, "unit": "count", "domain": "apical_dendrite"},
    ]


# --- Test ---
def test_morphology_registration_success(
    client,
    monkeypatch,
    mock_entity_payload,
    mock_measurement_list,
):
    # Mock EntitySDK client
    entitysdk_client_mock = MagicMock()
    
    # Override the dependency
    def mock_get_client():
        return entitysdk_client_mock
    
    client.app.dependency_overrides[get_client] = mock_get_client

    mock_entity_id = uuid.uuid4()
    expected_morphology_name = json.loads(mock_entity_payload)["name"]

    mock_registered_entity = MagicMock()
    mock_registered_entity.id = str(mock_entity_id)
    mock_registered_entity.name = expected_morphology_name

    # Mock analysis
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._run_morphology_analysis",
        lambda _: mock_measurement_list,
    )

    # Mock registration
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.register_morphology",
        lambda _client, _payload: mock_registered_entity,
    )

    mock_register_assets_and_measurements = MagicMock()
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._register_assets_and_measurements",
        mock_register_assets_and_measurements,
    )

    # Request
    response = client.post(
        ROUTE,
        data={
            "metadata": mock_entity_payload,
            "virtual_lab_id": VIRTUAL_LAB_ID,
            "project_id": PROJECT_ID,
        },
        files={
            "file": (
                "601506507_transformed.swc",
                b"mock swc content",
                "application/octet-stream"
            )
        },
    )

    # Cleanup dependency override
    client.app.dependency_overrides.pop(get_client, None)

    # Assert
    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json["status"] == "success"
    assert resp_json["entity_id"] == str(mock_entity_id)
    assert resp_json["morphology_name"] == expected_morphology_name

    mock_register_assets_and_measurements.assert_called_once()
    args, _ = mock_register_assets_and_measurements.call_args
    assert args[1] == str(mock_entity_id)
    assert args[4] == mock_measurement_list
