import logging
from typing import Annotated, ClassVar, Self

from pydantic import Field, NonNegativeFloat, PositiveFloat, PrivateAttr, model_validator

from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.library.constants import (
    _DEFAULT_SIMULATION_LENGTH_MILLISECONDS,
    _MAX_SIMULATION_LENGTH_MILLISECONDS,
    _MIN_SIMULATION_LENGTH_MILLISECONDS,
)
from obi_one.scientific.library.entity_property_types import (
    MappedPropertiesGroup,
)
from obi_one.scientific.library.ion_channel_model_circuit import CircuitFromIonChannelModels
from obi_one.scientific.tasks.generate_simulations.config.base import (
    DEFAULT_NODE_SET_NAME,
    DEFAULT_TIMESTAMPS_NAME,
    BlockGroup,
    SimulationScanConfig,
    SimulationSingleConfigMixin,
)
from obi_one.scientific.unions.unions_ion_channel_model import (
    IonChannelModelReference,
    IonChannelModelUnion,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
)
from obi_one.scientific.unions.unions_recordings import (
    IonChannelModelRecordingUnion,
    RecordingReference,
)
from obi_one.scientific.unions.unions_stimuli import (
    IonChannelModelStimulusUnion,
    StimulusReference,
)
from obi_one.scientific.unions.unions_timestamps import (
    TimestampsReference,
    TimestampsUnion,
)

L = logging.getLogger(__name__)


class IonChannelModelSimulationScanConfig(SimulationScanConfig):
    """Form for simulating ion channel model(s)."""

    single_coord_class_name: ClassVar[str] = "IonChannelModelSimulationSingleConfig"
    name: ClassVar[str] = "Ion Channel Model Simulation Campaign"
    description: ClassVar[str] = "Ion Channal Model SONATA simulation campaign"

    json_schema_extra_additions: ClassVar[dict] = {
        "ui_enabled": True,
        "group_order": [
            BlockGroup.SETUP_BLOCK_GROUP,
            BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            BlockGroup.EVENTS_GROUP,
        ],
        "default_block_reference_labels": {
            NeuronSetReference.__name__: DEFAULT_NODE_SET_NAME,
            TimestampsReference.__name__: DEFAULT_TIMESTAMPS_NAME,
        },
        "property_endpoints": {
            MappedPropertiesGroup.ION_CHANNEL_MODEL: "/mapped-ion-channel-properties",
        },
    }

    _all_block_reference_types: ClassVar[list[type[BlockReference]]] = [
        TimestampsReference,
        RecordingReference,
        IonChannelModelReference,
        StimulusReference,
    ]

    class Initialize(Block):
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
                "ui_element": "float_parameter_sweep",
                "units": "ms",
            },
        )

        temperature: NonNegativeFloat | list[NonNegativeFloat] = Field(
            title="Temperature (in °C)",
            description="Temperature of the simulation.",
            default=34.0,
            json_schema_extra={
                "ui_element": "float_parameter_sweep",
            },
        )

        v_init: float | list[float] = Field(
            default=-80.0,
            title="Initial Voltage",
            description="Initial membrane potential in millivolts (mV).",
            json_schema_extra={
                "ui_element": "float_parameter_sweep",
                "units": "mV",
            },
        )
        random_seed: int | list[int] = Field(
            default=1,
            title="Random Seed",
            description="Random seed for the simulation.",
            json_schema_extra={
                "ui_element": "int_parameter_sweep",
            },
        )
        _timestep: PositiveFloat | list[PositiveFloat] = PrivateAttr(
            default=0.025
        )  # Simulation time step in ms

        @property
        def timestep(self) -> PositiveFloat | list[PositiveFloat]:
            return self._timestep

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the simulation.",
        json_schema_extra={
            "ui_element": "block_single",
            "group": BlockGroup.SETUP_BLOCK_GROUP,
            "group_order": 2,
        },
    )

    info: Info = Field(
        title="Info",
        description="Information about the ion channel model simulation campaign.",
        json_schema_extra={
            "ui_element": "block_single",
            "group": BlockGroup.SETUP_BLOCK_GROUP,
            "group_order": 0,
        },
    )

    # contains models and their conductances
    ion_channel_models: dict[str, IonChannelModelUnion] = Field(
        default_factory=dict,
        title="Ion Channel Models",
        description="Ion channel models and their conductance / max permeability.",
        json_schema_extra={
            "ui_element": "block_dictionary",
            "group": BlockGroup.SETUP_BLOCK_GROUP,
            "group_order": 1,
            "singular_name": "Ion Channel Model",
            "reference_type": IonChannelModelReference.__name__,
        },
    )

    # have to define Union. Will probably be same as MEModel + SEClamp.
    # will have to wait for meeting with HPC team to confirm
    stimuli: dict[str, IonChannelModelStimulusUnion] = Field(
        default_factory=dict,
        title="Stimuli",
        description="Stimuli for the simulation.",
        json_schema_extra={
            "ui_element": "block_dictionary",
            "group": BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            "group_order": 0,
            "singular_name": "Stimulus",
            "reference_type": StimulusReference.__name__,
        },
    )
    # can we have recording union depending on what model we choose?
    # should allow user to choose any recording in {SUFFIX}.{RANGE variable} list
    # should also allow simple voltage recording
    # attention! For cadynamics, should use `cai`, not `{SUFFIX}.cai`.
    recordings: dict[str, IonChannelModelRecordingUnion] = Field(
        default_factory=dict,
        title="Recordings",
        description="Recordings for the simulation.",
        json_schema_extra={
            "ui_element": "block_dictionary",
            "group": BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            "group_order": 1,
            "singular_name": "Recording",
            "reference_type": RecordingReference.__name__,
        },
    )

    timestamps: dict[str, TimestampsUnion] = Field(
        default_factory=dict,
        title="Timestamps",
        description="Timestamps for the simulation.",
        json_schema_extra={
            "ui_element": "block_dictionary",
            "group": BlockGroup.EVENTS_GROUP,
            "group_order": 0,
            "singular_name": "Timestamps",
            "reference_type": TimestampsReference.__name__,
        },
    )

    @property
    def circuit(self) -> CircuitFromIonChannelModels:
        return CircuitFromIonChannelModels(self.ion_channel_models)

    @model_validator(mode="after")
    def atleast_one_ion_channel_model_required(self) -> Self:
        if len(self.ion_channel_models) == 0:
            msg = (
                "At least one ion channel model must be provided to determine entity ID "
                "for campaign."
            )
            raise OBIONEError(msg)
        return self

    def entity_id_for_campaign_entity_generation(self) -> str:
        """Determines the entity ID for the simulation campaign based on the ion channel models.

        For now, we will just use the first ion channel model to determine the entity ID.
        In the future, we will use all ion channel models with the new generic entity types.
        """
        first_icm_block = next(iter(self.ion_channel_models.values()))
        return first_icm_block.ion_channel_model.id_str


class IonChannelModelSimulationSingleConfig(
    IonChannelModelSimulationScanConfig, SingleConfigMixin, SimulationSingleConfigMixin
):
    """Only allows single values."""
