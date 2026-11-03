import logging
from abc import abstractmethod
from pathlib import Path
from typing import ClassVar, cast
from uuid import UUID

import entitysdk
from entitysdk import models
from entitysdk.models.activity import Activity
from entitysdk.staging.simulation import stage_simulation

from obi_one.core.task import Task
from obi_one.db_sdk.registration.simulation_result import register_simulation_results
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.simulation.neuron.schemas import (
    SimulationMetadata,
    SimulationResults,
)
from obi_one.scientific.tasks.simulation_execution.config import SimulationExecutionSingleConfig
from obi_one.utils.benchmark import log_timing
from obi_one.utils.filesystem import create_dir

L = logging.getLogger(__name__)


class SimulationExecutionTask(Task):
    """Stage a simulation, run it with a simulator-specific hook and register its outputs."""

    config: SimulationExecutionSingleConfig
    activity_type: ClassVar[type[Activity]] = models.SimulationExecution

    def _get_simulation_entity(self, db_client: entitysdk.client.Client) -> models.Simulation:  # ruff: ignore[unused-method-argument]
        return cast("models.Simulation", self.config.single_entity)

    @abstractmethod
    def _stage_circuit(
        self,
        *,
        db_client: entitysdk.client.Client,
        data_dir: Path,
        simulation_entity: models.Simulation,
    ) -> Circuit:
        """Stage the circuit inputs required for the simulation."""

    @abstractmethod
    def _run_simulation(
        self,
        *,
        staged_circuit: Circuit,
        simulation_config_path: Path,
        results_dir: Path,
    ) -> SimulationResults:
        """Run the staged simulation and return the produced reports."""

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client,
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: UUID | str | None,
    ) -> None:
        output_dir = Path(self.config.coordinate_output_root).resolve()
        data_dir = create_dir(output_dir / "data")
        results_dir = create_dir(output_dir / "outputs")

        execution_activity = None
        if execution_activity_id is not None:
            execution_activity = db_client.get_entity(
                entity_id=execution_activity_id,  # ty:ignore[invalid-argument-type]
                entity_type=self.activity_type,
            )
            L.info("Activity: %s(id=%s)", type(execution_activity), execution_activity.id)

        simulation_entity = self._get_simulation_entity(db_client)
        simulation_metadata = SimulationMetadata(simulation_id=simulation_entity.id)
        L.info("Simulation: %s", simulation_entity.id)

        with log_timing("stage_circuit"):
            staged_circuit = self._stage_circuit(
                db_client=db_client,
                data_dir=data_dir,
                simulation_entity=simulation_entity,
            )
        L.info("Circuit staged at %s", staged_circuit.path)

        with log_timing("stage_simulation"):
            staged_simulation_config_path = stage_simulation(
                client=db_client,
                model=simulation_entity,
                circuit_config_path=Path(staged_circuit.path),
                output_dir=data_dir,
                override_results_dir=results_dir,
            )
        L.info("Simulation staged at %s", staged_simulation_config_path)

        with log_timing("run_simulation"):
            simulation_results = self._run_simulation(
                staged_circuit=staged_circuit,
                simulation_config_path=staged_simulation_config_path,
                results_dir=results_dir,
            )
        L.info("Collected simulation results: %s", simulation_results)

        if execution_activity is not None:
            L.info("Registering simulation results...")
            with log_timing("register_simulation_results"):
                generated_entity = register_simulation_results(
                    client=db_client,
                    simulation_id=simulation_metadata.simulation_id,
                    spike_report_file=simulation_results.spike_report_file,
                    voltage_report_files=simulation_results.voltage_report_files,
                    lfp_report_files=simulation_results.lfp_report_files,
                    name="Simulation result",
                    description="Simulation result",
                )
                L.info("Generated %s(id=%s)", type(generated_entity), generated_entity.id)

                db_client.update_entity(
                    entity_id=execution_activity.id,
                    entity_type=self.activity_type,
                    attrs_or_entity={"generated_ids": [str(generated_entity.id)]},
                )
            L.info("Updated %s(id=%s)", type(execution_activity), execution_activity.id)

        L.info("Simulation completed.")
