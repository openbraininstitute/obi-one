import logging
from pathlib import Path
from typing import override

import entitysdk
from entitysdk import models

from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.simulation.staging import stage_circuit
from obi_one.scientific.tasks.simulation_execution.base import (
    SimulationExecutionSingleConfig,
    SimulationExecutionTask,
)
from obi_one.utils import db_sdk
from obi_one.utils.filesystem import create_dir

L = logging.getLogger(__name__)


class CircuitSimulationExecutionSingleConfig(SimulationExecutionSingleConfig):
    pass


class CircuitSimulationExecutionTask(SimulationExecutionTask):
    config: CircuitSimulationExecutionSingleConfig

    @override
    def _get_simulation_entity(self, db_client: entitysdk.client.Client) -> models.Simulation:
        simulation_entity = db_sdk.get_identifiable(
            client=db_client,
            identifiable_id=self.config.single_entity.id,
            identifiable_type=models.Simulation,
        )
        L.info("Fetched simulation config %s", simulation_entity.id)
        return simulation_entity

    @override
    def _stage_circuit(
        self,
        *,
        db_client: entitysdk.client.Client,
        data_dir: Path,
        simulation_entity: models.Simulation,
    ) -> Circuit:
        circuit_entity = db_client.get_entity(
            entity_id=simulation_entity.entity_id,
            entity_type=models.Circuit,
        )
        L.info("Fetched circuit %s", circuit_entity.id)

        staged_circuit = stage_circuit(
            client=db_client,
            model=circuit_entity,
            output_dir=create_dir(data_dir / "circuit"),
        )
        L.info("Staged circuit %s config at %s", circuit_entity.id, staged_circuit.path)
        return staged_circuit
