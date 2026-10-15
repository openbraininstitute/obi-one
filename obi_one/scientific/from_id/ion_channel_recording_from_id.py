from pathlib import Path

import entitysdk
from entitysdk.models import IonChannelRecording
from entitysdk.types import ContentType
from entitysdk.utils.filesystem import create_dir
from pydantic import Field

from obi_one.core.entity_from_id import EntityFromID


class IonChannelRecordingFromID(EntityFromID[IonChannelRecording]):
    entitysdk_type: type[IonChannelRecording] = Field(
        default=IonChannelRecording, exclude=True, repr=False
    )

    def download_asset(
        self,
        dest_dir: Path = Path(),
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
    ) -> Path:
        output_dir = create_dir(dest_dir)
        asset = db_client.download_assets(
            self.entity(db_client=db_client),
            selection={"content_type": ContentType.application_nwb},
            output_path=output_dir,
        ).one()

        return asset.path
