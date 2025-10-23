import abc
import logging
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar, Literal

import entitysdk
from pydantic import (
    Field,
    NonNegativeFloat,
    PositiveFloat,
    PrivateAttr,
)

from obi_one.core.block import Block
from obi_one.core.constants import (
    _DEFAULT_SIMULATION_LENGTH_MILLISECONDS,
    _MAX_SIMULATION_LENGTH_MILLISECONDS,
    _MIN_SIMULATION_LENGTH_MILLISECONDS,
)
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.memodel_circuit import MEModelCircuit
from obi_one.scientific.unions.unions_manipulations import (
    SynapticManipulationsReference,
    SynapticManipulationsUnion,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    SimulationNeuronSetUnion,
)
from obi_one.scientific.unions.unions_recordings import RecordingReference, RecordingUnion
from obi_one.scientific.unions.unions_stimuli import (
    MEModelStimulusUnion,
    StimulusReference,
    StimulusUnion,
)
from obi_one.scientific.unions.unions_timestamps import TimestampsReference, TimestampsUnion

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Authentication and authorization errors."""

    SETUP_BLOCK_GROUP = "Setup"
    STIMULI_RECORDINGS_BLOCK_GROUP = "Stimuli & Recordings"
    CIRUIT_COMPONENTS_BLOCK_GROUP = "Circuit Components"
    EVENTS_GROUP = "Events"
    CIRCUIT_MANIPULATIONS_GROUP = "Circuit Manipulations"


CircuitDiscriminator = Annotated[Circuit | CircuitFromID, Field(discriminator="type")]
MEModelDiscriminator = Annotated[MEModelCircuit | MEModelFromID, Field(discriminator="type")]

TARGET_SIMULATOR = "NEURON"
SONATA_VERSION = 2.4


class SimulationScanConfig(ScanConfig, abc.ABC):
    """Abstract base class for simulation scan configurations."""

    single_coord_class_name: ClassVar[str]
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    _campaign: entitysdk.models.SimulationCampaign = None

    class Config:
        json_schema_extra: ClassVar[dict] = {
            "block_block_group_order": [
                BlockGroup.SETUP_BLOCK_GROUP,
                BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
                BlockGroup.CIRUIT_COMPONENTS_BLOCK_GROUP,
                BlockGroup.EVENTS_GROUP,
                BlockGroup.CIRCUIT_MANIPULATIONS_GROUP,
            ]
        }

    timestamps: dict[str, TimestampsUnion] = Field(
        default_factory=dict,
        title="Timestamps",
        reference_type=TimestampsReference.__name__,
        description="Timestamps for the simulation.",
        singular_name="Timestamps",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=0,
    )
    recordings: dict[str, RecordingUnion] = Field(
        default_factory=dict,
        reference_type=RecordingReference.__name__,
        description="Recordings for the simulation.",
        singular_name="Recording",
        group=BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
        group_order=1,
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
            units="ms",
        )
        extracellular_calcium_concentration: list[NonNegativeFloat] | NonNegativeFloat = Field(
            default=1.1,
            title="Extracellular Calcium Concentration",
            description=(
                "Extracellular calcium concentration around the synapse in millimoles (mM). "
                "Increasing this value increases the probability of synaptic vesicle release, "
                "which in turn increases the level of network activity. In vivo values are "
                "estimated to be ~0.9-1.2mM, whilst in vitro values are on the order of 2mM."
            ),
            units="mM",
        )
        v_init: list[float] | float = Field(
            default=-80.0,
            title="Initial Voltage",
            description="Initial membrane potential in millivolts (mV).",
            units="mV",
        )
        random_seed: list[int] | int = Field(
            default=1, description="Random seed for the simulation."
        )

        _spike_location: Literal["AIS", "soma"] | list[Literal["AIS", "soma"]] = PrivateAttr(
            default="soma"
        )
        _timestep: list[PositiveFloat] | PositiveFloat = PrivateAttr(
            default=0.025
        )  # Simulation time step in ms

        @property
        def timestep(self) -> PositiveFloat | list[PositiveFloat]:
            return self._timestep

        @property
        def spike_location(self) -> Literal["AIS", "soma"] | list[Literal["AIS", "soma"]]:
            return self._spike_location

    info: Info = Field(
        title="Info",
        description="Information about the simulation campaign.",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=0,
    )

    def create_campaign_entity_with_config(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: entitysdk.client.Client = None,
    ) -> entitysdk.models.SimulationCampaign:
        """Initializes the simulation campaign in the database."""
        L.info("1. Initializing simulation campaign in the database...")
        if multiple_value_parameters_dictionary is None:
            multiple_value_parameters_dictionary = {}

        L.info("-- Register SimulationCampaign Entity")
        if isinstance(self.initialize.circuit, (CircuitFromID, MEModelFromID)):
            entity_id = self.initialize.circuit.id_str
        elif isinstance(self.initialize.circuit, list):
            if len(self.initialize.circuit) != 1:
                msg = "Only single circuit/MEModel currently supported for \
                    simulation campaign database persistence."
                raise OBIONEError(msg)
            entity_id = self.initialize.circuit[0].id_str

        self._campaign = db_client.register_entity(
            entitysdk.models.SimulationCampaign(
                name=self.info.campaign_name,
                description=self.info.campaign_description,
                entity_id=entity_id,
                scan_parameters=multiple_value_parameters_dictionary,
            )
        )

        L.info("-- Upload campaign_generation_config")
        _ = db_client.upload_file(
            entity_id=self._campaign.id,
            entity_type=entitysdk.models.SimulationCampaign,
            file_path=output_root / "run_scan_config.json",
            file_content_type="application/json",
            asset_label="campaign_generation_config",
        )

        return self._campaign

    def create_campaign_generation_entity(
        self, simulations: list[entitysdk.models.Simulation], db_client: entitysdk.client.Client
    ) -> None:
        L.info("3. Saving completed simulation campaign generation")

        L.info("-- Register SimulationGeneration Entity")
        db_client.register_entity(
            entitysdk.models.SimulationGeneration(
                start_time=datetime.now(UTC),
                used=[self._campaign],
                generated=simulations,
            )
        )


class MEModelSimulationScanConfig(SimulationScanConfig):
    """MEModelSimulationScanConfig."""

    single_coord_class_name: ClassVar[str] = "MEModelSimulationSingleConfig"
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    class Initialize(SimulationScanConfig.Initialize):
        circuit: MEModelDiscriminator | list[MEModelDiscriminator] = Field(
            title="ME Model", description="ME Model to simulate."
        )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the simulation.",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=1,
    )

    stimuli: dict[str, MEModelStimulusUnion] = Field(
        default_factory=dict,
        title="Stimuli",
        reference_type=StimulusReference.__name__,
        description="Stimuli for the simulation.",
        singular_name="Stimulus",
        group=BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
        group_order=0,
    )


class CircuitSimulationScanConfig(SimulationScanConfig):
    """CircuitSimulationScanConfig."""

    single_coord_class_name: ClassVar[str] = "CircuitSimulationSingleConfig"
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    neuron_sets: dict[str, SimulationNeuronSetUnion] = Field(
        default_factory=dict,
        reference_type=NeuronSetReference.__name__,
        description="Neuron sets for the simulation.",
        singular_name="Neuron Set",
        group=BlockGroup.CIRUIT_COMPONENTS_BLOCK_GROUP,
        group_order=0,
    )
    synaptic_manipulations: dict[str, SynapticManipulationsUnion] = Field(
        default_factory=dict,
        reference_type=SynapticManipulationsReference.__name__,
        description="Synaptic manipulations for the simulation.",
        singular_name="Synaptic Manipulation",
        group=BlockGroup.CIRUIT_COMPONENTS_BLOCK_GROUP,
        group_order=1,
    )

    class Initialize(SimulationScanConfig.Initialize):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
            title="Circuit", description="Circuit to simulate."
        )
        node_set: Annotated[
            NeuronSetReference, Field(title="Neuron Set", description="Neuron set to simulate.")
        ]

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the simulation.",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=1,
    )

    stimuli: dict[str, StimulusUnion] = Field(
        default_factory=dict,
        title="Stimuli",
        reference_type=StimulusReference.__name__,
        description="Stimuli for the simulation.",
        singular_name="Stimulus",
        group=BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
        group_order=0,
    )


class SimulationSingleConfigMixin(abc.ABC):
    """Mixin for CircuitSimulationSingleConfig and MEModelSimulationSingleConfig."""

    _single_entity: entitysdk.models.Simulation

    @property
    def single_entity(self) -> entitysdk.models.Simulation:
        return self._single_entity

    def create_single_entity_with_config(
        self, campaign: entitysdk.models.SimulationCampaign, db_client: entitysdk.client.Client
    ) -> entitysdk.models.Simulation:
        """Saves the simulation to the database."""
        L.info(f"2.{self.idx} Saving simulation {self.idx} to database...")

        if not isinstance(self.initialize.circuit, (CircuitFromID, MEModelFromID)):
            msg = (
                "Simulation can only be saved to entitycore if circuit is CircuitFromID "
                "or MEModelFromID"
            )
            raise OBIONEError(msg)

        L.info("-- Register Simulation Entity")
        self._single_entity = db_client.register_entity(
            entitysdk.models.Simulation(
                name=f"Simulation {self.idx}",
                description=f"Simulation {self.idx}",
                scan_parameters=self.single_coordinate_scan_params.dictionary_representaiton(),
                entity_id=self.initialize.circuit.id_str,
                simulation_campaign_id=campaign.id,
            )
        )

        L.info("-- Upload simulation_generation_config")
        _ = db_client.upload_file(
            entity_id=self.single_entity.id,
            entity_type=entitysdk.models.Simulation,
            file_path=Path(self.coordinate_output_root, "run_coordinate_instance.json"),
            file_content_type="application/json",
            asset_label="simulation_generation_config",
        )


class CircuitSimulationSingleConfig(
    CircuitSimulationScanConfig, SingleConfigMixin, SimulationSingleConfigMixin
):
    """Only allows single values."""


class MEModelSimulationSingleConfig(
    MEModelSimulationScanConfig, SingleConfigMixin, SimulationSingleConfigMixin
):
    """Only allows single values."""
