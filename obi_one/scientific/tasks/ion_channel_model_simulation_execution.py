import json
import logging
from pathlib import Path
from typing import ClassVar

import entitysdk
from entitysdk import models
from entitysdk.models.activity import Activity
from entitysdk.staging.simulation import stage_simulation

from obi_one.core.deserialize import deserialize_obi_object_from_json_data
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.library.simulation.process import compile_mechanisms, run_simulation
from obi_one.scientific.library.simulation.registration import register_simulation_results
from obi_one.scientific.library.simulation.schemas import SimulationMetadata
from obi_one.scientific.library.simulation.staging import (
    get_simulation_parameters,
    stage_ion_channel_models_as_circuit,
)
from obi_one.scientific.tasks.generate_simulations.config.ion_channel_models import (
    IonChannelModelSimulationSingleConfig,
)
from obi_one.types import SimulationBackend
from obi_one.utils import db_sdk
from obi_one.utils.filesystem import create_dir

L = logging.getLogger(__name__)


class IonChannelModelSimulationExecutionSingleConfig(ScanConfig, SingleConfigMixin):
    pass


class IonChannelModelSimulationExecutionTask(Task):
    config: IonChannelModelSimulationExecutionSingleConfig
    activity_type: ClassVar[type[Activity]] = models.SimulationExecution

    def get_generation_single_config(
        self, db_client: entitysdk.client.Client
    ) -> IonChannelModelSimulationSingleConfig:
        config_asset = db_sdk.get_entity_asset_by_label(
            client=db_client,
            config=self.config.single_entity,
            asset_label="simulation_generation_config",  # ty:ignore[invalid-argument-type]
        )

        json_str = db_client.download_content(
            entity_id=self.config.single_entity.id,  # ty:ignore[invalid-argument-type]
            entity_type=entitysdk.models.Simulation,  # ty:ignore[possibly-missing-submodule]
            asset_id=config_asset.id,
        ).decode(encoding="utf-8")

        json_dict = json.loads(json_str)
        single_config = deserialize_obi_object_from_json_data(json_dict)
        return single_config  # ty:ignore[invalid-return-type]

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client,
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None,
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
        output_dir = Path(self.config.coordinate_output_root).resolve()
        data_dir = create_dir(output_dir / "data")
        results_dir = create_dir(output_dir / "outputs")

        simulation_entity = self.config.single_entity

        if execution_activity_id is not None:
            execution_activity = db_client.get_entity(
                entity_id=execution_activity_id,  # ty:ignore[invalid-argument-type]
                entity_type=self.activity_type,
            )

        generation_single_config = self.get_generation_single_config(db_client)

        staged_circuit = stage_ion_channel_models_as_circuit(
            client=db_client,
            ion_channel_models=generation_single_config.ion_channel_models,
            output_dir=create_dir(data_dir / "circuit"),
        )
        libnrnmech_path = compile_mechanisms(staged_circuit)
        simulation_entity = self.config.single_entity

        simulation_metadata = SimulationMetadata(
            simulation_id=simulation_entity.id,  # ty:ignore[invalid-argument-type]
        )
        staged_simulation_config_path = stage_simulation(
            client=db_client,
            model=simulation_entity,  # ty:ignore[invalid-argument-type]
            circuit_config_path=staged_circuit.path,  # ty:ignore[invalid-argument-type]
            output_dir=data_dir,
            override_results_dir=results_dir,
        )
        simulation_parameters = get_simulation_parameters(
            staged_simulation_config_path, libnrnmech_path
        )

        simulation_results = run_simulation(
            parameters=simulation_parameters,
            results_dir=results_dir,
            simulation_backend=SimulationBackend.bluecellulab,
        )

        if execution_activity_id is not None:
            L.info("Registering entities...")
            generated_entity = register_simulation_results(
                client=db_client,
                simulation_results=simulation_results,
                simulation_metadata=simulation_metadata,
            )
            db_client.update_entity(
                entity_id=execution_activity.id,  # ty:ignore[invalid-argument-type]
                entity_type=self.activity_type,
                attrs_or_entity={"generated_ids": [str(generated_entity.id)]},  # ty:ignore[unresolved-attribute]
            )

        L.info("Simulation completed")
