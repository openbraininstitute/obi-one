import logging
from abc import abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, cast, override
from uuid import UUID

import entitysdk
from entitysdk import models
from entitysdk.models.activity import Activity
from entitysdk.staging.simulation import stage_simulation
from entitysdk.types import AssetLabel

from obi_one.core.task import Task
from obi_one.db_sdk import db_sdk
from obi_one.db_sdk.registration.simulation_result import register_simulation_results
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.simulation.neuron.process import compile_mechanisms, run_simulation
from obi_one.scientific.library.simulation.neuron.schemas import SimulationMetadata
from obi_one.scientific.library.simulation.neuron.staging import (
    get_simulation_parameters,
    stage_circuit,
    stage_ion_channel_models_as_circuit,
    stage_memodel_as_circuit,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_ion_channel_models import (
    IonChannelModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model import (
    MEModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.simulation_execution.neuron.config import (
    CircuitSimulationExecutionSingleConfig,
    IonChannelModelSimulationExecutionSingleConfig,
    SimulationExecutionSingleConfig,
    SingleNeuronSimulationExecutionSingleConfig,
    SingleNeuronSynaptomeSimulationExecutionSingleConfig,
)
from obi_one.types import SimulationBackend
from obi_one.utils.benchmark import log_timing
from obi_one.utils.filesystem import create_dir

if TYPE_CHECKING:
    from entitysdk.models import Simulation

    from obi_one.scientific.library.memodel_circuit import MEModelCircuit

L = logging.getLogger(__name__)


class SimulationExecutionTask(Task):
    """Run a staged simulation and optionally register its outputs."""

    config: SimulationExecutionSingleConfig
    activity_type: ClassVar[type[Activity]] = models.SimulationExecution
    simulation_backend: ClassVar[SimulationBackend] = SimulationBackend.neurodamus

    def _get_simulation_entity(self, db_client: entitysdk.client.Client) -> models.Simulation:  # ruff: ignore[unused-method-argument]
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
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
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

        with log_timing("stage_circuit"):
            staged_circuit = self._stage_circuit(
                db_client=db_client,
                data_dir=data_dir,
                simulation_entity=simulation_entity,
            )
        L.info("Circuit staged at %s", staged_circuit.directory)

        cache_dir = self.shared_cache.mechanisms_dir if self.shared_cache is not None else None
        with log_timing("compile_mechanisms"):
            mechanism_build = compile_mechanisms(
                mechanisms_dirs=[staged_circuit.mechanisms_dir.resolve()],
                output_dir=staged_circuit.directory.resolve(),
                simulation_backend=self.simulation_backend,
                cache_dir=cache_dir,
            )
        L.info("Mechanisms compiled: %s", mechanism_build)

        with log_timing("stage_simulation"):
            staged_simulation_config_path = stage_simulation(
                client=db_client,
                model=simulation_entity,
                circuit_config_path=Path(staged_circuit.path),
                output_dir=data_dir,
                override_results_dir=results_dir,
            )
        L.info("Simulation staged at %s", staged_simulation_config_path)

        with log_timing("get_simulation_parameters"):
            simulation_parameters = get_simulation_parameters(
                simulation_backend=self.simulation_backend,
                simulation_config_file=staged_simulation_config_path,
                mechanism_build=mechanism_build,
            )
        L.info("Collected simulation parameters: %s", simulation_parameters)

        with log_timing("run_simulation"):
            simulation_results = run_simulation(
                parameters=simulation_parameters,
                results_dir=results_dir,
                simulation_backend=self.simulation_backend,
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
            max_concurrent=8,
        )
        L.info("Staged circuit %s config at %s", circuit_entity.id, staged_circuit.path)
        return staged_circuit


class IonChannelModelSimulationExecutionTask(SimulationExecutionTask):
    config: IonChannelModelSimulationExecutionSingleConfig

    def get_generation_single_config(
        self, db_client: entitysdk.client.Client
    ) -> IonChannelModelSimulationSingleConfig:
        json_bytes = db_sdk.select_asset_content(
            client=db_client,
            entity=self.config.single_entity,
            selection={"label": AssetLabel.simulation_generation_config},
        )
        return IonChannelModelSimulationSingleConfig.model_validate_json(json_bytes)

    @override
    def _stage_circuit(
        self,
        *,
        db_client: entitysdk.client.Client,
        data_dir: Path,
        simulation_entity: models.Simulation,
    ) -> Circuit:
        generation_single_config = self.get_generation_single_config(db_client)
        return stage_ion_channel_models_as_circuit(
            client=db_client,
            ion_channel_models=generation_single_config.ion_channel_models,
            output_dir=create_dir(data_dir / "circuit"),
        )


class SingleNeuronSimulationExecutionTask(SimulationExecutionTask):
    config: SingleNeuronSimulationExecutionSingleConfig

    def get_generation_single_config(
        self, db_client: entitysdk.client.Client
    ) -> MEModelSimulationSingleConfig:
        json_bytes = db_sdk.select_asset_content(
            client=db_client,
            entity=self.config.single_entity,
            selection={"label": AssetLabel.simulation_generation_config},
        )
        return MEModelSimulationSingleConfig.model_validate_json(json_bytes)

    @override
    def _stage_circuit(
        self,
        *,
        db_client: entitysdk.client.Client,
        data_dir: Path,
        simulation_entity: models.Simulation,
    ) -> Circuit:
        generation_single_config = self.get_generation_single_config(db_client)
        return stage_memodel_as_circuit(
            client=db_client,
            circuit=cast("MEModelCircuit", generation_single_config.initialize.circuit),
            output_dir=create_dir(data_dir / "circuit"),
            max_concurrent=8,
        )


class SingleNeuronSynaptomeSimulationExecutionTask(CircuitSimulationExecutionTask):
    config: SingleNeuronSynaptomeSimulationExecutionSingleConfig
