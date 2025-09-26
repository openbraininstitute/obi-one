from pathlib import Path
from typing import ClassVar

import entitysdk
from entitysdk.models import IonChannelRecording
from entitysdk.models.entity import Entity
from entitysdk.types import ContentType
from entitysdk.utils.filesystem import create_dir
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import EntityFromID


class IonChannelRecordingFromID(EntityFromID):
    entitysdk_class: ClassVar[type[Entity]] = IonChannelRecording
    _entity: IonChannelRecording | None = PrivateAttr(default=None)

    def download_asset(
        self, dest_dir: Path = Path(), db_client: entitysdk.client.Client = None
    ) -> Path:
        output_dir = create_dir(dest_dir)
        asset = db_client.download_assets(
            self.entity(db_client=db_client),
            selection={"content_type": ContentType.application_nwb},
            output_path=output_dir,
        ).one()

        return asset.path
