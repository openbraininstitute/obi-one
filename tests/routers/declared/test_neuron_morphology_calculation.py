import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import UploadFile

from app.dependencies.entitysdk import get_client

ROUTE = "/declared/morphology-metrics-entity-registration"

VIRTUAL_LAB_ID = "bf7d398c-b812-408a-a2ee-098f633f7798"
PROJECT_ID = "100a9a8a-5229-4f3d-aef3-6a4184c59e74"


# === EARLY MONKEYPATCH: MOCK NEUROM + HEAVY IMPORTS ===
@pytest.fixture(autouse=True, scope="session")
def _early_patch_heavy_imports(monkeypatch):
    """
    Fully mock:
      - neurom (prevents NEURON/MPI loading)
      - template file
      - analysis dict creation
      - morphology processing
    """
    # 1. Mock the template file read
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

    def mock_read_text():
        return json.dumps(fake_template)

    monkeypatch.setattr(Path, "read_text", mock_read_text)

    # 2. Mock analysis dict creation
    def mock_create_analysis_dict(_template):
        return {
            "soma": {"mock_metric": lambda _: 42.0},
            "basal_dendrite": {"mock_metric": lambda _: 10.0},
        }

    monkeypatch.setattr(
        "app.endpoints.useful_functions.useful_functions.create_analysis_dict",
        mock_create_analysis_dict,
    )

    # 3. FULLY MOCK neurom (prevents NEURON/MPI import)
    mock_neurom = MagicMock()
    mock_neurom.load_morphology.return_value = MagicMock()
    monkeypatch.setattr("neurom", mock_neurom)
    monkeypatch.setattr("app.endpoints.morphology_metrics_calculation.nm", mock_neurom)

    # 4. Mock process_and_convert_morphology (avoids file I/O)
    def mock_process_and_convert():
        return "/mock/fake_output.swc", None

    monkeypatch.setattr(
        "app.endpoints.morphology_validation.process_and_convert_morphology",
        mock_process_and_convert,
    )


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
def mock_morphology_file():
    mock_file = MagicMock()
    upload_file = UploadFile(
        filename="test_morphology.swc",
        file=mock_file,
    )
    return upload_file


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
    mock_morphology_file,
):
    # Mock EntitySDK client
    entitysdk_client_mock = MagicMock()
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: entitysdk_client_mock)

    mock_entity_id = uuid.uuid4()
    expected_morphology_name = json.loads(mock_entity_payload)["name"]

    mock_registered_entity = MagicMock()
    mock_registered_entity.id = str(mock_entity_id)
    mock_registered_entity.name = expected_morphology_name

    # Mock analysis result
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._run_morphology_analysis",
        lambda _: mock_measurement_list,
    )

    # Mock entity registration
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.register_morphology",
        lambda _client, _payload: mock_registered_entity,
    )

    # Mock asset/measurement registration
    mock_register_assets_and_measurements = MagicMock()
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._register_assets_and_measurements",
        mock_register_assets_and_measurements,
    )

    # Configure file mock
    mock_morphology_file.filename = "601506507_transformed.swc"
    mock_morphology_file.file.read.return_value = b"mock swc content"

    # Make request
    response = client.post(
        ROUTE,
        data={
            "metadata": mock_entity_payload,
            "virtual_lab_id": VIRTUAL_LAB_ID,
            "project_id": PROJECT_ID,
        },
        files={"file": mock_morphology_file},
    )

    # Assertions
    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json["status"] == "success"
    assert resp_json["entity_id"] == str(mock_entity_id)
    assert resp_json["morphology_name"] == expected_morphology_name

    mock_register_assets_and_measurements.assert_called_once()
    args, _ = mock_register_assets_and_measurements.call_args
    assert args[1] == str(mock_entity_id)
    assert args[4] == mock_measurement_list
