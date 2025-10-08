from pathlib import Path
from typing import ClassVar

from entitysdk.client import Client
from entitysdk.models import MEModel
from entitysdk.models.entity import Entity
from entitysdk.staging.memodel import stage_sonata_from_memodel
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import EntityFromID
from obi_one.scientific.library.circuit import Circuit


class MEModelFromID(EntityFromID):
    entitysdk_class: ClassVar[type[Entity]] = MEModel
    _entity: MEModel | None = PrivateAttr(default=None)

    def stage_memodel_as_circuit(
        self, db_client: Client = None, dest_dir: Path | None = None
    ) -> Circuit:

        circuit_config_path = stage_sonata_from_memodel(
            client=db_client, memodel=self.entity(db_client), output_dir=dest_dir
        )

        return Circuit(name="single_cell", path=str(circuit_config_path))
