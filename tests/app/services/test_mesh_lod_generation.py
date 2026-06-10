# app/tests/scientific/tasks/test_mesh_lod_generation.py
import pathlib
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from entitysdk.models import EMCellMesh
from entitysdk.types import AssetLabel

import obi_one.scientific.tasks.mesh_lod_generation as mesh_lod
from obi_one.scientific.tasks.mesh_lod_generation.config import MeshLodGenerationScanConfig
from obi_one.scientific.tasks.mesh_lod_generation.estimate import (
    estimate_mesh_lod_generation_count,
)
from obi_one.scientific.tasks.mesh_lod_generation.task import (
    _download_obj,
    _generate_lods,
    _upload_lod_directory,
    run_mesh_lod_generation,
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
    obj_id = uuid4()

    config = MeshLodGenerationScanConfig(
        entity_id=entity_id,
        obj_asset_id=obj_id,
    )

    assert config.entity_id == entity_id
    assert config.obj_asset_id == obj_id
    assert config.name == "Mesh LOD Generation"


# ==========================================
# 3. Sizing Resource Estimation (estimate.py)
# ==========================================
def test_estimate_mesh_lod_generation_count():
    """Verify resource allocation calculation returns 1 regardless of inputs."""
    mock_db = MagicMock()
    mock_config_id = uuid4()

    result = estimate_mesh_lod_generation_count(db_client=mock_db, config_id=mock_config_id)
    assert result == 1


# ==========================================
# 4. Pipeline Execution & Branches (task.py)
# ==========================================
def test_download_obj(tmp_path):
    """Test that binary stream is properly intercepted and written out."""
    mock_client = MagicMock()
    mock_client.download_content.return_value = b"mock-obj-binary-data"

    dest_file = tmp_path / "test.obj"
    entity_id = uuid4()
    obj_id = uuid4()

    _download_obj(mock_client, entity_id, obj_id, dest_file)

    assert dest_file.read_bytes() == b"mock-obj-binary-data"
    mock_client.download_content.assert_called_once_with(
        entity_id=entity_id,
        entity_type=EMCellMesh,
        asset_id=obj_id,
    )


def test_generate_lods_success(tmp_path):
    """Verify proper directory reading when ultraliser produces output files."""
    obj_path = tmp_path / "input.obj"
    obj_path.write_bytes(b"data")

    output_dir = tmp_path / "output_lods"

    # Avoid targeting underlying C-bindings by patching the reference directly
    # inside the execution task namespace as an open MagicMock object.
    with patch("obi_one.scientific.tasks.mesh_lod_generation.task.ultraliser") as mock_ultra:
        mock_mesh_instance = MagicMock()
        mock_ultra.Mesh.return_value = mock_mesh_instance

        def side_effect_create_file(out_dir_str):
            p = pathlib.Path(out_dir_str) / "lod_1.gltf"
            p.write_bytes(b"gltf-content")

        mock_mesh_instance.generate_web_lods.side_effect = side_effect_create_file

        result = _generate_lods(obj_path, output_dir)

        assert pathlib.Path("lod_1.gltf") in result
        assert result[pathlib.Path("lod_1.gltf")] == output_dir / "lod_1.gltf"


def test_generate_lods_empty_failure(tmp_path):
    """Ensure an explicit RuntimeError boundary is hit if no files are generated."""
    obj_path = tmp_path / "input.obj"
    obj_path.write_bytes(b"data")
    output_dir = tmp_path / "output_lods"

    with patch("obi_one.scientific.tasks.mesh_lod_generation.task.ultraliser") as mock_ultra:
        mock_mesh_instance = MagicMock()
        mock_mesh_instance.generate_web_lods.return_value = None
        mock_ultra.Mesh.return_value = mock_mesh_instance

        with pytest.raises(RuntimeError, match="ultraliser produced no LOD output files"):
            _generate_lods(obj_path, output_dir)


def test_upload_lod_directory_with_id_attribute(tmp_path):
    """Cover the branch where client returns an instance with an 'id' attribute."""
    mock_client = MagicMock()
    mock_result = MagicMock()
    mock_result.id = "asset-uuid-from-attr"
    mock_client.upload_directory.return_value = mock_result

    entity_id = uuid4()
    dummy_file = tmp_path / "lod_1.gltf"
    files = {pathlib.Path("lod_1.gltf"): dummy_file}

    asset_id = _upload_lod_directory(mock_client, entity_id, files)

    assert asset_id == "asset-uuid-from-attr"
    mock_client.upload_directory.assert_called_once_with(
        entity_id=entity_id,
        entity_type=EMCellMesh,
        name="lod-mesh-directory",
        paths=files,
        label=AssetLabel.lod_mesh_block,
        metadata=None,
    )


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


@patch("obi_one.scientific.tasks.mesh_lod_generation.task._download_obj")
@patch("obi_one.scientific.tasks.mesh_lod_generation.task._generate_lods")
@patch("obi_one.scientific.tasks.mesh_lod_generation.task._upload_lod_directory")
def test_run_mesh_lod_generation_pipeline(mock_upload, mock_generate, mock_download, tmp_path):
    """Test full integration workflow and temporal scoping from start to finish."""
    config = MeshLodGenerationScanConfig(entity_id=uuid4(), obj_asset_id=uuid4())
    mock_client = MagicMock()

    dummy_file = tmp_path / "lod_1.gltf"
    mock_generate.return_value = {pathlib.Path("lod_1.gltf"): dummy_file}
    mock_upload.return_value = "final-registered-asset-id"

    result = run_mesh_lod_generation(config, mock_client)

    assert result == "final-registered-asset-id"
    mock_download.assert_called_once()
    mock_generate.assert_called_once()
    mock_upload.assert_called_once_with(mock_client, config.entity_id, mock_generate.return_value)
