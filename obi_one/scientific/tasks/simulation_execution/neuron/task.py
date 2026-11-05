import logging
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, cast, override

import entitysdk
from entitysdk import models
from entitysdk.types import AssetLabel

from obi_one.db_sdk import db_sdk
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.simulation.neuron.process import compile_mechanisms, run_simulation
from obi_one.scientific.library.simulation.neuron.schemas import SimulationResults
from obi_one.scientific.library.simulation.neuron.staging import (
    get_simulation_parameters,
    stage_circuit,
    stage_ion_channel_models_as_circuit,
    stage_memodel_as_circuit,
)
from obi_one.scientific.tasks.simulation_execution.neuron.config import (
    CircuitSimulationExecutionSingleConfig,
    IonChannelModelSimulationExecutionSingleConfig,
    SingleNeuronSimulationExecutionSingleConfig,
    SingleNeuronSynaptomeSimulationExecutionSingleConfig,
)
from obi_one.scientific.tasks.simulation_execution.task import SimulationExecutionTask
from obi_one.types import SimulationBackend
from obi_one.utils.benchmark import log_timing
from obi_one.utils.filesystem import create_dir

if TYPE_CHECKING:
    from obi_one.scientific.library.memodel_circuit import MEModelCircuit
    from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_ion_channel_models import (  # ruff: ignore[line-too-long]
        IonChannelModelSimulationSingleConfig,
    )
    from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model import (
        MEModelSimulationSingleConfig,
    )

L = logging.getLogger(__name__)


class NeuronSimulationExecutionTask(SimulationExecutionTask):
    simulation_backend: ClassVar[SimulationBackend] = SimulationBackend.neurodamus

    @override
    def _run_simulation(
        self,
        *,
        staged_circuit: Circuit,
        simulation_config_path: Path,
        results_dir: Path,
    ) -> SimulationResults:
        cache_dir = self.shared_cache.mechanisms_dir if self.shared_cache is not None else None
        with log_timing("compile_mechanisms"):
            mechanism_build = compile_mechanisms(
                mechanisms_dirs=[staged_circuit.mechanisms_dir.resolve()],
                output_dir=staged_circuit.directory.resolve(),
                simulation_backend=self.simulation_backend,
                cache_dir=cache_dir,
            )
        L.info("Mechanisms compiled: %s", mechanism_build)

        with log_timing("get_simulation_parameters"):
            simulation_parameters = get_simulation_parameters(
                simulation_backend=self.simulation_backend,
                simulation_config_file=simulation_config_path,
                mechanism_build=mechanism_build,
            )
        L.info("Collected simulation parameters: %s", simulation_parameters)

        return run_simulation(
            parameters=simulation_parameters,
            results_dir=results_dir,
            simulation_backend=self.simulation_backend,
        )


class CircuitSimulationExecutionTask(NeuronSimulationExecutionTask):
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


class IonChannelModelSimulationExecutionTask(NeuronSimulationExecutionTask):
    config: IonChannelModelSimulationExecutionSingleConfig

    def get_generation_single_config(
        self, db_client: entitysdk.client.Client
    ) -> "IonChannelModelSimulationSingleConfig":
        from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_ion_channel_models import (  # ruff: ignore[line-too-long, import-outside-top-level]
            IonChannelModelSimulationSingleConfig,
        )

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


class SingleNeuronSimulationExecutionTask(NeuronSimulationExecutionTask):
    config: SingleNeuronSimulationExecutionSingleConfig

    def get_generation_single_config(
        self, db_client: entitysdk.client.Client
    ) -> "MEModelSimulationSingleConfig":
        from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model import (  # ruff: ignore[import-outside-top-level]
            MEModelSimulationSingleConfig,
        )

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
