import io
import logging
from pathlib import Path
from typing import ClassVar

import entitysdk
import morphio
import neurom
from entitysdk.models import CellMorphology
from entitysdk.models.entity import Entity
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import EntityFromID, LoadAssetMethod

L = logging.getLogger(__name__)


class CellMorphologyFromID(EntityFromID):
    entitysdk_class: ClassVar[type[Entity]] = CellMorphology
    _entity: CellMorphology | None = PrivateAttr(default=None)
    _swc_file_path: Path | None = PrivateAttr(default=None)
    _neurom_morphology: neurom.core.Morphology | None = PrivateAttr(default=None)
    _morphio_morphology: morphio.Morphology | None = PrivateAttr(default=None)
    _swc_file_content: str | None = PrivateAttr(default=None)

    def swc_file_content(self, db_client: entitysdk.client.Client = None) -> None:
        """Function for downloading SWC files of a morphology into memory."""
        if self._swc_file_content is None:
            for asset in self.entity(db_client=db_client).assets:
                if asset.content_type == "application/swc":
                    load_asset_method = LoadAssetMethod.MEMORY
                    if load_asset_method == LoadAssetMethod.MEMORY:
                        L.info("Downloading SWC file for morphology...")

                        # Download the content into memory
                        content = db_client.download_content(
                            entity_id=self.entity(db_client=db_client).id,
                            entity_type=self.entitysdk_type,
                            asset_id=asset.id,
                        ).decode(encoding="utf-8")

                        self._swc_file_content = content
                        break

            if self._swc_file_content is None:
                msg = "No valid application/asc asset found for morphology."
                raise ValueError(msg)

        return self._swc_file_content

    def neurom_morphology(
        self, db_client: entitysdk.client.Client = None
    ) -> neurom.core.Morphology:
        """Getter for the neurom_morphology property.

        Downloads the application/asc asset if not already downloaded
        and loads it using neurom.load_morphology.
        """
        if self._neurom_morphology is None:
            self._neurom_morphology = neurom.load_morphology(
                io.StringIO(self.swc_file_content(db_client)), reader="swc"
            )
        return self._neurom_morphology

    def morphio_morphology(self, db_client: entitysdk.client.Client = None) -> morphio.Morphology:
        """Getter for the morphio_morphology property.

        Downloads the application/asc asset if not already downloaded
        and initializes it as morphio.Morphology([...]).
        """
        msg = "morphio_morphology must be retested."
        raise NotImplementedError(msg)

        if self._morphio_morphology is None:
            self._morphio_morphology = morphio.Morphology(
                io.StringIO(self.swc_file_content(db_client)), reader="swc"
            )
        return self._morphio_morphology
