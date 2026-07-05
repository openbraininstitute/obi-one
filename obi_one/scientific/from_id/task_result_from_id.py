from pathlib import Path
from typing import ClassVar

import entitysdk
from entitysdk.models import TaskResult
from entitysdk.models.entity import Entity
from entitysdk.types import AssetLabel, ContentType
from entitysdk.utils.filesystem import create_dir
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import EntityFromID


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
        output_dir = create_dir(dest_dir)
        asset = db_client.download_assets(
            self.entity(db_client=db_client),
            selection={"label": asset_label},
            output_path=output_dir,
        ).one()

        return asset.path

    def download_json_asset_by_label(
        self,
        asset_label: AssetLabel,
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
    ) -> dict:
        """Download a JSON asset by label and return it as a parsed dict."""
        from entitysdk.types import ContentType as CT  # noqa: PLC0415

        bytes_content = db_client.fetch_content(
            entity_id=self.entity(db_client=db_client).id,  # ty:ignore[invalid-argument-type]
            entity_type=TaskResult,
            asset_or_id=db_client.select_assets(
                entity=self.entity(db_client=db_client),
                selection={"label": asset_label, "content_type": CT.application_json},
            ).one(),
        )
        import json  # noqa: PLC0415

        return json.loads(bytes_content)

    def download_directory_asset_by_label(
        self,
        asset_label: AssetLabel,
        dest_dir: Path = Path(),
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
    ) -> Path:
        """Download a directory asset matching the given label to dest_dir.

        Returns the path to the downloaded directory.
        """
        output_dir = create_dir(dest_dir)
        asset = db_client.download_assets(
            self.entity(db_client=db_client),
            selection={"label": asset_label, "content_type": ContentType.application_vnd_directory},
            output_path=output_dir,
        ).one()

        return asset.path
