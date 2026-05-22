import logging
from pathlib import Path
from typing import ClassVar, cast
from uuid import UUID

import entitysdk
from entitysdk import models
from entitysdk.models.activity import Activity
from entitysdk.staging.simulation import stage_simulation

from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.library.simulation.process import compile_mechanisms, run_simulation
from obi_one.scientific.library.simulation.registration import register_simulation_results
from obi_one.scientific.library.simulation.schemas import SimulationMetadata
from obi_one.scientific.library.simulation.staging import get_simulation_parameters, stage_circuit
from obi_one.types import SimulationBackend
from obi_one.utils import db_sdk
from obi_one.utils.filesystem import create_dir

L = logging.getLogger(__name__)


class CircuitSimulationExecutionSingleConfig(ScanConfig, SingleConfigMixin):
    pass


class CircuitSimulationExecutionTask(Task):
    config: CircuitSimulationExecutionSingleConfig
    activity_type: ClassVar[type[Activity]] = models.SimulationExecution

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client,
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: UUID | None,
    ) -> None:
        """Execute the ion channel model simulation task.

        This method prepares inputs, runs the simulation process,
        and optionally registers the outputs in the database.

        Args:
            db_client: Client used to interact with the database.
            entity_cache: Unused parameter
            execution_activity_id:
                The ID of the execution activity entity.

                If provided, the execution is considered *tracked*:
                the generated outputs are registered in the database and
                linked to the corresponding activity entity.

                If ``None``, the execution is considered *local*:
                the process runs and produces outputs on disk, but no data
                is registered in the database and no entities are updated.

        Note:
            When ``execution_activity_id`` is ``None``, the execution runs
            locally and does **not** register any generated resources in
            the database.
        """
        simulation_backend = SimulationBackend.neurodamus  # TODO: Add in config perhaps?
        output_dir = Path(self.config.coordinate_output_root).resolve()
        data_dir = create_dir(output_dir / "data")
        results_dir = create_dir(output_dir / "outputs")

        if execution_activity_id is not None:
            execution_activity = db_client.get_entity(
                entity_id=execution_activity_id,
                entity_type=self.activity_type,
            )

        simulation_entity = db_sdk.get_identifiable(
            client=db_client,
            identifiable_id=cast("UUID", self.config.single_entity.id),
            identifiable_type=models.Simulation,
        )
        simulation_metadata = SimulationMetadata(
            simulation_id=cast("UUID", simulation_entity.id),
        )
        circuit_entity = db_client.get_entity(
            entity_id=simulation_entity.entity_id,
            entity_type=models.Circuit,
        )
        staged_circuit = stage_circuit(
            client=db_client,
            model=circuit_entity,
            output_dir=create_dir(data_dir / "circuit"),
        )
        L.info("Staged Circuit %s config at %s", circuit_entity.id, staged_circuit.path)
        staged_simulation_config_path = stage_simulation(
            client=db_client,
            model=simulation_entity,
            circuit_config_path=Path(staged_circuit.path),
            output_dir=data_dir,
            override_results_dir=results_dir,
        )
        L.info(
            "Staged Simulation %s config at %s. Extracted metadata: %s",
            simulation_entity.id,
            staged_simulation_config_path,
            simulation_metadata,
        )
        L.info("Compiling mechanisms in %s...", staged_circuit.mechanisms_dir)
        mechanism_build = compile_mechanisms(
            mechanisms_dir=staged_circuit.mechanisms_dir.resolve(),
            output_dir=staged_circuit.directory.resolve(),
            simulation_backend=simulation_backend,
        )
        L.info("Mechanisms compiled successfully.")

        simulation_parameters = get_simulation_parameters(
            simulation_backend=simulation_backend,
            simulation_config_file=staged_simulation_config_path,
            mechanism_build=mechanism_build,
        )
        L.info("Simulation parameters: %s", simulation_parameters)

        L.info("Running circuit simulation...")
        simulation_results = run_simulation(
            parameters=simulation_parameters,
            results_dir=results_dir,
            simulation_backend=simulation_backend,
        )
        L.info("Simulation results: %s", simulation_results)

        if execution_activity_id is not None:
            L.info("Registering simulation results...")
            generated_entity = register_simulation_results(
                client=db_client,
                simulation_results=simulation_results,
                simulation_metadata=simulation_metadata,
            )
            L.info("Generated SimulationResult %s", generated_entity.id)
            db_client.update_entity(
                entity_id=cast("UUID", execution_activity.id),
                entity_type=self.activity_type,
                attrs_or_entity={"generated_ids": [str(generated_entity.id)]},
            )

        L.info("Simulation completed.")
