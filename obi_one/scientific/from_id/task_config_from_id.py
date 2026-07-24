from pathlib import Path
from typing import ClassVar

import entitysdk
from entitysdk.models import TaskConfig
from entitysdk.models.entity import Entity
from entitysdk.types import AssetLabel
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import EntityFromID
from obi_one.utils.db_sdk import fetch_asset_by_label


class TaskConfigFromID(EntityFromID):
    """Wrapper for downloading assets from a TaskConfig entity."""

    entitysdk_class: ClassVar[type[Entity]] = TaskConfig
    _entity: TaskConfig | None = PrivateAttr(default=None)

    def download_asset_by_label(
        self,
        asset_label: AssetLabel,
        dest_dir: Path = Path(),
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
    ) -> Path:
        """Download a single asset matching the given label to dest_dir.

        Returns the path to the downloaded file.
        """
        return fetch_asset_by_label(
            client=db_client,
            entity=self.entity(db_client=db_client),
            asset_label=asset_label,
            output_path=dest_dir,
        )
