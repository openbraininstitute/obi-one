import pathlib
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import entitysdk
import pytest
from entitysdk.models import EMCellMesh

import obi_one.scientific.tasks.mesh_lod_generation as mesh_lod
from obi_one.scientific.tasks.mesh_lod_generation.config import MeshLodGenerationSingleConfig
from obi_one.scientific.tasks.mesh_lod_generation.task import (
    MeshLODGenerationTask,
    _download_mesh,
    _generate_lods,
    _upload_lod_directory,
)

MeshLodGenerationSingleConfig.model_rebuild(_types_namespace={"UUID": UUID})
MeshLODGenerationTask.model_rebuild(
    _types_namespace={
        "UUID": UUID,
        "entitysdk": entitysdk,
        "MeshLodGenerationSingleConfig": MeshLodGenerationSingleConfig,
    }
)


def test_init_exports():
    assert "MeshLodGenerationSingleConfig" in mesh_lod.__all__


def test_mesh_lod_config_valid():
    entity_id = uuid4()
    mesh_asset_id = uuid4()
    config = MeshLodGenerationSingleConfig(
        entity_id=entity_id, mesh_asset_id=mesh_asset_id, mesh_format="obj"
    )
    assert config.entity_id == entity_id
    assert config.mesh_asset_id == mesh_asset_id
    assert config.mesh_format == "obj"


def test_mesh_lod_config_invalid_types():
    with pytest.raises(ValueError, match="uuid"):
        MeshLodGenerationSingleConfig(
            entity_id="not-a-uuid", mesh_asset_id=uuid4(), mesh_format="obj"
        )


@patch("entitysdk.Client")
def test_download_mesh_execution(mock_client_cls, tmp_path):
    mock_client = mock_client_cls()
    mock_client.download_content.return_value = b"gltf-raw-payload"

    dest = tmp_path / "target.obj"
    entity_id = uuid4()
    mesh_asset_id = uuid4()

    _download_mesh(mock_client, entity_id, mesh_asset_id, dest)

    assert dest.read_bytes() == b"gltf-raw-payload"
    mock_client.download_content.assert_called_once_with(
        entity_id=entity_id,
        entity_type=EMCellMesh,
        asset_id=mesh_asset_id,
    )


def test_generate_lods_empty_failure(tmp_path):
    input_mesh = tmp_path / "empty.obj"
    input_mesh.write_text("v 0 0 0")
    out_dir = tmp_path / "lods"

    with (
        patch("ultraliser.LODGenerator"),
        patch("ultraliser.Mesh"),
        pytest.raises(RuntimeError, match="ultraliser produced no LOD output files"),
    ):
        _generate_lods(input_mesh, "obj", out_dir)


def test_generate_lods_success(tmp_path):
    input_mesh = tmp_path / "valid.obj"
    input_mesh.write_text("v 0 0 0")
    out_dir = tmp_path / "lods"

    def side_effect(path_str):
        pathlib.Path(path_str).mkdir(parents=True, exist_ok=True)
        (pathlib.Path(path_str) / "lod_1.gltf").write_text("data")

    with patch("ultraliser.LODGenerator") as mock_gen, patch("ultraliser.Mesh"):
        mock_gen.return_value.generate_web_lods.side_effect = side_effect
        res = _generate_lods(input_mesh, "obj", out_dir)
        assert pathlib.Path("lod_1.gltf") in res


def test_generate_lods_glb_success(tmp_path):
    input_mesh = tmp_path / "valid.glb"
    input_mesh.write_bytes(b"glb-data")
    out_dir = tmp_path / "lods"

    def side_effect(path_str):
        pathlib.Path(path_str).mkdir(parents=True, exist_ok=True)
        (pathlib.Path(path_str) / "lod_1.gltf").write_text("data")

    with patch("ultraliser.LODGenerator") as mock_gen, patch("ultraliser.Mesh"):
        mock_gen.return_value.generate_web_lods.side_effect = side_effect
        res = _generate_lods(input_mesh, "glb", out_dir)
        assert pathlib.Path("lod_1.gltf") in res


def test_generate_lods_unsupported_format(tmp_path):
    input_mesh = tmp_path / "valid.stl"
    input_mesh.write_text("solid")
    out_dir = tmp_path / "lods"

    with (
        patch("ultraliser.Mesh"),
        pytest.raises(RuntimeError, match="Unsupported mesh format"),
    ):
        _generate_lods(input_mesh, "stl", out_dir)


def test_upload_lod_directory_no_existing_assets(tmp_path):
    mock_client = MagicMock()
    mock_client.get_entity.return_value = MagicMock()
    mock_client.select_assets.return_value = []
    mock_client.upload_directory.return_value = MagicMock()

    entity_id = uuid4()
    dummy_file = tmp_path / "lod_1.gltf"
    files = {pathlib.Path("lod_1.gltf"): dummy_file}

    result = _upload_lod_directory(mock_client, entity_id, files)

    assert result == str(entity_id)
    mock_client.delete_asset.assert_not_called()
    mock_client.upload_directory.assert_called_once()


def test_upload_lod_directory_replaces_existing_assets(tmp_path):
    mock_client = MagicMock()
    mock_client.get_entity.return_value = MagicMock()

    existing_asset = MagicMock()
    existing_asset.id = uuid4()
    mock_client.select_assets.return_value = [existing_asset]
    mock_client.upload_directory.return_value = MagicMock()

    entity_id = uuid4()
    dummy_file = tmp_path / "lod_1.gltf"
    files = {pathlib.Path("lod_1.gltf"): dummy_file}

    result = _upload_lod_directory(mock_client, entity_id, files)

    assert result == str(entity_id)
    mock_client.delete_asset.assert_called_once_with(
        entity_id=entity_id, entity_type=EMCellMesh, asset_id=existing_asset.id
    )
    mock_client.upload_directory.assert_called_once()

    delete_call = next(c for c in mock_client.mock_calls if c[0] == "delete_asset")
    upload_call = next(c for c in mock_client.mock_calls if c[0] == "upload_directory")
    assert mock_client.mock_calls.index(delete_call) < mock_client.mock_calls.index(upload_call)


@patch("obi_one.scientific.tasks.mesh_lod_generation.task._upload_lod_directory")
@patch("obi_one.scientific.tasks.mesh_lod_generation.task._generate_lods")
@patch("obi_one.scientific.tasks.mesh_lod_generation.task._download_mesh")
def test_run_mesh_lod_generation_pipeline(mock_download, mock_generate, mock_upload, tmp_path):
    config = MeshLodGenerationSingleConfig(
        entity_id=uuid4(), mesh_asset_id=uuid4(), mesh_format="obj"
    )
    mock_client = MagicMock(spec=entitysdk.Client)

    dummy_file = tmp_path / "lod_1.gltf"
    mock_generate.return_value = {pathlib.Path("lod_1.gltf"): dummy_file}
    mock_upload.return_value = str(config.entity_id)

    task = MeshLODGenerationTask(config=config, client=mock_client)
    result = task.execute()

    assert result == str(config.entity_id)
    mock_download.assert_called_once()
