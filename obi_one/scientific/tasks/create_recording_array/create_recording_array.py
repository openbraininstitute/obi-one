import logging
from enum import StrEnum
from typing import ClassVar, Literal

from entitysdk import Client, models
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.generate_simulation_configs import CircuitDiscriminator

L = logging.getLogger(__name__)
_RUN_VALIDATION = False


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    ELECTRODE_POSITIONS = "Electrode Location"


class CreateExtracellularRecordingArrayScanConfig(ScanConfig):
    """Description."""

    single_coord_class_name: ClassVar[str] = "CreateExtracellularRecordingArraySingleConfig"
    name: ClassVar[str] = "Create Extracellular Recording Array"
    description: ClassVar[str] = "Description."

    _campaign: models.CircuitExtractionCampaign = None

    json_schema_extra_additions: ClassVar[dict] = {
        "ui_enabled": False,
        "group_order": [BlockGroup.SETUP, BlockGroup.ELECTRODE_POSITIONS],
    }

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


class CreateExtracellularRecordingArraySingleConfig(
    CreateExtracellularRecordingArrayScanConfig, SingleConfigMixin
):
    """Description."""


class CreateExtracellularRecordingArrayTask(Task):
    """Task to create an extracellular recording array."""

    config: CreateExtracellularRecordingArraySingleConfig

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

    def execute(
        self,
        *,
        db_client: Client = None,
        entity_cache: bool = False,
        execution_activity_id: str | None = None,
    ) -> str | None:  # Returns the ID of the extracted circuit
        """Run the task."""
        self._resolve_circuit(db_client=self.db_client, entity_cache=entity_cache)

        test_locations = [[0.0, 0.0, 0.0], [50.0, 50.0, 50.0]]  # multiple x, y, z locations to test

        # Use BlueRecording to generate a weights file for the circuit and test locations
        # Using the three valid values of self.config.initialize.calculation_method
        self.config.initialize.calculation_method

        # Add the block of code for sonata simulation config as a comment
