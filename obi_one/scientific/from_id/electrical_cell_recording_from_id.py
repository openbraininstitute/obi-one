from pathlib import Path

import entitysdk
from entitysdk.models import ElectricalCellRecording
from entitysdk.types import AssetLabel, ContentType
from entitysdk.utils.filesystem import create_dir

from obi_one.core.entity_from_id import EntityFromID
from obi_one.db_sdk.db_sdk import require_db_client


class ElectricalCellRecordingFromID(EntityFromID[ElectricalCellRecording]):
    _entitysdk_type: type[ElectricalCellRecording] = ElectricalCellRecording

    def download_nwb_asset(
        self,
        dest_dir: Path = Path(),
        db_client: entitysdk.client.Client | None = None,
    ) -> Path:
        db_client = require_db_client(db_client)
        output_dir = create_dir(dest_dir)
        asset = db_client.fetch_assets(
            self.entity(db_client=db_client),
            selection={"content_type": ContentType.application_nwb, "label": AssetLabel.nwb},
            output_path=output_dir,
        ).one()

        return asset.path
