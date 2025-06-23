from pathlib import Path
from typing import ClassVar

import morphio
import neurom
import entitysdk
from entitysdk.models import Circuit
from entitysdk.models.entity import Entity
from pydantic import PrivateAttr

from obi_one.database.db_manager import db
from obi_one.database.entity_from_id import EntityFromID, LoadAssetMethod

import io

class CircuitFromID(EntityFromID):
    entitysdk_class: ClassVar[type[Entity]] = Circuit
    _entity: Circuit | None = PrivateAttr(default=None)

    def circuit_directory(self, dest_dir=Path(), db_client: entitysdk.client.Client = None) -> None:
        for asset in self.entity(db_client=db_client).assets:
            if asset.content_type == "application/vnd.directory":

                # load_asset_method = LoadAssetMethod.MEMORY
                # if load_asset_method == LoadAssetMethod.MEMORY:
                #     print("Downloading SWC file for morphology...")

                # Download the content into memory
                content = db_client.download_content(
                    entity_id=self.entity(db_client=db_client).id,
                    entity_type=self.entitysdk_type,
                    asset_id=asset.id,
                    output_path=dest_dir,
                ).decode(encoding="utf-8")

                type(content)

                self._swc_file_content = content
                break

    # with tempfile.TemporaryDirectory() as tdir:

    # files = client.list_directory(
    #     entity_id=circuit.id,
    #     entity_type=models.Circuit,
    #     asset_id=directory_asset.id
    # )
    # rprint(files)

    # client.download_directory(
    #     entity_id=circuit.id,
    #     entity_type=models.Circuit,
    #     asset_id=directory_asset.id,
    #     output_path=Path(tdir)
    # )
    # rprint(list(Path(tdir).iterdir()))