import json
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, create_autospec

import pytest
from _pytest.monkeypatch import MonkeyPatch

from app.dependencies.entitysdk import get_client
from app.services.morphology import validate_and_convert_morphology

ROUTE = "/declared/register-morphology-with-calculated-metrics"

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
    sys.modules["neurom"] = mock_neurom

    yield

    # Cleanup
    if "neurom" in sys.modules:
        del sys.modules["neurom"]


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

    def mock_read_text(self, *args, **kwargs):
        if "morphology_template.json" in str(self):
            return json.dumps(fake_template)
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", mock_read_text)

    # Mock create_analysis_dict
    def mock_create_analysis_dict(_template):
        return {"soma": {"mock_metric": lambda _: 42.0}}

    monkeypatch.setattr(
        "app.endpoints.useful_functions.useful_functions.create_analysis_dict",
        mock_create_analysis_dict,
    )

    mock_validate_and_convert_morphology = create_autospec(
        validate_and_convert_morphology, return_value=[Path("path0"), Path("path1")]
    )

    # FIX: Patch directly in the calling module to ensure correct mocking
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.validate_and_convert_morphology",
        mock_validate_and_convert_morphology,
    )


# 🌟 FINAL, ROBUST I/O MOCKING FIXTURE
@pytest.fixture(autouse=True)
def mock_io_for_test(monkeypatch):
    """
    Guarantees tempfile and pathlib are mocked before the endpoint logic executes,
    preventing 500 errors from unhandled OS exceptions during cleanup.
    """
    # 1. Mock tempfile.NamedTemporaryFile
    mock_file_handle = MagicMock()
    # FIX S108: Use a non-file path string to avoid linting warning
    mock_file_handle.name = "/mock/temp_uploaded_file.swc"
    mock_file_handle.__enter__.return_value = mock_file_handle

    # Explicitly set the write and close return values
    mock_file_handle.write.return_value = 100  # Mock a successful write of 100 bytes
    mock_file_handle.close.return_value = None  # Mock close

    # FIX ARG005: Use *_args to silence unused argument warning
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.tempfile.NamedTemporaryFile",
        lambda *_args, **_kwargs: mock_file_handle,
    )

    # 2. Mock Path constructor for cleanup/I/O calls
    mock_path_instance = MagicMock()
    mock_path_instance.unlink.return_value = None  # Prevents OS error during cleanup
    mock_path_instance.exists.return_value = False
    mock_path_instance.is_file.return_value = False  # Prevents file checks from failing

    # 3. Mock Path constructor for validation call: Path("filename.swc").suffix.lower()
    mock_path_for_validation = MagicMock()
    mock_suffix_mock = MagicMock()
    mock_suffix_mock.lower.return_value = ".swc"
    mock_path_for_validation.suffix = mock_suffix_mock

    def mock_path_constructor_final(path_str):
        # Validation call uses the filename string
        if path_str == "601506507_transformed.swc":
            return mock_path_for_validation
        # All other calls (cleanup) return the cleanup mock
        return mock_path_instance

    # Patch the imports in the target module
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.pathlib.Path", mock_path_constructor_final
    )
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.Path", mock_path_constructor_final
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
    # ID Generation is local to the test function
    mock_entity_id = uuid.uuid4()
    # FIX: Define both variables used in mocking and assertion
    payload_morphology_name = json.loads(mock_entity_payload)["name"]
    expected_response_name = "601506507_transformed.swc"

    # Mock EntitySDK client and its methods
    entitysdk_client_mock = MagicMock()
    entitysdk_client_mock.upload_file.return_value = {"asset_id": str(uuid.uuid4())}
    mock_entity_search_result = MagicMock()
    mock_entity_search_result.one.return_value = None
    entitysdk_client_mock.search_entity.return_value = mock_entity_search_result

    # Override the dependency
    def mock_get_client():
        return entitysdk_client_mock

    client.app.dependency_overrides[get_client] = mock_get_client

    # Mock registration logic uses the locally created ID
    mock_registered_entity = MagicMock()
    mock_registered_entity.id = str(mock_entity_id)
    # FIX: Use the payload name for the mock entity
    mock_registered_entity.name = payload_morphology_name

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

    mock_validate_and_convert_morphology = create_autospec(
        validate_and_convert_morphology,
        return_value=["mock_converted_1.h5", "mock_converted_2.asc"],
    )

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.validate_and_convert_morphology",
        mock_validate_and_convert_morphology,
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
            "file": ("601506507_transformed.swc", b"mock swc content", "application/octet-stream")
        },
    )

    # Cleanup dependency override
    client.app.dependency_overrides.pop(get_client, None)

    # Assert
    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json["status"] == "success"
    assert resp_json["entity_id"] == str(mock_entity_id)
    # FIX: Assert against the expected filename returned by the endpoint
    assert resp_json["morphology_name"] == expected_response_name

    mock_register_assets_and_measurements.assert_called_once()
    args, _ = mock_register_assets_and_measurements.call_args
    assert args[1] == str(mock_entity_id)
    assert args[4] == mock_measurement_list
