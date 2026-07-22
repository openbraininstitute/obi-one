from pathlib import Path
from typing import TYPE_CHECKING, cast, override

import entitysdk
from entitysdk import models
from entitysdk.types import AssetLabel

from obi_one.core.deserialize import deserialize_obi_object_from_json_data
from obi_one.core.exception import OBIONEError
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.simulation.neuron.staging import stage_memodel_as_circuit
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model import (
    MEModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.simulation_execution.base import (
    SimulationExecutionSingleConfig,
    SimulationExecutionTask,
)
from obi_one.utils import db_sdk
from obi_one.utils.filesystem import create_dir

if TYPE_CHECKING:
    from obi_one.scientific.library.memodel_circuit import MEModelCircuit


class SingleNeuronSimulationExecutionSingleConfig(SimulationExecutionSingleConfig):
    pass


class SingleNeuronSimulationExecutionTask(SimulationExecutionTask):
    config: SingleNeuronSimulationExecutionSingleConfig

    def get_generation_single_config(
        self, db_client: entitysdk.client.Client
    ) -> MEModelSimulationSingleConfig:
        json_dict = db_sdk.select_json_asset_content(
            client=db_client,
            entity=self.config.single_entity,
            selection={"label": AssetLabel.simulation_generation_config},
        )
        config = deserialize_obi_object_from_json_data(json_dict)
        if not isinstance(config, MEModelSimulationSingleConfig):
            msg = f"Expected MEModelSimulationSingleConfig but got {type(config)}."
            raise OBIONEError(msg)
        return config

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
        )
