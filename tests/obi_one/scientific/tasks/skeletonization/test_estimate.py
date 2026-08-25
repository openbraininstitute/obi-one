"""Unit tests for skeletonization cost estimation."""

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from entitysdk.exception import EntitySDKError
from entitysdk.types import AssetLabel

from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.single import SingleCoordinateScanParams
from obi_one.scientific.from_id.em_cell_mesh_from_id import EMCellMeshFromID
from obi_one.scientific.tasks.skeletonization.config import SkeletonizationSingleConfig
from obi_one.scientific.tasks.skeletonization.estimate import (
    _compute_mesh_surface_area,
    _get_skeletonization_config,
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
def mock_task_config_asset():
    """Create a mock asset with task_config label."""
    asset = Mock()
    asset.id = uuid4()
    asset.label = AssetLabel.task_config
    return asset


@pytest.fixture
def mock_db_client():
    """Create a mock database client."""
    return MagicMock()


def _make_fetch_assets_side_effect(source_glb_path: Path):
    """Create a side effect that copies the test GLB to the output path."""

    def fetch_assets_side_effect(*, output_path, **_kwargs):
        shutil.copy(source_glb_path, output_path)
        result = Mock()
        result.one.return_value = None
        return result

    return fetch_assets_side_effect


def test_compute_mesh_surface_area(mock_db_client, mesh_id):
    """Test that _compute_mesh_surface_area correctly computes surface area."""
    mock_db_client.fetch_assets.side_effect = _make_fetch_assets_side_effect(SPHERE_GLB_PATH)

    cell_mesh = EMCellMeshFromID(id_str=mesh_id)
    area = _compute_mesh_surface_area(mock_db_client, cell_mesh)

    assert area > 0
    mock_db_client.fetch_assets.assert_called_once()


def test_get_skeletonization_config(mock_db_client, config_id, mesh_id, mock_task_config_asset):
    """Test that _get_skeletonization_config fetches and parses the config."""
    mock_task_config = Mock()
    mock_task_config.assets = [mock_task_config_asset]
    mock_db_client.get_entity.return_value = mock_task_config
    mock_db_client.select_assets.return_value.one.return_value = mock_task_config_asset

    config_dict = {
        "type": "SkeletonizationSingleConfig",
        "info": {"campaign_name": "test", "campaign_description": "test"},
        "initialize": {
            "cell_mesh": {"type": "EMCellMeshFromID", "id_str": mesh_id},
            "neuron_voxel_size": 0.005,
            "spines_voxel_size": 0.1,
        },
    }
    mock_db_client.download_content.return_value = json.dumps(config_dict).encode("utf-8")

    config = _get_skeletonization_config(mock_db_client, config_id)

    assert isinstance(config, SkeletonizationSingleConfig)
    assert config.initialize.cell_mesh.id_str == mesh_id


def test_get_skeletonization_config_no_asset(mock_db_client, config_id):
    """Test that _get_skeletonization_config raises when no task_config asset found."""
    mock_task_config = Mock()
    mock_task_config.assets = []
    mock_db_client.get_entity.return_value = mock_task_config
    mock_db_client.select_assets.return_value.one.side_effect = EntitySDKError("No asset found")

    with pytest.raises(OBIONEError, match="Could not find asset with label"):
        _get_skeletonization_config(mock_db_client, config_id)


def test_estimate_skeletonization_count_single_mesh(mock_db_client, config_id, mesh_id, tmp_path):
    """Test estimate_skeletonization_count with a single mesh."""
    mock_db_client.fetch_assets.side_effect = _make_fetch_assets_side_effect(SPHERE_GLB_PATH)

    config = SkeletonizationSingleConfig(
        info=Info(campaign_name="test", campaign_description="test"),
        initialize=SkeletonizationSingleConfig.Initialize(
            cell_mesh=EMCellMeshFromID(id_str=mesh_id),
            neuron_voxel_size=0.005,
            spines_voxel_size=0.1,
        ),
        coordinate_output_root=tmp_path,
        idx=1,
        single_coordinate_scan_params=SingleCoordinateScanParams(scan_params=[]),
    )

    with patch(
        "obi_one.scientific.tasks.skeletonization.estimate._get_skeletonization_config",
        return_value=config,
    ):
        count = estimate_skeletonization_count(db_client=mock_db_client, config_id=config_id)

    assert count > 0
