from pathlib import Path

import entitysdk
from entitysdk.models import TaskConfig
from entitysdk.types import AssetLabel

from obi_one.core.entity_from_id import EntityFromID
from obi_one.db_sdk.db_sdk import fetch_asset_by_label, require_db_client


class TaskConfigFromID(EntityFromID[TaskConfig]):
    """Wrapper for downloading assets from a TaskConfig entity."""

    _entitysdk_type: type[TaskConfig] = TaskConfig

    def download_asset_by_label(
        self,
        asset_label: AssetLabel,
        dest_dir: Path = Path(),
        db_client: entitysdk.client.Client | None = None,
    ) -> Path:
        """Download a single asset matching the given label to dest_dir.

        Returns the path to the downloaded file.
        """
        db_client = require_db_client(db_client)
        return fetch_asset_by_label(
            client=db_client,
            entity=self.entity(db_client=db_client),
            asset_label=asset_label,
            output_path=dest_dir,
        )
