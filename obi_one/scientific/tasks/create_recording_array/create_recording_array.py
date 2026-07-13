import json
import logging
import tempfile
import typing
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal

from entitysdk import Client
from entitysdk.models import Entity, SimulatableExtracellularRecordingArray
from entitysdk.types import AssetLabel, ContentType, ElectrodeType, TaskActivityType, TaskConfigType
from pydantic import Field, PrivateAttr

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitDiscriminator,
)
from obi_one.scientific.unions.unions_extracellular_locations import (
    ExtracellularLocationsReference,
    ExtracellularLocationsUnion,
)
from obi_one.utils import db_sdk

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    ELECTRODE_POSITIONS = "Electrode Positions"


class CreateExtracellularRecordingArrayScanConfig(InfoScanConfig):
    """Description."""

    single_coord_class_name: ClassVar[str] = "CreateExtracellularRecordingArraySingleConfig"
    name: ClassVar[str] = "Create Extracellular Recording Array"
    description: ClassVar[str] = "Description."

    json_schema_extra_additions: ClassVar[dict] = {
        "ui_enabled": True,
        "group_order": [BlockGroup.SETUP, BlockGroup.ELECTRODE_POSITIONS],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = (
        TaskConfigType.extracellular_recording_weights_calculation__campaign
    )
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.extracellular_recording_weights_calculation__config_generation
    )

    @typing.override
    def input_entities(self, db_client: Client) -> list[Entity]:
        return [self.initialize.circuit.entity(db_client=db_client)]  # ty:ignore[unresolved-attribute]

    class Initialize(Block):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
            title="Circuit",
            description="Parent circuit to extract a sub-circuit from.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER,
            },
        )
        calculation_method: Literal["PointSource", "LineSource", "ObjectiveCSD"] = Field(
            title="Calculation Method",
            description=(
                "Method to calculate extracellular signals from the"
                " specified neuron set and electrode locations."
            ),
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION_ENHANCED,
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
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the extracellular recording array creation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    electrode_locations: dict[str, ExtracellularLocationsUnion] = Field(
        default_factory=dict,
        title="Electrode Locations",
        description=(
            "Parameters defining the locations of the electrodes for the"
            " extracellular recording array. Each entry contributes its electrodes to the array."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [ExtracellularLocationsReference.__name__],
            SchemaKey.SINGULAR_NAME: "Electrode Locations",
            SchemaKey.GROUP: BlockGroup.ELECTRODE_POSITIONS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class CreateExtracellularRecordingArraySingleConfig(
    CreateExtracellularRecordingArrayScanConfig, SingleConfigMixin
):
    """Description."""

    _single_task_config_type: ClassVar[TaskConfigType] = (
        TaskConfigType.extracellular_recording_weights_calculation__config
    )
    _single_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.extracellular_recording_weights_calculation__execution
    )


class CreateExtracellularRecordingArrayTask(Task):
    """Task to create an extracellular recording array."""

    config: CreateExtracellularRecordingArraySingleConfig

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

        execution_activity = CreateExtracellularRecordingArrayTask._get_execution_activity(
            db_client=db_client, execution_activity_id=execution_activity_id
        )

        self._circuit, self._circuit_entity = db_sdk.resolve_circuit(
            self.config.initialize.circuit,  # ty:ignore[invalid-argument-type]
            db_client=db_client,
            entity_cache=entity_cache,
            cache_root=self.config.scan_output_root,
            temp_dir=self._create_temp_dir(),
        )

        # Plot the configured electrode array relative to the circuit's somas and save the image.
        import matplotlib.pyplot as plt  # noqa: PLC0415

        from obi_one.scientific.library.extracellular_locations import (  # noqa: PLC0415
            extracellular_locations_block_dictionary_summary,
            plot_extracellular_arrays,
        )

        figure = plot_extracellular_arrays(
            self._circuit.sonata_circuit, self.config.electrode_locations
        )
        image_path = self.config.coordinate_output_root / "electrode_array.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(image_path, dpi=150, bbox_inches="tight")
        plt.close(figure)
        L.info("Saved electrode-array plot to: %s", image_path)

        # Use BlueRecording to generate a weights file for the circuit and test locations
        # Using the value of self.config.initialize.calculation_method
        import numpy as np  # noqa: PLC0415
        from bluerecording import compute_weights  # noqa: PLC0415 # ty:ignore[unresolved-import]
        from bluerecording.weights import (  # noqa: PLC0415 # ty:ignore[unresolved-import]
            Electrode,
            ElectrodeType as BlueRecordingElectrodeType,
            save_weights,
        )

        # Build the electrode array from every electrode-locations block in the dictionary, using
        # each block's global coordinates (origin and direction applied). Electrode names are
        # prefixed with the block name so electrodes from different blocks stay distinct.
        electrodes = [
            Electrode(
                name=f"{block_name}_electrode_{i}",
                position=np.array(loc, dtype=float),
                type=BlueRecordingElectrodeType.POINT_SOURCE,
            )
            for block_name, locations in self.config.electrode_locations.items()
            for i, loc in enumerate(locations.get_global_electrode_xyz_locations())
        ]

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

        entity = SimulatableExtracellularRecordingArray(
            name=f"Extracellular Recording Array for {self._circuit.name}",
            description="Temp description.",
            electrode_type=ElectrodeType.custom,
            authorized_public=False,
            circuit_id=self._circuit_entity.id,  # ty:ignore[invalid-argument-type, unresolved-attribute]
        )
        entity = db_client.register_entity(entity)

        # Upload the electrode-array plot as the entity's electrode_array_image asset.
        db_client.upload_file(
            entity_id=entity.id,  # ty:ignore[invalid-argument-type]
            entity_type=SimulatableExtracellularRecordingArray,
            file_path=image_path,
            file_content_type=ContentType.image_png,
            asset_label=AssetLabel.electrode_array_image,
        )

        # Write the electrode locations + each block's properties to a JSON asset.
        locations_path = self.config.coordinate_output_root / "electrode_locations.json"
        with locations_path.open("w") as locations_file:
            json.dump(
                extracellular_locations_block_dictionary_summary(self.config.electrode_locations),
                locations_file,
                indent=2,
            )
        db_client.upload_file(
            entity_id=entity.id,  # ty:ignore[invalid-argument-type]
            entity_type=SimulatableExtracellularRecordingArray,
            file_path=locations_path,
            file_content_type=ContentType.application_json,
            asset_label=AssetLabel.electrode_locations,
        )
        L.info("Uploaded electrode locations to recording array %s.", entity.id)

        _ = db_client.upload_file(
            entity_id=entity.id,  # ty:ignore[invalid-argument-type]
            entity_type=SimulatableExtracellularRecordingArray,
            file_path=weights_output_path,
            file_content_type=ContentType.application_x_hdf5,
            asset_label=AssetLabel.electrode_array_weight_matrix,
        )

        # Update execution activity (if any)
        CreateExtracellularRecordingArrayTask._update_execution_activity(
            db_client=db_client,
            execution_activity=execution_activity,
            generated=[str(entity.id)],
        )
