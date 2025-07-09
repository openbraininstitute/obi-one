from pathlib import Path
from typing import ClassVar

import morphio
import neurom
import entitysdk
from entitysdk.models import Circuit
from entitysdk.models.entity import Entity
from entitysdk.staging.circuit import stage_circuit
from pydantic import PrivateAttr

from obi_one.database.db_manager import db
from obi_one.database.entity_from_id import EntityFromID, LoadAssetMethod

import io

class CircuitFromID(EntityFromID):
    entitysdk_class: ClassVar[type[Entity]] = Circuit
    _entity: Circuit | None = PrivateAttr(default=None)

    def download_circuit_directory(self, dest_dir=Path(), db_client: entitysdk.client.Client = None) -> None: 

        for asset in self.entity(db_client=db_client).assets:
            if asset.label == "sonata_circuit":

                circuit_dir = dest_dir / asset.path
                if circuit_dir.exists():
                    raise FileExistsError(f"Circuit directory '{circuit_dir}' already exists and is not empty.")

                circuit = db_client.get_entity(entity_id=self.id_str, entity_type=Circuit)
                stage_circuit(client=db_client, model=circuit, output_dir=circuit_dir, max_concurrent=4)

                break