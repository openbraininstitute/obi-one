from pathlib import Path
from unittest.mock import MagicMock, patch

from entitysdk.models import TaskConfig
from entitysdk.types import AssetLabel

from obi_one.scientific.from_id.task_config_from_id import TaskConfigFromID

_MODULE = "obi_one.scientific.from_id.task_config_from_id"


def test_task_config_from_id_download_asset_by_label():
    obj = TaskConfigFromID(id_str="00000000-0000-0000-0000-000000000010")
    entity = MagicMock()
    expected_path = Path("/tmp/config.json")
    client = MagicMock()

    with (
        patch.object(TaskConfigFromID, "fetch", return_value=entity),
        patch(f"{_MODULE}.fetch_asset_by_label", return_value=expected_path) as mock_fetch_asset,
    ):
        path = obj.download_asset_by_label(
            asset_label=AssetLabel.task_config,
            dest_dir=Path("/tmp"),
            db_client=client,
        )

    assert path is expected_path
    mock_fetch_asset.assert_called_once_with(
        client=client,
        entity=entity,
        asset_label=AssetLabel.task_config,
        output_path=Path("/tmp"),
    )
    assert TaskConfigFromID.entitysdk_class() is TaskConfig
