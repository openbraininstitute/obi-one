import json
import pathlib
import sys
import uuid
from http import HTTPStatus
from pathlib import Path
from unittest.mock import MagicMock, create_autospec, patch

import pytest
from _pytest.monkeypatch import MonkeyPatch
from fastapi import HTTPException
from requests.exceptions import RequestException

from app.dependencies.entitysdk import get_client
from app.endpoints.morphology_metrics_calculation import (
    MorphologyMetadata,
    PlaceholderCellMorphologyProtocol,
    _get_analysis_dict,
    _get_h5_analysis_path,
    _get_template,
    _get_template as cached_func,  # Top-level import to fix PLC0415
    _prepare_entity_payload,
    _register_assets_and_measurements,
    _resolve_swc_bytes_for_mesh,
    _try_mesh_and_register,
    _validate_file_extension,
    register_assets,
    register_measurements,
    register_morphology,
    run_morphology_analysis,
)
from app.errors import ApiError
from app.services.morphology import MorphologyFiles, validate_and_convert_morphology

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

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._get_template", lambda: fake_template
    )

    def mock_create_analysis_dict(_template):
        return {"soma": {"mock_metric": lambda _: 42.0}}

    monkeypatch.setattr(
        "app.endpoints.useful_functions.useful_functions.create_analysis_dict",
        mock_create_analysis_dict,
    )

    mock_result = MagicMock()
    mock_result.hdf5 = Path("path0.h5")
    mock_result.swc = Path("path1.swc")

    mock_validate_and_convert_morphology = create_autospec(
        validate_and_convert_morphology, return_value=mock_result
    )
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.validate_and_convert_morphology",
        mock_validate_and_convert_morphology,
    )


@pytest.fixture(autouse=True)
def mock_io_for_test(monkeypatch):
    """Mocks IO operations and registration functions."""
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

        mock_inst.read_text.return_value = '{"data": []}'

        parent_mock = MagicMock()
        parent_mock.__str__ = lambda _self: str(real.parent)
        mock_inst.parent = parent_mock

        return mock_inst

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.pathlib.Path", _make_mock_path
    )
    monkeypatch.setattr("app.endpoints.morphology_metrics_calculation.Path", _make_mock_path)

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.register_morphology",
        lambda _client, _payload: MagicMock(id="mock-entity-id"),
    )

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.register_asset_from_content",
        lambda *_args, **_kwargs: MagicMock(),
    )

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.register_assets",
        lambda *_args, **_kwargs: MagicMock(),
    )

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.register_measurements",
        lambda _client, entity_id, _measurements: MagicMock(id=entity_id),
    )

    _get_template.cache_clear()
    _get_analysis_dict.cache_clear()


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

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.register_morphology",
        lambda _client, _payload: MagicMock(id=mock_id),
    )
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.run_morphology_analysis", lambda _: []
    )

    response = client.post(
        ROUTE, data={"metadata": mock_entity_payload}, files={"file": ("test.swc", b"content")}
    )

    assert response.status_code == 200, response.json()
    assert response.json()["entity_id"] == mock_id


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
        "app.endpoints.morphology_metrics_calculation.run_morphology_analysis", mock_fail
    )

    response = client.post(
        ROUTE, data={"metadata": mock_entity_payload}, files={"file": ("test.swc", b"content")}
    )

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "MORPHOLOGY_ANALYSIS_ERROR"


def test_sdk_registration_failure(client, monkeypatch, mock_entity_payload):
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.run_morphology_analysis", lambda _: []
    )
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.register_asset_from_content",
        MagicMock(
            side_effect=HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={"code": "ENTITYSDK_API_FAILURE", "detail": "Upload fail"},
            )
        ),
    )

    response = client.post(
        ROUTE, data={"metadata": mock_entity_payload}, files={"file": ("test.swc", b"content")}
    )
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "ENTITYSDK_API_FAILURE"


