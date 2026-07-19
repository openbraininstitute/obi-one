from pathlib import Path
from typing import ClassVar

import entitysdk
from entitysdk.models import TaskResult
from entitysdk.models.entity import Entity
from entitysdk.types import AssetLabel
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import EntityFromID
from obi_one.utils.db_sdk import fetch_asset_by_label, fetch_directory_asset_by_label


class TaskResultFromID(EntityFromID):
    """Wrapper for downloading assets from a TaskResult entity."""

    entitysdk_class: ClassVar[type[Entity]] = TaskResult
    _entity: TaskResult | None = PrivateAttr(default=None)

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

    def download_directory_asset_by_label(
        self,
        asset_label: AssetLabel,
        dest_dir: Path = Path(),
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
    ) -> Path:
        """Download a directory asset matching the given label to dest_dir.

        Returns the path to the downloaded directory.
        """
        return fetch_directory_asset_by_label(
            client=db_client,
            entity=self.entity(db_client=db_client),
            asset_label=asset_label,
            output_path=dest_dir,
        )
