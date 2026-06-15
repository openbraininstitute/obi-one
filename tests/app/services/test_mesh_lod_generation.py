# app/tests/scientific/tasks/test_mesh_lod_generation.py
import pathlib
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from entitysdk.models import EMCellMesh

import obi_one.scientific.tasks.mesh_lod_generation as mesh_lod
from obi_one.scientific.tasks.mesh_lod_generation.config import MeshLodGenerationScanConfig
from obi_one.scientific.tasks.mesh_lod_generation.estimate import (
    estimate_mesh_lod_generation_count,
)
from obi_one.scientific.tasks.mesh_lod_generation.task import (
    MeshLODGenerationTask,
    _download_obj,
    _generate_lods,
    _upload_lod_directory,
)

# Explicitly rebuild the Pydantic schema using the runtime UUID type
# to fix the 'class-not-fully-defined' forward reference error.
MeshLodGenerationScanConfig.model_rebuild(_types_namespace={"UUID": UUID})


# ==========================================
# 1. Package Initialization (__init__.py)
# ==========================================
def test_init_exports():
    """Ensure __all__ and package-level exports are properly initialized."""
    assert "MeshLodGenerationScanConfig" in mesh_lod.__all__
    assert mesh_lod.MeshLodGenerationScanConfig is MeshLodGenerationScanConfig


# ==========================================
# 2. Configuration Schema (config.py)
# ==========================================
def test_mesh_lod_config_valid():
    """Ensure config parses valid combinations of UUIDs and attributes."""
    entity_id = uuid4()
    obj_asset_id = uuid4()
    config = MeshLodGenerationScanConfig(entity_id=entity_id, obj_asset_id=obj_asset_id)
    assert config.entity_id == entity_id
    assert config.obj_asset_id == obj_asset_id


def test_mesh_lod_config_invalid_types():
    """Ensure structural failure when non-UUID string types are supplied."""
    with pytest.raises(ValueError, match="uuid"):
        MeshLodGenerationScanConfig(entity_id="not-a-uuid", obj_asset_id=uuid4())


# ==========================================
# 3. Estimation Metrics (estimate.py)
# ==========================================
def test_estimate_mesh_lod_generation_count():
    """Ensure metrics scale deterministically (1 element per incoming item context)."""
    assert estimate_mesh_lod_generation_count() == 1


# ==========================================
# 4. Core Pipeline & Orchestration (task.py)
# ==========================================
@patch("entitysdk.Client")
def test_download_obj_execution(mock_client_cls, tmp_path):
    """Ensure asset payload downloads are bound correctly to paths."""
    mock_client = mock_client_cls()
    mock_client.download_content.return_value = b"gltf-raw-payload"

    dest = tmp_path / "target.obj"
    entity_id = uuid4()
    obj_asset_id = uuid4()

    _download_obj(mock_client, entity_id, obj_asset_id, dest)

    assert dest.read_bytes() == b"gltf-raw-payload"
    mock_client.download_content.assert_called_once_with(
        entity_id=entity_id,
        entity_type=EMCellMesh,
        asset_id=obj_asset_id,
    )


def test_generate_lods_empty_failure(tmp_path):
    """Ensure a RuntimeError is declared if ultraliser outputs nothing."""
    input_obj = tmp_path / "empty.obj"
    input_obj.write_text("v 0 0 0")
    out_dir = tmp_path / "lods"

    with (
        patch("ultraliser.LODGenerator"),
        patch("ultraliser.Mesh"),
        pytest.raises(RuntimeError, match="ultraliser produced no LOD output files"),
    ):
        _generate_lods(input_obj, out_dir)


def test_generate_lods_success(tmp_path):
    """Ensure file dictionaries map correctly from structural output listings."""
    input_obj = tmp_path / "valid.obj"
    input_obj.write_text("v 0 0 0")
    out_dir = tmp_path / "lods"

    def side_effect(path_str):
        pathlib.Path(path_str).mkdir(parents=True, exist_ok=True)
        (pathlib.Path(path_str) / "lod_1.gltf").write_text("data")

    with patch("ultraliser.LODGenerator") as mock_gen, patch("ultraliser.Mesh"):
        mock_gen.return_value.generate_web_lods.side_effect = side_effect
        res = _generate_lods(input_obj, out_dir)
        assert pathlib.Path("lod_1.gltf") in res


def test_upload_lod_directory_with_id_attribute(tmp_path):
    """Cover the branch where client returns an object containing an 'id' field."""
    mock_client = MagicMock()
    mock_result = MagicMock()
    mock_result.id = "asset-uuid-from-attr"
    mock_client.upload_directory.return_value = mock_result

    entity_id = uuid4()
    dummy_file = tmp_path / "lod_1.gltf"
    files = {pathlib.Path("lod_1.gltf"): dummy_file}

    asset_id = _upload_lod_directory(mock_client, entity_id, files)
    assert asset_id == "asset-uuid-from-attr"


def test_upload_lod_directory_with_list_fallback(tmp_path):
    """Cover the fallback 'else' branch where client returns an indexable list."""
    mock_client = MagicMock()
    mock_item = MagicMock()
    mock_item.id = "asset-uuid-from-list"
    mock_client.upload_directory.return_value = [mock_item]

    entity_id = uuid4()
    dummy_file = tmp_path / "lod_1.gltf"
    files = {pathlib.Path("lod_1.gltf"): dummy_file}

    asset_id = _upload_lod_directory(mock_client, entity_id, files)
    assert asset_id == "asset-uuid-from-list"


@patch("obi_one.scientific.tasks.mesh_lod_generation.task._upload_lod_directory")
@patch("obi_one.scientific.tasks.mesh_lod_generation.task._generate_lods")
@patch("obi_one.scientific.tasks.mesh_lod_generation.task._download_obj")
def test_run_mesh_lod_generation_pipeline(mock_download, mock_generate, mock_upload, tmp_path):
    """Test full integration workflow and temporal scoping from start to finish."""
    config = MeshLodGenerationScanConfig(entity_id=uuid4(), obj_asset_id=uuid4())
    mock_client = MagicMock()

    dummy_file = tmp_path / "lod_1.gltf"
    mock_generate.return_value = {pathlib.Path("lod_1.gltf"): dummy_file}
    mock_upload.return_value = "final-asset-id"

    task = MeshLODGenerationTask(config=config, client=mock_client)
    asset_id = task.execute()

    assert asset_id == "final-asset-id"
    mock_download.assert_called_once()
