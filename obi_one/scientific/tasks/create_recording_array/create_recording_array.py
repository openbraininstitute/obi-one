import json
import logging
import tempfile
import typing
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal

import bluepysnap as snap
import libsonata
import matplotlib.pyplot as plt
import numpy as np
from entitysdk import Client
from entitysdk.models import Entity, SimulatableExtracellularRecordingArray
from entitysdk.types import AssetLabel, ContentType, ElectrodeType
from pydantic import Field, PrivateAttr

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.db_sdk import db_sdk
from obi_one.scientific.library.extracellular_locations import (
    extracellular_locations_block_dictionary_summary,
    plot_extracellular_arrays,
)
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig
from obi_one.scientific.library.simulation.neuron.process import compile_mechanisms
from obi_one.scientific.tasks.create_recording_array.process import (
    run_bluerecording_write_weights,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitDiscriminator,
)
from obi_one.scientific.unions_and_references.extracellular_locations import (
    ExtracellularLocationsReference,
    ExtracellularLocationsUnion,
)
from obi_one.types import SimulationBackend

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    ELECTRODE_POSITIONS = "Electrode Positions"


class CreateExtracellularRecordingArrayScanConfig(InfoScanConfig):
    """Description."""

    name: ClassVar[str] = "Create Extracellular Recording Array"
    description: ClassVar[str] = "Description."

    json_schema_extra_additions: ClassVar[dict] = {
        "ui_enabled": True,
        "group_order": [BlockGroup.SETUP, BlockGroup.ELECTRODE_POSITIONS],
    }

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


def _write_electrode_json(
    electrode_locations: dict,
    calculation_method: str,
    output_path: Path,
) -> Path:  # pragma: no cover
    """Write electrode positions to a JSON file for the bluerecording CLI.

    Builds global positions from each block's ``get_global_electrode_xyz_locations()``
    and writes them using ``Electrode.to_json`` from bluerecording.

    Args:
        electrode_locations: Dict of electrode location blocks (name -> block).
        calculation_method: One of "PointSource", "LineSource", "ObjectiveCSD".
        output_path: Path to write the JSON file.

    Returns:
        The output path.
    """
    from bluerecording.electrodes import (  # ruff: ignore[import-outside-top-level] # ty:ignore[unresolved-import]
        Electrode,
        ElectrodeType,
    )

    electrodes = [
        Electrode(
            name=f"{block_name}_electrode_{i}",
            position=np.array([x, y, z], dtype=float),
            type=ElectrodeType(calculation_method),
        )
        for block_name, block in electrode_locations.items()
        for i, (x, y, z) in enumerate(block.get_global_electrode_xyz_locations())
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    Electrode.to_json(electrodes, str(output_path))

    L.info("Wrote %d electrodes to %s", len(electrodes), output_path)
    return output_path


def _plot_electrode_array(
    sonata_circuit: snap.Circuit,
    electrode_locations: dict[str, ExtracellularLocationsUnion],
    image_path: Path,
) -> None:
    """Plot the configured electrode array relative to the circuit's somas and save the image."""
    figure = plot_extracellular_arrays(sonata_circuit, electrode_locations)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(image_path, dpi=150, bbox_inches="tight")
    plt.close(figure)
    L.info("Saved electrode-array plot to: %s", image_path)


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

        image_path = self.config.coordinate_output_root / "electrode_array.png"
        _plot_electrode_array(
            self._circuit.sonata_circuit, self.config.electrode_locations, image_path
        )

        circuit_config_path = Path(self._circuit.path)
        circuit_config = libsonata.CircuitConfig.from_file(circuit_config_path)
        mechanisms_dirs = {
            Path(d)
            for pop in circuit_config.node_populations
            if (d := circuit_config.node_population_properties(pop).mechanisms_dir)
        }

        if mechanisms_dirs or (circuit_config_path.parent / "mod").exists():
            if (circuit_config_path.parent / "mod").exists():
                mechanisms_dirs = [circuit_config_path.parent / "mod"]

            mods_dir = self.config.coordinate_output_root / "compiled_mods"
            mods_dir.mkdir(exist_ok=True, parents=True)
            nrnmech_lib_path = compile_mechanisms(
                output_dir=mods_dir,
                mechanisms_dirs=list(mechanisms_dirs),
                simulation_backend=SimulationBackend.neurodamus,
            ).libnrnmech_path
        else:
            # fallback to neocortex if no mod file locations specified
            nrnmech_lib_path = Path("/opt/obi/neocortex/x86_64/libnrnmech.so")

        electrode_json_path = _write_electrode_json(
            self.config.electrode_locations,
            self.config.initialize.calculation_method,
            self.config.coordinate_output_root / "electrodes.json",
        )
        weights_output_path = self.config.coordinate_output_root / "weights.h5"
        run_bluerecording_write_weights(
            circuit_config_path,
            electrode_json_path,
            weights_output_path,
            nrnmech_lib_path=nrnmech_lib_path.absolute(),
        )
        L.info("Weights saved to: %s", weights_output_path)

        entity = SimulatableExtracellularRecordingArray(
            name=f"Extracellular Recording Array for {self._circuit.name}",
            description="Temp description.",
            electrode_type=ElectrodeType.custom,
            authorized_public=False,
            circuit_id=self._circuit_entity.id,  # ty:ignore[unresolved-attribute]
        )
        entity = db_client.register_entity(entity)

        # Upload the electrode-array plot as the entity's electrode_array_image asset.
        db_client.upload_file(
            entity_id=entity.id,
            entity_type=SimulatableExtracellularRecordingArray,
            file_path=image_path,
            file_content_type=ContentType.image_png,
            asset_label=AssetLabel.electrode_array_image,
        )
        db_client.upload_content(
            entity_id=entity.id,
            entity_type=SimulatableExtracellularRecordingArray,
            file_content=json.dumps(
                extracellular_locations_block_dictionary_summary(self.config.electrode_locations),
                indent=2,
            ).encode(),
            file_name="electrode_locations.json",
            file_content_type=ContentType.application_json,
            asset_label=AssetLabel.electrode_locations,
        )

        L.info("Uploaded electrode locations to recording array %s.", entity.id)

        db_client.upload_file(
            entity_id=entity.id,
            entity_type=SimulatableExtracellularRecordingArray,
            file_path=weights_output_path,
            file_content_type=ContentType.application_x_hdf5,
            asset_label=AssetLabel.electrode_array_weight_matrix,
        )

        CreateExtracellularRecordingArrayTask._update_execution_activity(
            db_client=db_client,
            execution_activity=execution_activity,
            generated=[str(entity.id)],
        )
