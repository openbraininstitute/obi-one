import abc
import logging
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar, Literal

import entitysdk
from pydantic import Field, NonNegativeFloat, PositiveFloat, PrivateAttr

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.core.units import Units
from obi_one.scientific.from_id.circuit_from_id import (
    CircuitFromID,
    MEModelWithSynapsesCircuitFromID,
)
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.constants import (
    _COORDINATE_CONFIG_FILENAME,
    _DEFAULT_SIMULATION_LENGTH_MILLISECONDS,
    _MAX_SIMULATION_LENGTH_MILLISECONDS,
    _MIN_SIMULATION_LENGTH_MILLISECONDS,
    _SCAN_CONFIG_FILENAME,
    _SIMULATION_TIMESTEP_MILLISECONDS,
)
from obi_one.scientific.library.entity_property_types import (
    MappedPropertiesGroup,
)
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig
from obi_one.scientific.library.ion_channel_model_circuit import CircuitFromIonChannelModels
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
)
from obi_one.scientific.unions.unions_recordings import (
    RecordingReference,
    RecordingUnion,
)
from obi_one.scientific.unions.unions_timestamps import (
    TimestampsReference,
    TimestampsUnion,
)

L = logging.getLogger(__name__)


DEFAULT_NODE_SET_NAME = "Default: All Biophysical Neurons"
DEFAULT_TIMESTAMPS_NAME = "Default: Simulation Start (0 ms)"
DEFAULT_DISTRIBUTION_NAME = "Default: Exp, scale 50 ms, 20 Hz"


class BlockGroup(StrEnum):
    """Authentication and authorization errors."""

    SETUP_BLOCK_GROUP = "Setup"
    STIMULI_RECORDINGS_BLOCK_GROUP = "Stimuli & Recordings"
    CIRCUIT_COMPONENTS_BLOCK_GROUP = "Circuit Components"
    CIRCUIT_MANIPULATIONS_GROUP = "Manipulations"
    EVENTS_GROUP = "Events"


SONATA_VERSION = 2.4


class SimulationScanConfig(InfoScanConfig, abc.ABC):
    """Abstract base class for simulation scan configurations."""

    single_coord_class_name: ClassVar[str]
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    _campaign: entitysdk.models.SimulationCampaign = None  # ty:ignore[possibly-missing-submodule]

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP_BLOCK_GROUP,
            BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            BlockGroup.EVENTS_GROUP,
        ],
        SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS: {
            NeuronSetReference.__name__: DEFAULT_NODE_SET_NAME,
            TimestampsReference.__name__: DEFAULT_TIMESTAMPS_NAME,
        },
        SchemaKey.PROPERTY_ENDPOINTS: {
            MappedPropertiesGroup.CIRCUIT: "/mapped-circuit-properties/{circuit_id}",
        },
    }

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
    recordings: dict[str, RecordingUnion] = Field(
        default_factory=dict,
        description="Recordings for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPE: RecordingReference.__name__,
            SchemaKey.SINGULAR_NAME: "Recording",
            SchemaKey.GROUP: BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    class Initialize(Block):
        circuit: None
        simulation_length: (
            Annotated[
                NonNegativeFloat,
                Field(
                    ge=_MIN_SIMULATION_LENGTH_MILLISECONDS, le=_MAX_SIMULATION_LENGTH_MILLISECONDS
                ),
            ]
            | Annotated[
                list[
                    Annotated[
                        NonNegativeFloat,
                        Field(
                            ge=_MIN_SIMULATION_LENGTH_MILLISECONDS,
                            le=_MAX_SIMULATION_LENGTH_MILLISECONDS,
                        ),
                    ]
                ],
                Field(min_length=1),
            ]
        ) = Field(
            default=_DEFAULT_SIMULATION_LENGTH_MILLISECONDS,
            title="Duration",
            description="Simulation length in milliseconds (ms).",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
                SchemaKey.UNITS: Units.MILLISECONDS,
            },
        )
        extracellular_calcium_concentration: NonNegativeFloat | list[NonNegativeFloat] = Field(
            default=1.10,
            title="Extracellular Calcium Concentration",
            description=(
                "Extracellular calcium concentration around the synapse in millimoles (mM). "
                "Increasing this value increases the probability of synaptic vesicle release, "
                "which in turn increases the level of network activity. In vivo values are "
                "estimated to be ~0.9-1.2mM, whilst in vitro values are on the order of 2mM."
            ),
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
                SchemaKey.UNITS: Units.MILLIMOLAR,
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

        _spike_location: Literal["AIS", "soma"] | list[Literal["AIS", "soma"]] = PrivateAttr(
            default="soma"
        )
        _timestep: list[PositiveFloat] | PositiveFloat = PrivateAttr(
            default=_SIMULATION_TIMESTEP_MILLISECONDS
        )

        @property
        def timestep(self) -> PositiveFloat | list[PositiveFloat]:
            return self._timestep

        @property
        def spike_location(self) -> Literal["AIS", "soma"] | list[Literal["AIS", "soma"]]:
            return self._spike_location

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
            file_path=output_root / _SCAN_CONFIG_FILENAME,
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
            file_path=Path(self.coordinate_output_root, _COORDINATE_CONFIG_FILENAME),
            file_content_type="application/json",  # ty:ignore[invalid-argument-type]
            asset_label="simulation_generation_config",  # ty:ignore[invalid-argument-type]
        )
