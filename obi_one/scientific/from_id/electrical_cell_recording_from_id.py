from pathlib import Path
from typing import ClassVar

import entitysdk
from entitysdk.models import ElectricalCellRecording
from entitysdk.types import AssetLabel, ContentType
from entitysdk.utils.filesystem import create_dir

from obi_one.core.entity_from_id import EntityFromID


class ElectricalCellRecordingFromID(EntityFromID[ElectricalCellRecording]):
    entitysdk_class: ClassVar[type[ElectricalCellRecording]] = ElectricalCellRecording

    def download_nwb_asset(
        self,
        dest_dir: Path = Path(),
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
    ) -> Path:
        output_dir = create_dir(dest_dir)
        asset = db_client.fetch_assets(
            self.entity(db_client=db_client),
            selection={"content_type": ContentType.application_nwb, "label": AssetLabel.nwb},
            output_path=output_dir,
        ).one()

        return asset.path