def test_meshing_failure_is_graceful(client, monkeypatch, mock_entity_payload):
    monkeypatch.setattr("app.endpoints.morphology_metrics_calculation.HAS_MESHING", True)
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._mesh_and_register",
        MagicMock(side_effect=Exception("Mesh error")),
    )
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.run_morphology_analysis", lambda _: []
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


def test_meshing_api_error_is_graceful(client, monkeypatch, mock_entity_payload):
    monkeypatch.setattr("app.endpoints.morphology_metrics_calculation.HAS_MESHING", True)
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._mesh_and_register",
        MagicMock(side_effect=ApiError(message="api err", error_code="TEST_ERR")),
    )
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.run_morphology_analysis", lambda _: []
    )

    response = client.post(
        ROUTE, data={"metadata": mock_entity_payload}, files={"file": ("test.swc", b"content")}
    )
    assert response.status_code == 200
    assert response.json()["mesh_asset_id"] is None


def test_meshing_success(client, monkeypatch, mock_entity_payload):
    mesh_id = str(uuid.uuid4())
    entity_id = str(uuid.uuid4())
    monkeypatch.setattr("app.endpoints.morphology_metrics_calculation.HAS_MESHING", True)
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._mesh_and_register",
        MagicMock(return_value=MagicMock(id=mesh_id)),
    )
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.run_morphology_analysis", lambda _: []
    )
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.register_morphology",
        lambda _client, _payload: MagicMock(id=entity_id),
    )

    response = client.post(
        ROUTE, data={"metadata": mock_entity_payload}, files={"file": ("test.swc", b"content")}
    )
    assert response.status_code == 200
    assert response.json()["mesh_asset_id"] == mesh_id


def test_h5_upload_uses_original_path(client, monkeypatch):
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.run_morphology_analysis", lambda _: []
    )
    mock_entity_payload_h5 = json.dumps({"name": "H5 Morphology"})

    response = client.post(
        ROUTE,
        data={"metadata": mock_entity_payload_h5},
        files={"file": ("test.h5", b"content")},
    )
    assert response.status_code == 200, response.json()


def test_prepare_entity_payload_default_name():
    metadata = MorphologyMetadata()
    payload = _prepare_entity_payload(metadata, "my_cell.swc")
    assert payload["name"] == "Morphology: my_cell"


def test_prepare_entity_payload_test_name_replaced():
    metadata = MorphologyMetadata(name="test")
    payload = _prepare_entity_payload(metadata, "my_cell.swc")
    assert payload["name"] == "Morphology: my_cell"


def test_prepare_entity_payload_custom_name_kept():
    metadata = MorphologyMetadata(name="My Custom Morphology")
    payload = _prepare_entity_payload(metadata, "my_cell.swc")
    assert payload["name"] == "My Custom Morphology"


def test_get_h5_analysis_path_h5_extension():
    result = _get_h5_analysis_path("original.h5", ".h5", MorphologyFiles())
    assert result == "original.h5"


def test_get_h5_analysis_path_converted_h5_found(tmp_path):
    h5_file = tmp_path / "converted.h5"
    h5_file.write_bytes(b"")
    result = _get_h5_analysis_path("original.swc", ".swc", MorphologyFiles(hdf5=h5_file))
    assert result == str(h5_file)


def test_get_h5_analysis_path_falls_back_to_original():
    result = _get_h5_analysis_path("original.swc", ".swc", MorphologyFiles())
    assert result == "original.swc"


def test_validate_file_extension_empty():
    with pytest.raises(HTTPException) as exc_info:
        _validate_file_extension("")
    assert exc_info.value.detail["code"] == "BAD_REQUEST"


def test_validate_file_extension_invalid():
    with pytest.raises(HTTPException) as exc_info:
        _validate_file_extension("file.txt")
    assert exc_info.value.detail["code"] == "BAD_REQUEST"


def test_validate_file_extension_valid():
    assert _validate_file_extension("neuron.swc") == ".swc"
    assert _validate_file_extension("neuron.h5") == ".h5"
    assert _validate_file_extension("neuron.asc") == ".asc"


