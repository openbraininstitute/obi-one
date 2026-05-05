import logging
import os
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal

from entitysdk import Client
from entitysdk.models import Entity, TaskConfig
from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import Field, PrivateAttr

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.generate_simulations.config.circuit import CircuitDiscriminator

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    ELECTRODE_POSITIONS = "Electrode Location"


class CreateExtracellularRecordingArrayScanConfig(ScanConfig):
    """Description."""

    single_coord_class_name: ClassVar[str] = "CreateExtracellularRecordingArraySingleConfig"
    name: ClassVar[str] = "Create Extracellular Recording Array"
    description: ClassVar[str] = "Description."

    json_schema_extra_additions: ClassVar[dict] = {
        "ui_enabled": False,
        "group_order": [BlockGroup.SETUP, BlockGroup.ELECTRODE_POSITIONS],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = None
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = None

    def input_entities(self, db_client: Client) -> list[Entity]:
        return [n.entity(db_client=db_client) for n in self.initialize.neurons]

    class Initialize(Block):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
            title="Circuit",
            description="Parent circuit to extract a sub-circuit from.",
            json_schema_extra={
                "ui_element": "model_identifier",
            },
        )
        calculation_method: (
            Literal["PointSource", "LineSource", "ObjectiveCSD"]
            | list[Literal["PointSource", "LineSource", "ObjectiveCSD"]]
        ) = Field(
            title="Calculation Method",
            description="Method to calculate extracellular signals from the specified neuron set and"
            " electrode locations.",
            json_schema_extra={
                "ui_element": "string_selection_enhanced",
                "title_by_key": {
                    "PointSource": "Point Source",
                    "LineSource": "Line Source",
                    "ObjectiveCSD": "Objective CSD",
                },
                "description_by_key": {
                    "PointSource": "Calculate extracellular signals using the Point Source method.",
                    "LineSource": "Calculate extracellular signals using the Line Source method.",
                    "ObjectiveCSD": "Calculate extracellular signals using the Objective CSD method.",
                },
            },
        )

    info: Info = Field(
        title="Info",
        description="Information...",
        json_schema_extra={
            "ui_element": "block_single",
            "group": BlockGroup.SETUP,
            "group_order": 0,
        },
    )
    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the extracellular recording array creation.",
        json_schema_extra={
            "ui_element": "block_single",
            "group": BlockGroup.SETUP,
            "group_order": 1,
        },
    )
    # extracellular_locations: ExtracellularLocationsUnion = Field(
    #     title="Extracellular Locations",
    #     description="Electrode locations for recording extracellular signals.",
    #     json_schema_extra={
    #         "ui_element": "block_union",
    #         "group": BlockGroup.ELECTRODE_POSITIONS,
    #         "group_order": 0,
    #     },
    # )

    def create_campaign_entity_with_config(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: Client = None,
    ):
        pass

    def create_campaign_generation_entity(self, generated: list, db_client: Client) -> None:
        pass


class CreateExtracellularRecordingArraySingleConfig(
    CreateExtracellularRecordingArrayScanConfig, SingleConfigMixin
):
    """Description."""

    def create_single_entity_with_config(
        self,
        campaign: TaskConfig,
        db_client: Client,
    ):
        pass


class CreateExtracellularRecordingArrayTask(Task):
    """Task to create an extracellular recording array."""

    config: CreateExtracellularRecordingArraySingleConfig

    _single_task_config_type: ClassVar[TaskConfigType] = None
    _single_task_activity_type: ClassVar[TaskActivityType] = None

    _temp_dir: tempfile.TemporaryDirectory | None = PrivateAttr(default=None)

    def _create_temp_dir(self) -> Path:
        """Creation of a new temporary directory."""
        self._cleanup_temp_dir()  # In case it exists already
        self._temp_dir = tempfile.TemporaryDirectory()
        return Path(self._temp_dir.name).resolve()

    def _cleanup_temp_dir(self) -> None:
        """Clean-up of temporary directory, if any."""
        if self._temp_dir is not None:
            self._temp_dir.cleanup()
            self._temp_dir = None

    def _resolve_circuit(self, *, db_client: Client, entity_cache: bool) -> None:
        """Set circuit variable based on the type of initialize.circuit."""
        if isinstance(self.config.initialize.circuit, Circuit):
            L.info("initialize.circuit is a Circuit instance.")
            self._circuit = self.config.initialize.circuit

        elif isinstance(self.config.initialize.circuit, CircuitFromID):
            L.info("initialize.circuit is a CircuitFromID instance.")
            circuit_id = self.config.initialize.circuit.id_str

            if entity_cache:
                # Use a cache directory at the campaign root --> Won't be deleted after extraction!
                L.info("Use entity cache")
                circuit_dest_dir = (
                    self.config.scan_output_root / "entity_cache" / "sonata_circuit" / circuit_id
                )
            else:
                # Stage circuit in a temporary directory --> Will be deleted after extraction!
                circuit_dest_dir = self._create_temp_dir() / "sonata_circuit"

            self._circuit = self.config.initialize.circuit.stage_circuit(
                db_client=db_client, dest_dir=circuit_dest_dir, entity_cache=entity_cache
            )
            self._circuit_entity = self.config.initialize.circuit.entity(db_client=db_client)

        if self._circuit is None:
            msg = "Failed to resolve circuit!"
            raise OBIONEError(msg)

        return circuit_dest_dir

    def execute(
        self,
        *,
        db_client: Client = None,
        entity_cache: bool = False,
        execution_activity_id: str | None = None,
    ) -> str | None:  # Returns the ID of the extracted circuit
        """Run the task."""
        execution_activity = CreateExtracellularRecordingArrayTask._get_execution_activity(
            db_client=db_client, execution_activity_id=execution_activity_id
        )

        circuit_dest_dir = self._resolve_circuit(db_client=db_client, entity_cache=entity_cache)
        print(circuit_dest_dir)
        files = os.listdir(circuit_dest_dir)
        print(files)

        test_locations = [[0.0, 0.0, 0.0], [50.0, 50.0, 50.0]]  # multiple x, y, z locations to test

        # Use BlueRecording to generate a weights file for the circuit and test locations
        # Using the value of self.config.initialize.calculation_method
        from bluerecording import compute_weights
        from bluerecording.weights import Electrode, ElectrodeType, save_weights
        import numpy as np

        electrodes = {
            f"electrode_{i}": Electrode(
                position=np.array(loc, dtype=float),
                type=ElectrodeType.POINT_SOURCE,
            )
            for i, loc in enumerate(test_locations)
        }

        circuit_config_path = Path(circuit_dest_dir) / "circuit_config.json"
        weights, positions_df, cols, neurite_types, population_name = compute_weights(
            path_to_config=circuit_config_path,
            electrodes=electrodes,
            replace_axons=True,
        )
        print("weights shape:", weights.shape if weights is not None else None)
        print("positions_df shape:", positions_df.shape)
        print("cols shape:", cols.shape)
        print("neurite_types shape:", neurite_types.shape)
        print("population_name:", population_name)

        weights_output_path = Path(circuit_dest_dir) / "weights.h5"
        save_weights(
            weights=weights,
            cols=cols,
            population_name=population_name,
            outputfile=str(weights_output_path),
            electrodes=electrodes,
            neurite_types=neurite_types,
        )
        print("Weights saved to:", weights_output_path)

        # Todo later: Update execution activity (if any)
        # CreateExtracellularRecordingArrayTask._update_execution_activity(
        #     db_client=db_client,
        #     execution_activity=execution_activity,
        #     generated=[registered_circuit_id],
        # )
