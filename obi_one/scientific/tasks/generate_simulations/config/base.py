import abc
import logging
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar

import entitysdk
from libsonata import SimulatorType
from pydantic import Field, NonNegativeFloat, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.serialization_constants import (
    COORDINATE_CONFIG_FILENAME,
    SCAN_CONFIG_FILENAME,
)
from obi_one.core.single import SingleConfigMixin
from obi_one.core.units import Units
from obi_one.scientific.from_id.circuit_from_id import (
    CircuitFromID,
    MEModelWithSynapsesCircuitFromID,
)
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.constants import (
    DEFAULT_SIMULATION_LENGTH_MILLISECONDS,
    MAX_SIMULATION_LENGTH_MILLISECONDS,
    MIN_SIMULATION_LENGTH_MILLISECONDS,
)
from obi_one.scientific.library.entity_property_types import (
    MappedPropertiesGroup,
)
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig
from obi_one.scientific.library.ion_channel_model_circuit import CircuitFromIonChannelModels
from obi_one.scientific.unions.unions_timestamps import (
    TimestampsReference,
    TimestampsUnion,
)

SONATA_VERSION = 2.4

L = logging.getLogger(__name__)


DEFAULT_NODE_SET_NAME = "Default: All Biophysical Neurons"
DEFAULT_TIMESTAMPS_NAME = "Default: Simulation Start (0 ms)"
DEFAULT_DISTRIBUTION_NAME = "Default: Exponential, scale 50 ms"


class BlockGroup(StrEnum):
    """Enumeration of block groups for simulation configuration."""

    SETUP_BLOCK_GROUP = "Setup"
    STIMULI_RECORDINGS_BLOCK_GROUP = "Stimuli & Recordings"
    DISTRIBUTIONS_BLOCK_GROUP = "Distributions"
    CIRCUIT_COMPONENTS_BLOCK_GROUP = "Circuit Components"
    CIRCUIT_MANIPULATIONS_GROUP = "Manipulations"
    EVENTS_GROUP = "Events"


