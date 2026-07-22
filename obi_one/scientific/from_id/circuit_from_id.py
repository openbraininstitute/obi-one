from pathlib import Path
from typing import ClassVar

from entitysdk import Client, models
from entitysdk.staging.circuit import stage_circuit
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import EntityFromID
from obi_one.core.exception import OBIONEError
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.memodel_circuit import MEModelWithSynapsesCircuit


class CircuitFromID(EntityFromID):
    entitysdk_class: ClassVar[type[models.Entity]] = models.Circuit
    _entity: models.Circuit | None = PrivateAttr(default=None)

    def stage_circuit(
        self,
        *,
        dest_dir: Path = Path(),
        db_client: Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,
    ) -> Circuit:
        for asset in self.entity(db_client=db_client).assets:
            if asset.label == "sonata_circuit":
                if not entity_cache and dest_dir.exists():
                    msg = f"Circuit directory '{dest_dir}' already exists and is not empty."
                    raise FileExistsError(msg)

                if (not entity_cache) | (entity_cache and not dest_dir.exists()):
                    stage_circuit(
                        client=db_client,
                        model=self.entity(db_client),  # ty:ignore[invalid-argument-type]
                        output_dir=dest_dir,
                        max_concurrent=4,
                    )

                circuit = Circuit(
                    name=str(self),
                    path=str(dest_dir / "circuit_config.json"),
                )
                return circuit

        msg = f"No 'sonata_circuit' asset found for Circuit with ID {self.id_str}."
        raise OBIONEError(msg)


class MEModelWithSynapsesCircuitFromID(EntityFromID):
    entitysdk_class: ClassVar[type[models.Entity]] = models.Circuit
    _entity: models.Circuit | None = PrivateAttr(default=None)

    def entity(self, db_client: Client) -> models.Circuit:
        entity = super().entity(db_client=db_client)
        if entity.scale != "single":  # ty:ignore[unresolved-attribute]
            msg = "Entity must be a circuit of scale 'single'."
            raise OBIONEError(msg)
        return entity  # ty:ignore[invalid-return-type]

    def stage_circuit(
        self,
        *,
        dest_dir: Path = Path(),
        db_client: Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,
    ) -> MEModelWithSynapsesCircuit:
        for asset in self.entity(db_client=db_client).assets:
            if asset.label == "sonata_circuit":
                if not entity_cache and dest_dir.exists():
                    msg = f"Circuit directory '{dest_dir}' already exists and is not empty."
                    raise FileExistsError(msg)

                if (not entity_cache) | (entity_cache and not dest_dir.exists()):
                    stage_circuit(
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