def test_get_template_caches(monkeypatch):
    sentinel = {"data": []}
    _get_template.cache_clear()

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._get_template",
        MagicMock(return_value=sentinel),
    )

    result1 = cached_func()
    result2 = cached_func()
    assert result1 is result2


def test_get_analysis_dict_caches(monkeypatch):
    _get_template.cache_clear()
    _get_analysis_dict.cache_clear()
    sentinel = {"soma": {}}

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._get_template", lambda: {"data": []}
    )
    monkeypatch.setattr(
        "app.endpoints.useful_functions.useful_functions.create_analysis_dict",
        lambda _: sentinel,
    )

    result1 = _get_analysis_dict()
    result2 = _get_analysis_dict()
    assert result1 is result2
    assert result1 == sentinel


def test_get_analysis_dict_extends_neurite_domains(monkeypatch):
    _get_template.cache_clear()
    _get_analysis_dict.cache_clear()

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._get_template", lambda: {"data": []}
    )
    monkeypatch.setattr(
        "app.endpoints.useful_functions.useful_functions.create_analysis_dict",
        lambda _t: {"basal_dendrite": {"metric": lambda _: 1.0}},
    )
    result = _get_analysis_dict()
    assert "apical_dendrite" in result
    assert "axon" in result


def test_register_assets_file_not_found():
    client = MagicMock()
    with patch("app.endpoints.morphology_metrics_calculation.pathlib.Path") as mock_path_cls:
        mock_p = MagicMock()
        mock_p.exists.return_value = False
        mock_path_cls.return_value.__truediv__ = MagicMock(return_value=mock_p)
        with pytest.raises(FileNotFoundError):
            register_assets(client, "eid", "/some/dir", "file.swc")


def test_register_assets_unsupported_extension():
    client = MagicMock()
    with patch("app.endpoints.morphology_metrics_calculation.pathlib.Path") as mock_path_cls:
        mock_p = MagicMock()
        mock_p.exists.return_value = True
        mock_p.suffix = ".xyz"
        mock_path_cls.return_value.__truediv__ = MagicMock(return_value=mock_p)
        with pytest.raises(ValueError, match="Unsupported file extension"):
            register_assets(client, "eid", "/some/dir", "file.xyz")


def test_register_assets_request_exception():
    valid_eid = str(uuid.uuid4())
    client = MagicMock()
    client.upload_file.side_effect = RequestException("Network error")
    with patch("app.endpoints.morphology_metrics_calculation.pathlib.Path") as mock_path_cls:
        mock_p = MagicMock()
        mock_p.exists.return_value = True
        mock_p.suffix = ".swc"
        mock_path_cls.return_value.__truediv__ = MagicMock(return_value=mock_p)
        with pytest.raises(HTTPException) as exc_info:
            register_assets(client, valid_eid, "/some/dir", "file.swc")
    assert exc_info.value.detail["code"] == "ENTITYSDK_API_FAILURE"


def test_register_measurements_request_exception(monkeypatch):
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.MeasurementAnnotation",
        MagicMock(return_value=MagicMock()),
    )
    client = MagicMock()
    client.register_entity.side_effect = RequestException("Network error")
    with pytest.raises(HTTPException) as exc_info:
        register_measurements(client, str(uuid.uuid4()), [])
    assert exc_info.value.detail["code"] == "ENTITYSDK_API_FAILURE"


def test_register_measurements_success(monkeypatch):
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.MeasurementAnnotation",
        MagicMock(return_value=MagicMock()),
    )
    client = MagicMock()
    client.register_entity.return_value = MagicMock(id="result-id")
    result = register_measurements(client, str(uuid.uuid4()), [])
    assert result.id == "result-id"


