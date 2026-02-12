import json
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, create_autospec

import pytest
from _pytest.monkeypatch import MonkeyPatch

from app.dependencies.entitysdk import get_client
from app.services.morphology import convert_morphology

ROUTE = "/declared/register-morphology-with-calculated-metrics"

VIRTUAL_LAB_ID = "bf7d398c-b812-408a-a2ee-098f633f7798"
PROJECT_ID = "100a9a8a-5229-4f3d-aef3-6a4184c59e74"


@pytest.fixture(scope="module")
def monkeypatch_session():
    m = MonkeyPatch()
    yield m
    m.undo()


@pytest.fixture(autouse=True, scope="module")
def mock_heavy_dependencies(monkeypatch_session):
    mock_neurom = MagicMock()
    mock_neurom.load_morphology.return_value = MagicMock()
    sys.modules["neurom"] = mock_neurom
    yield
    if "neurom" in sys.modules:
        del sys.modules["neurom"]


@pytest.fixture(autouse=True)
def mock_template_and_functions(monkeypatch):
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


@pytest.fixture(autouse=True)
def mock_io_for_test(monkeypatch):
    mock_path_instance = MagicMock()
    mock_path_instance.unlink.return_value = None
    mock_path_instance.exists.return_value = True  # Changed to True to allow register_assets to run
    mock_path_instance.is_file.return_value = True
    mock_path_instance.__truediv__.return_value = mock_path_instance
    mock_path_instance.stem = "601506507_transformed"

    mock_path_for_validation = MagicMock()
    mock_suffix_mock = MagicMock()
    mock_suffix_mock.lower.return_value = ".swc"
    mock_path_for_validation.suffix = mock_suffix_mock

    def mock_path_constructor_final(path_str):
        if path_str == "601506507_transformed.swc":
            return mock_path_for_validation
        return mock_path_instance

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.pathlib.Path", mock_path_constructor_final
    )
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.Path", mock_path_constructor_final
    )


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


def test_morphology_registration_success(
    client,
    monkeypatch,
    mock_entity_payload,
    mock_measurement_list,
):
    mock_entity_id = uuid.uuid4()
    mock_measurement_id = uuid.uuid4()
    payload_morphology_name = json.loads(mock_entity_payload)["name"]
    expected_response_name = "601506507_transformed.swc"

    entitysdk_client_mock = MagicMock()
    client.app.dependency_overrides[get_client] = lambda: entitysdk_client_mock

    mock_registered_entity = MagicMock()
    mock_registered_entity.id = str(mock_entity_id)
    mock_registered_entity.name = payload_morphology_name

    mock_measurement_entity = MagicMock()
    mock_measurement_entity.id = str(mock_measurement_id)

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._run_morphology_analysis",
        lambda _: mock_measurement_list,
    )

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.register_morphology",
        lambda _client, _payload: mock_registered_entity,
    )

    mock_register_assets = MagicMock()
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.register_assets",
        mock_register_assets,
    )

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.register_measurements",
        lambda _client, _id, _list: mock_measurement_entity,
    )

    mock_convert_morphology = create_autospec(
        convert_morphology, return_value=["mock_converted_1.h5", "mock_converted_2.asc"]
    )

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.convert_morphology",
        mock_convert_morphology,
    )

    response = client.post(
        ROUTE,
        data={
            "metadata": mock_entity_payload,
        },
        files={
            "file": ("601506507_transformed.swc", b"mock swc content", "application/octet-stream")
        },
    )

    client.app.dependency_overrides.pop(get_client, None)

    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json["status"] == "success"
    assert resp_json["entity_id"] == str(mock_entity_id)
    assert resp_json["measurement_entity_id"] == str(mock_measurement_id)
    assert resp_json["morphology_name"] == expected_response_name

    assert mock_register_assets.call_count == 3