class BaseSimulationScanConfig(InfoScanConfig, abc.ABC):
    """Abstract base class for simulation scan configurations."""

    single_coord_class_name: ClassVar[str]
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    _campaign: entitysdk.models.SimulationCampaign = None  # ty:ignore[possibly-missing-submodule]
    _sonata_version: ClassVar[float] = SONATA_VERSION
    _target_simulator: ClassVar[SimulatorType] = None
    _timestep: ClassVar[None] = None

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.PROPERTY_ENDPOINTS: {
            MappedPropertiesGroup.CIRCUIT: "/mapped-circuit-properties/{circuit_id}",
        },
    }

    class Initialize(Block):
        simulation_length: (
            Annotated[
                NonNegativeFloat,
                Field(ge=MIN_SIMULATION_LENGTH_MILLISECONDS, le=MAX_SIMULATION_LENGTH_MILLISECONDS),
            ]
            | Annotated[
                list[
                    Annotated[
                        NonNegativeFloat,
                        Field(
                            ge=MIN_SIMULATION_LENGTH_MILLISECONDS,
                            le=MAX_SIMULATION_LENGTH_MILLISECONDS,
                        ),
                    ]
                ],
                Field(min_length=1),
            ]
        ) = Field(
            default=DEFAULT_SIMULATION_LENGTH_MILLISECONDS,
            title="Duration",
            description="Simulation length in milliseconds (ms).",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
                SchemaKey.UNITS: Units.MILLISECONDS,
            },
        )

        v_init: float | list[float] = Field(
            default=-80.0,
            title="Initial Voltage",
            description="Initial membrane potential in millivolts (mV).",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
                SchemaKey.UNITS: Units.MILLIVOLTS,
            },
        )
        random_seed: int | list[int] = Field(
            default=1,
            title="Random Seed",
            description="Random seed for the simulation.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
            },
        )

    initialize: Initialize

    timestamps: dict[str, TimestampsUnion] = Field(
        default_factory=dict,
        title="Timestamps",
        description="Timestamps for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPE: TimestampsReference.__name__,
            SchemaKey.SINGULAR_NAME: "Timestamps",
            SchemaKey.GROUP: BlockGroup.EVENTS_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    def base_sonata_config(self, sonata_config: dict | None = None) -> dict:
        """Returns the base SONATA configuration for the simulation campaign."""
        if sonata_config is None:
            sonata_config = {}

        sonata_config["version"] = self._sonata_version
        sonata_config["target_simulator"] = self._target_simulator.name

        sonata_config["run"] = {}
        sonata_config["run"]["dt"] = self.timestep
        sonata_config["run"]["random_seed"] = self.initialize.random_seed
        sonata_config["run"]["tstop"] = self.initialize.simulation_length

        sonata_config["conditions"] = {}
        sonata_config["conditions"]["v_init"] = self.initialize.v_init

        sonata_config["output"] = {}
        sonata_config["output"]["output_dir"] = "output"
        sonata_config["output"]["spikes_file"] = "spikes.h5"

        return sonata_config

    @property
    def target_simulator(self) -> SimulatorType:
        """Returns the target simulator for the simulation campaign."""
        if self._target_simulator is None:
            msg = "Target simulator not specified for simulation campaign."
            raise NotImplementedError(msg)
        return self._target_simulator

    @property
    def timestep(self) -> PositiveFloat:
        """Returns the simulation timestep."""
        if self._timestep is None:
            msg = "Timestep not specified for simulation campaign."
            raise NotImplementedError(msg)
        return self._timestep

    def entity_id_for_campaign_entity_generation(self) -> str:
        """Determines the entity ID for the simulation campaign based on the circuit."""
        if isinstance(self.initialize.circuit, list):  # ty:ignore[unresolved-attribute]
            if len(self.initialize.circuit) != 1:  # ty:ignore[unresolved-attribute]
                msg = "Only single circuit/MEModel currently supported for \
                    simulation campaign database persistence."
                raise OBIONEError(msg)
            return self.initialize.circuit[0].id_str  # ty:ignore[unresolved-attribute]
        if self.initialize.circuit is None:  # ty:ignore[unresolved-attribute]
            msg = "Circuit must be specified to determine entity ID for simulation campaign."
            raise OBIONEError(msg)
        try:
            return self.initialize.circuit.id_str  # ty:ignore[unresolved-attribute]
        except AttributeError as err:
            msg = "self.initialize.circuit must have an id_str attribute."
            raise OBIONEError(msg) from err

    def create_campaign_entity_with_config(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
    ) -> entitysdk.models.SimulationCampaign:  # ty:ignore[possibly-missing-submodule]
        """Initializes the simulation campaign in the database."""
        L.info("1. Initializing simulation campaign in the database...")
        if multiple_value_parameters_dictionary is None:
            multiple_value_parameters_dictionary = {}

        L.info("-- Register SimulationCampaign Entity")

        self._campaign = db_client.register_entity(
            entitysdk.models.SimulationCampaign(  # ty:ignore[possibly-missing-submodule]
                name=self.info.campaign_name,
                description=self.info.campaign_description,
                entity_id=self.entity_id_for_campaign_entity_generation(),
                scan_parameters=multiple_value_parameters_dictionary,
            )
        )

        L.info("-- Upload campaign_generation_config")
        _ = db_client.upload_file(
            entity_id=self._campaign.id,
            entity_type=entitysdk.models.SimulationCampaign,  # ty:ignore[possibly-missing-submodule]
            file_path=output_root / SCAN_CONFIG_FILENAME,
            file_content_type="application/json",  # ty:ignore[invalid-argument-type]
            asset_label="campaign_generation_config",  # ty:ignore[invalid-argument-type]
        )

        return self._campaign

    def create_campaign_generation_entity(
        self,
        simulations: list[entitysdk.models.Simulation],  # ty:ignore[possibly-missing-submodule]
        db_client: entitysdk.client.Client,
    ) -> None:  # ty:ignore[invalid-method-override]
        L.info("3. Saving completed simulation campaign generation")

        L.info("-- Register SimulationGeneration Entity")
        db_client.register_entity(
            entitysdk.models.SimulationGeneration(  # ty:ignore[possibly-missing-submodule]
                start_time=datetime.now(UTC),
                used=[self._campaign],
                generated=simulations,
            )
        )


class SimulationSingleConfigMixin(SingleConfigMixin):
    """Mixin for CircuitSimulationSingleConfig and MEModelSimulationSingleConfig.

    Inherits from SingleConfigMixin and overrides create_single_entity_with_config
    to register a Simulation entity instead of a generic TaskConfig.
    """

    def create_single_entity_with_config(
        self,
        campaign: entitysdk.models.SimulationCampaign,  # ty:ignore[possibly-missing-submodule]
        db_client: entitysdk.client.Client,
    ) -> entitysdk.models.Simulation:  # ty:ignore[possibly-missing-submodule]
        """Saves the simulation to the database."""
        L.info(f"2.{self.idx} Saving simulation {self.idx} to database...")

        if hasattr(self.initialize, "circuit"):  # ty:ignore[unresolved-attribute]
            circuit = self.initialize.circuit  # ty:ignore[unresolved-attribute]
        elif hasattr(self, "circuit"):
            circuit = self.circuit

        if not isinstance(
            circuit,
            (
                CircuitFromID,
                MEModelFromID,
                MEModelWithSynapsesCircuitFromID,
                CircuitFromIonChannelModels,
            ),
        ):
            msg = (
                "Simulation can only be saved to entitycore if circuit is CircuitFromID "
                "or MEModelFromID"
            )
            raise OBIONEError(msg)

        L.info("-- Register Simulation Entity")
        self._single_entity = db_client.register_entity(
            entitysdk.models.Simulation(  # ty:ignore[possibly-missing-submodule]
                name=f"Simulation {self.idx}",
                description=f"Simulation {self.idx}",
                scan_parameters=self.single_coordinate_scan_params.dictionary_representation(),
                entity_id=self.entity_id_for_campaign_entity_generation(),  # ty:ignore[unresolved-attribute]
                simulation_campaign_id=campaign.id,
                number_neurons=-1,
            )
        )

        L.info("-- Upload simulation_generation_config")
        _ = db_client.upload_file(
            entity_id=self.single_entity.id,  # ty:ignore[invalid-argument-type]
            entity_type=entitysdk.models.Simulation,  # ty:ignore[possibly-missing-submodule]
            file_path=Path(self.coordinate_output_root, COORDINATE_CONFIG_FILENAME),
            file_content_type="application/json",  # ty:ignore[invalid-argument-type]
            asset_label="simulation_generation_config",  # ty:ignore[invalid-argument-type]
        )