def test_register_morphology_logic_variants(monkeypatch):
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.CellMorphology",
        MagicMock(return_value=MagicMock()),
    )
    mock_protocol = MagicMock(spec=PlaceholderCellMorphologyProtocol)
    client = MagicMock()

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.PlaceholderCellMorphologyProtocol",
        MagicMock(return_value=mock_protocol),
    )

    def _search_side_effect(*_args, **_kwargs):
        mock_result = MagicMock()
        mock_result.one.return_value = mock_protocol
        return mock_result

    client.search_entity.side_effect = _search_side_effect

    payload = {
        "brain_location": [1.0],
        "cell_morphology_protocol_id": str(uuid.uuid4()),
        "name": "test",
    }
    result = register_morphology(client, payload)
    assert result is not None


def test_register_morphology_with_valid_brain_location(monkeypatch):
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.CellMorphology",
        MagicMock(return_value=MagicMock()),
    )
    mock_protocol = MagicMock(spec=PlaceholderCellMorphologyProtocol)

    def _search_side_effect(*_args, **_kwargs):
        mock_result = MagicMock()
        mock_result.one.return_value = mock_protocol
        return mock_result

    client = MagicMock()
    client.search_entity.side_effect = _search_side_effect
    payload = {
        "brain_location": [1.0, 2.0, 3.0],
        "cell_morphology_protocol_id": str(uuid.uuid4()),
        "name": "test",
        "authorized_public": False,
    }
    result = register_morphology(client, payload)
    assert result is not None


def test_register_morphology_request_exception_in_get_entity(monkeypatch):
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.CellMorphology",
        MagicMock(return_value=MagicMock()),
    )
    mock_protocol = MagicMock(spec=PlaceholderCellMorphologyProtocol)

    def _search_side_effect(*_args, **_kwargs):
        mock_result = MagicMock()
        mock_result.one.return_value = mock_protocol
        return mock_result

    client = MagicMock()
    client.search_entity.side_effect = _search_side_effect
    payload = {
        "subject_id": "some-id",
        "cell_morphology_protocol_id": str(uuid.uuid4()),
        "name": "test",
        "authorized_public": False,
    }
    result = register_morphology(client, payload)
    assert result is not None


def test_register_assets_and_measurements_no_converted_files(monkeypatch):
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.register_assets",
        MagicMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.register_measurements",
        MagicMock(return_value=MagicMock(id="meas-id")),
    )
    client = MagicMock()
    result = _register_assets_and_measurements(
        client, "eid", "file.swc", b"data", [], MorphologyFiles()
    )
    assert result.id == "meas-id"


def test_register_assets_and_measurements_converted_file_not_exists(monkeypatch):
    mock_register_assets = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.register_assets", mock_register_assets
    )
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.register_measurements",
        MagicMock(return_value=MagicMock(id="meas-id")),
    )

    real_path = pathlib.Path

    def _mock_path(p):
        inst = MagicMock()
        inst.exists.return_value = False
        inst.suffix = real_path(p).suffix
        inst.name = real_path(p).name
        parent = MagicMock()
        parent.__str__ = lambda _: str(real_path(p).parent)
        inst.parent = parent
        return inst

    monkeypatch.setattr("app.endpoints.morphology_metrics_calculation.pathlib.Path", _mock_path)

    client = MagicMock()
    result = _register_assets_and_measurements(
        client, "eid", "file.swc", b"data", [], MorphologyFiles()
    )
    assert result.id == "meas-id"
    assert mock_register_assets.call_count == 0


def test_resolve_swc_bytes_for_mesh_swc_converted_exists(tmp_path):
    mock_swc = tmp_path / "mock.swc"
    with (
        patch.object(pathlib.Path, "exists", return_value=True),
        patch.object(pathlib.Path, "read_bytes", return_value=b"swc data"),
    ):
        result = _resolve_swc_bytes_for_mesh(
            None, MorphologyFiles(swc=mock_swc), ".h5", b"original"
        )
        assert result == b"swc data"


def test_resolve_swc_bytes_for_mesh_swc_extension():
    result = _resolve_swc_bytes_for_mesh(None, MorphologyFiles(), ".swc", b"original content")
    assert result == b"original content"


