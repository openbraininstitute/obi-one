from pathlib import Path
from typing import ClassVar

import morphio
import neurom
from entitysdk.models import ReconstructionMorphology
from entitysdk.models.entity import Entity
from pydantic import PrivateAttr

from obi_one.database.db_manager import db
from obi_one.database.entity_from_id import EntityFromID, LoadAssetMethod

import io

class ReconstructionMorphologyFromID(EntityFromID):
    entitysdk_class: ClassVar[type[Entity]] = ReconstructionMorphology
    _entity: ReconstructionMorphology | None = PrivateAttr(default=None)
    _swc_file_path: Path | None = PrivateAttr(default=None)
    _neurom_morphology: neurom.core.Morphology | None = PrivateAttr(default=None)
    _morphio_morphology: morphio.Morphology | None = PrivateAttr(default=None)
    _swc_file_content: str | None = PrivateAttr(default=None) 

    # @property
    def swc_file_content(self, db_client) -> None:
        """Function for downloading SWC files of a morphology into memory."""
        
        
        if self._swc_file_content is None:
            for asset in self.entity(db_client=db_client).assets:
                if asset.content_type == "application/swc":

                    load_asset_method = LoadAssetMethod.MEMORY
                    if load_asset_method == LoadAssetMethod.MEMORY:
                        print("Downloading SWC file for morphology...")

                        # Download the content into memory
                        content = db_client.download_content(
                            entity_id=self.entity(db_client=db_client).id,
                            entity_type=self.entitysdk_type,
                            asset_id=asset.id,
                        ).decode(encoding="utf-8")

                        type(content)

                        self._swc_file_content = content
                        break

                    #     # Use StringIO to create a file-like object in memory from the string content
                    #     neurom_morphology = neurom.load_morphology(io.StringIO(content), reader="asc")

                    # else:
                    #     file_output_path = Path(db.entity_file_store_path) / asset.full_path
                    #     file_output_path.parent.mkdir(parents=True, exist_ok=True)

                    #     # db.client.download_file(
                    #     client.download_file(
                    #         entity_id=self.entity(client).id,
                    #         entity_type=self.entitysdk_type,
                    #         asset_id=asset.id,
                    #         output_path=file_output_path,
                    #         # token=db.token,
                    #     )

                    #     self._swc_file_path = file_output_path
                    # break

            if self._swc_file_content is None:
                msg = "No valid application/asc asset found for morphology."
                raise ValueError(msg)

        return self._swc_file_content

    # @property
    def neurom_morphology(self, db_client) -> neurom.core.Morphology:
        """Getter for the neurom_morphology property.

        Downloads the application/asc asset if not already downloaded
        and loads it using neurom.load_morphology.
        """
        
        if self._neurom_morphology is None:
            self._neurom_morphology = neurom.load_morphology(io.StringIO(self.swc_file_content(db_client)), reader="swc")
        return self._neurom_morphology

    # # @property
    # def morphio_morphology(self, db_client) -> morphio.Morphology:
    #     """Getter for the morphio_morphology property.

    #     Downloads the application/asc asset if not already downloaded
    #     and initializes it as morphio.Morphology([...]).
    #     """
    #     if self._morphio_morphology is None:
    #         self._morphio_morphology = morphio.Morphology(io.StringIO(self.swc_file_content(db_client)), reader="asc")
    #     return self._morphio_morphology
