import logging
from abc import abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, cast
from uuid import UUID

import entitysdk
from entitysdk import models
from entitysdk.models.activity import Activity
from entitysdk.staging.simulation import stage_simulation

from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.simulation.process import compile_mechanisms, run_simulation
from obi_one.scientific.library.simulation.registration import register_simulation_results
from obi_one.scientific.library.simulation.schemas import SimulationMetadata
from obi_one.scientific.library.simulation.staging import get_simulation_parameters
from obi_one.types import SimulationBackend
from obi_one.utils.filesystem import create_dir

if TYPE_CHECKING:
    from entitysdk.models import Simulation

L = logging.getLogger(__name__)


class SimulationExecutionSingleConfig(ScanConfig, SingleConfigMixin):
    pass


class SimulationExecutionTask(Task):
    """Run a staged simulation and optionally register its outputs."""

    config: SimulationExecutionSingleConfig
    activity_type: ClassVar[type[Activity]] = models.SimulationExecution
    simulation_backend: ClassVar[SimulationBackend] = SimulationBackend.neurodamus

    def _get_simulation_entity(self, db_client: entitysdk.client.Client) -> models.Simulation:  # noqa: ARG002
        return cast("Simulation", self.config.single_entity)

    @abstractmethod
    def _stage_circuit(
        self,
        *,
        db_client: entitysdk.client.Client,
        data_dir: Path,
        simulation_entity: models.Simulation,
    ) -> Circuit:
        """Stage circuit inputs required for simulation execution."""

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client,
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: UUID | str | None,
    ) -> None:
        """Prepare inputs, run the simulation, and optionally register outputs."""
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
        simulation_metadata = SimulationMetadata(
            simulation_id=simulation_entity.id,
        )
        L.info("Simulation: %s", simulation_entity.id)

        staged_circuit = self._stage_circuit(
            db_client=db_client,
            data_dir=data_dir,
            simulation_entity=simulation_entity,
        )
        L.info("Circuit staged at %s", staged_circuit.directory)

        mechanism_build = compile_mechanisms(
            mechanisms_dir=staged_circuit.mechanisms_dir.resolve(),
            output_dir=staged_circuit.directory.resolve(),
            simulation_backend=self.simulation_backend,
        )
        L.info("Mechanisms compiled: %s", mechanism_build)

        staged_simulation_config_path = stage_simulation(
            client=db_client,
            model=simulation_entity,
            circuit_config_path=Path(staged_circuit.path),
            output_dir=data_dir,
            override_results_dir=results_dir,
        )
        L.info("Simulation staged at %s", staged_simulation_config_path)

        simulation_parameters = get_simulation_parameters(
            simulation_backend=self.simulation_backend,
            simulation_config_file=staged_simulation_config_path,
            mechanism_build=mechanism_build,
        )
        L.info("Collected simulation parameters: %s", simulation_parameters)

        simulation_results = run_simulation(
            parameters=simulation_parameters,
            results_dir=results_dir,
            simulation_backend=self.simulation_backend,
        )
        L.info("Collected simulation results: %s", simulation_results)

        if execution_activity is not None:
            L.info("Registering simulation results...")
            generated_entity = register_simulation_results(
                client=db_client,
                simulation_results=simulation_results,
                simulation_metadata=simulation_metadata,
            )
            L.info("Generated %s(id=%s)", type(generated_entity), generated_entity.id)

            db_client.update_entity(
                entity_id=execution_activity.id,
                entity_type=self.activity_type,
                attrs_or_entity={"generated_ids": [str(generated_entity.id)]},
            )
            L.info("Updated %s(id=%s)", type(execution_activity), execution_activity.id)

        L.info("Simulation completed.")
