import os
from pathlib import Path
from typing import override

import entitysdk
from entitysdk import models

from obi_one.db_sdk import db_sdk
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.simulation.neuron.schemas import SimulationResults
from obi_one.scientific.library.simulation.neuron.staging import stage_circuit
from obi_one.scientific.tasks.simulation_execution.nest.config import (
    NestCircuitSimulationExecutionSingleConfig,
)
from obi_one.scientific.tasks.simulation_execution.task import SimulationExecutionTask
from obi_one.utils.filesystem import create_dir


def simulation_thread_count() -> int:
    """NEST threads: the CPUs the launch system allocated (JOB_CPUS), else 1."""
    return int(os.environ.get("JOB_CPUS") or 1)


class NestCircuitSimulationExecutionTask(SimulationExecutionTask):
    config: NestCircuitSimulationExecutionSingleConfig

    @override
    def _get_simulation_entity(self, db_client: entitysdk.client.Client) -> models.Simulation:
        return db_sdk.get_identifiable(
            client=db_client,
            identifiable_id=self.config.single_entity.id,
            identifiable_type=models.Simulation,
        )

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
        return stage_circuit(
            client=db_client,
            model=circuit_entity,
            output_dir=create_dir(data_dir / "circuit"),
            max_concurrent=8,
        )

    @override
    def _run_simulation(
        self,
        *,
        staged_circuit: Circuit,
        simulation_config_path: Path,
        results_dir: Path,
    ) -> SimulationResults:
        from obi_one.scientific.library.simulation.nest.simulate_nest import (  # ruff: ignore[import-outside-top-level]
            run_simulation,
        )

        return run_simulation(simulation_config_path, num_threads=simulation_thread_count())
