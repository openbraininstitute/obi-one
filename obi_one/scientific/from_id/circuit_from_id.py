from pathlib import Path
from typing import ClassVar

import entitysdk
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import EntityFromID
from obi_one.core.exception import OBIONEError
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.memodel_circuit import MEModelWithSynapsesCircuit


class CircuitFromID(EntityFromID):
    entitysdk_class: ClassVar[type[entitysdk.models.entity.Entity]] = entitysdk.models.Circuit
    _entity: entitysdk.models.Circuit | None = PrivateAttr(default=None)

    def stage_circuit(
        self,
        *,
        dest_dir: Path = Path(),
        db_client: entitysdk.client.Client = None,
        entity_cache: bool = False,
    ) -> Circuit:
        for asset in self.entity(db_client=db_client).assets:
            if asset.label == "sonata_circuit":
                if not entity_cache and dest_dir.exists():
                    msg = f"Circuit directory '{dest_dir}' already exists and is not empty."
                    raise FileExistsError(msg)

                if (not entity_cache) | (entity_cache and not dest_dir.exists()):
                    entitysdk.staging.circuit.stage_circuit(
                        client=db_client,
                        model=self.entity(db_client),
                        output_dir=dest_dir,
                        max_concurrent=4,
                    )

                circuit = Circuit(
                    name=self.entity(db_client=db_client).name,
                    path=str(dest_dir / "circuit_config.json"),
                )
                return circuit

        msg = f"No 'sonata_circuit' asset found for Circuit with ID {self.id_str}."
        raise OBIONEError(msg)


class MEModelWithSynapsesCircuitFromID(EntityFromID):
    entitysdk_class: ClassVar[type[entitysdk.models.entity.Entity]] = entitysdk.models.Circuit
    _entity: entitysdk.models.Circuit | None = PrivateAttr(default=None)

    def entity(self, db_client: entitysdk.client.Client) -> entitysdk.models.Circuit:
        entity = super().entity(db_client=db_client)
        if entity.scale != "single":
            msg = "Entity must be a circuit of scale 'single'."
            raise OBIONEError(msg)
        return entity

    def stage_circuit(
        self,
        *,
        dest_dir: Path = Path(),
        db_client: entitysdk.client.Client = None,
        entity_cache: bool = False,
    ) -> MEModelWithSynapsesCircuit:
        for asset in self.entity(db_client=db_client).assets:
            if asset.label == "sonata_circuit":
                if not entity_cache and dest_dir.exists():
                    msg = f"Circuit directory '{dest_dir}' already exists and is not empty."
                    raise FileExistsError(msg)

                if (not entity_cache) | (entity_cache and not dest_dir.exists()):
                    entitysdk.staging.circuit.stage_circuit(
                        client=db_client,
                        model=self.entity(db_client),
                        output_dir=dest_dir,
                        max_concurrent=4,
                    )

                circuit = MEModelWithSynapsesCircuit(
                    name=dest_dir.name,
                    path=str(dest_dir / "circuit_config.json"),
                )
                return circuit

        msg = f"No 'sonata_circuit' asset found for Circuit with ID {self.id_str}."
        raise OBIONEError(msg)
