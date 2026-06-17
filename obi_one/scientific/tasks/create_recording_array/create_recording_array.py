import logging
import tempfile
import typing
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal

from entitysdk import Client
from entitysdk.models import Entity, TaskConfig
from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import Field, PrivateAttr

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.tasks.generate_simulations.config.circuit import CircuitDiscriminator
from obi_one.utils import db_sdk

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

    _campaign_task_config_type: ClassVar[TaskConfigType] = None  # ty:ignore[invalid-assignment]
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = None  # ty:ignore[invalid-assignment]

    @typing.override
    def input_entities(self, db_client: Client) -> list[Entity]:
        return []

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
            description=(
                "Method to calculate extracellular signals from the"
                " specified neuron set and electrode locations."
            ),
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
                    "ObjectiveCSD": (
                        "Calculate extracellular signals using the Objective CSD method."
                    ),
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

    def create_campaign_entity_with_config(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: Client = None,  # ty:ignore[invalid-parameter-default]
    ) -> None:  # ty:ignore[invalid-method-override]
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
    ) -> None:  # ty:ignore[invalid-method-override]
        pass


class CreateExtracellularRecordingArrayTask(Task):
    """Task to create an extracellular recording array."""

    config: CreateExtracellularRecordingArraySingleConfig

    _single_task_config_type: ClassVar[TaskConfigType] = None  # ty:ignore[invalid-assignment]
    _single_task_activity_type: ClassVar[TaskActivityType] = None  # ty:ignore[invalid-assignment]

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

    def execute(
        self,
        *,
        db_client: Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,
        execution_activity_id: str | None = None,
    ) -> str | None:  # Returns the ID of the extracted circuit
        """Run the task."""
        _ = CreateExtracellularRecordingArrayTask._get_execution_activity(
            db_client=db_client, execution_activity_id=execution_activity_id
        )

        self._circuit, self._circuit_entity = db_sdk.resolve_circuit(
            self.config.initialize.circuit,  # ty:ignore[invalid-argument-type]
            db_client=db_client,
            entity_cache=entity_cache,
            cache_root=self.config.scan_output_root,
            temp_dir=self._create_temp_dir(),
        )

        test_locations = [[0.0, 0.0, 0.0], [50.0, 50.0, 50.0]]  # multiple x, y, z locations to test

        # Use BlueRecording to generate a weights file for the circuit and test locations
        # Using the value of self.config.initialize.calculation_method
        import numpy as np  # noqa: PLC0415
        from bluerecording import compute_weights  # noqa: PLC0415 # ty:ignore[unresolved-import]
        from bluerecording.weights import (  # noqa: PLC0415 # ty:ignore[unresolved-import]
            Electrode,
            ElectrodeType,
            save_weights,
        )

        electrodes = {
            f"electrode_{i}": Electrode(
                position=np.array(loc, dtype=float),
                type=ElectrodeType.POINT_SOURCE,
            )
            for i, loc in enumerate(test_locations)
        }

        circuit_config_path = Path(self._circuit.path)
        weights, positions_df, cols, neurite_types, population_name = compute_weights(
            path_to_config=circuit_config_path,
            electrodes=electrodes,
            replace_axons=True,
        )
        L.info("weights shape: %s", weights.shape if weights is not None else None)
        L.info("positions_df shape: %s", positions_df.shape)
        L.info("cols shape: %s", cols.shape)
        L.info("neurite_types shape: %s", neurite_types.shape)
        L.info("population_name: %s", population_name)

        weights_output_path = self.config.coordinate_output_root / "weights.h5"
        save_weights(
            weights=weights,
            cols=cols,
            population_name=population_name,
            outputfile=str(weights_output_path),
            electrodes=electrodes,
            neurite_types=neurite_types,
        )
        L.info("Weights saved to: %s", weights_output_path)
