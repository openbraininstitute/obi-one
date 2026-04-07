"""Unit tests for skeletonization cost estimation."""

import shutil
from pathlib import Path
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest
from entitysdk.types import AssetLabel

from obi_one.core.info import Info
from obi_one.core.single import SingleCoordinateScanParams
from obi_one.scientific.from_id.em_cell_mesh_from_id import EMCellMeshFromID
from obi_one.scientific.tasks.skeletonization.config import SkeletonizationSingleConfig
from obi_one.scientific.tasks.skeletonization.estimate import (
    _compute_mesh_surface_area,
    estimate_skeletonization_count,
)

TEST_DATA_DIR = Path(__file__).parent
SPHERE_GLB_PATH = TEST_DATA_DIR / "sphere.glb"


@pytest.fixture
def mesh_id():
    return str(uuid4())


@pytest.fixture
def asset_id():
    return uuid4()


@pytest.fixture
def config_id():
    return uuid4()


@pytest.fixture
def mock_asset(asset_id):
    """Create a mock asset with cell_surface_mesh label."""
    asset = Mock()
    asset.id = asset_id
    asset.label = AssetLabel.cell_surface_mesh
    return asset


@pytest.fixture
def mock_em_cell_mesh(mock_asset):
    """Create a mock EMCellMesh entity."""
    em_cell_mesh = Mock()
    em_cell_mesh.id = uuid4()
    em_cell_mesh.assets = [mock_asset]
    return em_cell_mesh


@pytest.fixture
def mock_db_client(mock_em_cell_mesh):
    """Create a mock database client."""
    client = MagicMock()
    client.get_entity.return_value = mock_em_cell_mesh
    return client


def _make_fetch_file_side_effect(source_glb_path: Path):
    """Create a side effect that copies the test GLB to the output path."""

    def fetch_file_side_effect(*, output_path, **_kwargs):
        shutil.copy(source_glb_path, output_path)

    return fetch_file_side_effect


def test_compute_mesh_surface_area(mock_db_client, mesh_id):
    """Test that _compute_mesh_surface_area correctly computes surface area."""
    mock_db_client.fetch_file.side_effect = _make_fetch_file_side_effect(SPHERE_GLB_PATH)

    cell_mesh = EMCellMeshFromID(id_str=mesh_id)
    area = _compute_mesh_surface_area(mock_db_client, cell_mesh)

    assert area > 0
    mock_db_client.get_entity.assert_called_once()
    mock_db_client.fetch_file.assert_called_once()


def test_compute_mesh_surface_area_no_asset(mock_db_client, mesh_id):
    """Test that _compute_mesh_surface_area raises when no asset found."""
    mock_db_client.get_entity.return_value.assets = []

    cell_mesh = EMCellMeshFromID(id_str=mesh_id)

    with pytest.raises(ValueError, match="No cell_surface_mesh asset found"):
        _compute_mesh_surface_area(mock_db_client, cell_mesh)


def test_estimate_skeletonization_count_single_mesh(mock_db_client, config_id, mesh_id, tmp_path):
    """Test estimate_skeletonization_count with a single mesh."""
    mock_db_client.fetch_file.side_effect = _make_fetch_file_side_effect(SPHERE_GLB_PATH)

    config = SkeletonizationSingleConfig(
        info=Info(campaign_name="test", campaign_description="test"),
        initialize=SkeletonizationSingleConfig.Initialize(
            cell_mesh=EMCellMeshFromID(id_str=mesh_id),
            neuron_voxel_size=0.1,
            spines_voxel_size=0.1,
        ),
        coordinate_output_root=tmp_path,
        idx=1,
        single_coordinate_scan_params=SingleCoordinateScanParams(scan_params=[]),
    )
    mock_db_client.get_task_config.return_value = config

    count = estimate_skeletonization_count(db_client=mock_db_client, config_id=config_id)

    assert count > 0
    mock_db_client.get_task_config.assert_called_once_with(
        config_id=config_id,
        config_type=SkeletonizationSingleConfig,
    )


def test_estimate_skeletonization_count_multiple_meshes(mock_db_client, config_id, tmp_path):
    """Test estimate_skeletonization_count with multiple meshes."""
    mesh_id_1 = str(uuid4())
    mesh_id_2 = str(uuid4())

    mock_db_client.fetch_file.side_effect = _make_fetch_file_side_effect(SPHERE_GLB_PATH)

    config = SkeletonizationSingleConfig(
        info=Info(campaign_name="test", campaign_description="test"),
        initialize=SkeletonizationSingleConfig.Initialize(
            cell_mesh=[
                EMCellMeshFromID(id_str=mesh_id_1),
                EMCellMeshFromID(id_str=mesh_id_2),
            ],
            neuron_voxel_size=0.1,
            spines_voxel_size=0.1,
        ),
        coordinate_output_root=tmp_path,
        idx=1,
        single_coordinate_scan_params=SingleCoordinateScanParams(scan_params=[]),
    )
    mock_db_client.get_task_config.return_value = config

    count = estimate_skeletonization_count(db_client=mock_db_client, config_id=config_id)

    assert count > 0
    assert mock_db_client.fetch_file.call_count == 2
