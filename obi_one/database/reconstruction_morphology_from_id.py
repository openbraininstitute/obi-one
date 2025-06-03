from pathlib import Path
from typing import ClassVar

import morphio
import neurom
from entitysdk.models import ReconstructionMorphology
from entitysdk.models.entity import Entity
from pydantic import PrivateAttr

from obi_one.database.db_manager import db
from obi_one.database.entity_from_id import EntityFromID


class ReconstructionMorphologyFromID(EntityFromID):
    entitysdk_class: ClassVar[type[Entity]] = ReconstructionMorphology
    _entity: ReconstructionMorphology | None = PrivateAttr(default=None)
    _swc_file_path: Path | None = PrivateAttr(default=None)
    _neurom_morphology: neurom.core.Morphology | None = PrivateAttr(default=None)
    _morphio_morphology: morphio.Morphology | None = PrivateAttr(default=None)

    @property
    def swc_file(self) -> Path:
        """Function for downloading SWC files of a morphology."""
        if self._swc_file_path is None:
            for asset in self.entity.assets:
                if asset.content_type == "application/asc":
                    file_output_path = Path(db.entity_file_store_path) / asset.full_path
                    file_output_path.parent.mkdir(parents=True, exist_ok=True)

                    db.client.download_file(
                        entity_id=self.entity.id,
                        entity_type=self.entitysdk_type,
                        asset_id=asset.id,
                        output_path=file_output_path,
                        token=db.token,
                    )

                    self._swc_file_path = file_output_path
                    break

            if self._swc_file_path is None:
                msg = "No valid application/asc asset found for morphology."
                raise ValueError(msg)

        return self._swc_file_path

    @property
    def neurom_morphology(self) -> neurom.core.Morphology:
        """Getter for the neurom_morphology property.

        Downloads the application/asc asset if not already downloaded
        and loads it using neurom.load_morphology.
        """
        if self._neurom_morphology is None:
            self._neurom_morphology = neurom.load_morphology(self.swc_file)
        return self._neurom_morphology

    @property
    def morphio_morphology(self) -> morphio.Morphology:
        """Getter for the morphio_morphology property.

        Downloads the application/asc asset if not already downloaded
        and initializes it as morphio.Morphology([...]).
        """
        if self._morphio_morphology is None:
            self._morphio_morphology = morphio.Morphology(self.swc_file)
        return self._morphio_morphology