def test_resolve_swc_bytes_for_mesh_non_swc_returns_none():
    result = _resolve_swc_bytes_for_mesh(None, MorphologyFiles(), ".h5", b"original")
    assert result is None


def test_try_mesh_and_register_no_meshing(monkeypatch):
    monkeypatch.setattr("app.endpoints.morphology_metrics_calculation.HAS_MESHING", False)
    client = MagicMock()
    result = _try_mesh_and_register(client, str(uuid.uuid4()), b"swc")
    assert result is None


def test_try_mesh_and_register_success(monkeypatch):
    mesh_id = str(uuid.uuid4())
    monkeypatch.setattr("app.endpoints.morphology_metrics_calculation.HAS_MESHING", True)
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._mesh_and_register",
        MagicMock(return_value=MagicMock(id=mesh_id)),
    )
    client = MagicMock()
    result = _try_mesh_and_register(client, str(uuid.uuid4()), b"swc")
    assert result == mesh_id


def test_try_mesh_and_register_api_error(monkeypatch):
    monkeypatch.setattr("app.endpoints.morphology_metrics_calculation.HAS_MESHING", True)
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._mesh_and_register",
        MagicMock(side_effect=ApiError(message="mesh failed", error_code="TEST_ERR")),
    )
    client = MagicMock()
    result = _try_mesh_and_register(client, str(uuid.uuid4()), b"swc")
    assert result is None


def test_try_mesh_and_register_unexpected_error(monkeypatch):
    monkeypatch.setattr("app.endpoints.morphology_metrics_calculation.HAS_MESHING", True)
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._mesh_and_register",
        MagicMock(side_effect=RuntimeError("crash")),
    )
    client = MagicMock()
    result = _try_mesh_and_register(client, str(uuid.uuid4()), b"swc")
    assert result is None


def test_run_morphology_analysis_success(monkeypatch):
    fake_neuron = MagicMock()
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.nm.load_morphology",
        MagicMock(return_value=fake_neuron),
    )
    monkeypatch.setattr(
        "app.endpoints.useful_functions.useful_functions.build_results_dict",
        MagicMock(return_value={}),
    )

    fake_filled = {
        "data": [
            {"measurement_kinds": [{"pref_label": "metric", "measurement_items": [{"value": 1.0}]}]}
        ]
    }
    monkeypatch.setattr(
        "app.endpoints.useful_functions.useful_functions.fill_json",
        MagicMock(return_value=fake_filled),
    )

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._get_template",
        lambda: {"data": [{"measurement_kinds": []}]},
    )
    monkeypatch.setattr("app.endpoints.morphology_metrics_calculation._get_analysis_dict", dict)

    result = run_morphology_analysis("some/path.h5")
    assert len(result) == 1


def test_run_morphology_analysis_filters_none_values(monkeypatch):
    fake_neuron = MagicMock()
    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation.nm.load_morphology",
        MagicMock(return_value=fake_neuron),
    )
    monkeypatch.setattr(
        "app.endpoints.useful_functions.useful_functions.build_results_dict",
        MagicMock(return_value={}),
    )

    fake_filled = {
        "data": [
            {
                "measurement_kinds": [
                    {"pref_label": "null_metric", "measurement_items": [{"value": None}]},
                    {"pref_label": "valid_metric", "measurement_items": [{"value": 5.0}]},
                ]
            }
        ]
    }
    monkeypatch.setattr(
        "app.endpoints.useful_functions.useful_functions.fill_json",
        MagicMock(return_value=fake_filled),
    )

    monkeypatch.setattr(
        "app.endpoints.morphology_metrics_calculation._get_template",
        lambda: {"data": [{"measurement_kinds": []}]},
    )
    monkeypatch.setattr("app.endpoints.morphology_metrics_calculation._get_analysis_dict", dict)

    result = run_morphology_analysis("some/path.h5")
    assert len(result) == 1
    assert result[0]["pref_label"] == "valid_metric"
