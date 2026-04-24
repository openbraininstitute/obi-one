import logging
from typing import Annotated, ClassVar, Self

from pydantic import Field, NonNegativeFloat, PositiveFloat, PrivateAttr, model_validator

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
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
    DEFAULT_TIMESTAMPS_NAME,
    BlockGroup,
    SimulationScanConfig,
    SimulationSingleConfigMixin,
)
from obi_one.scientific.unions.unions_ion_channel_model import (
    IonChannelModelReference,
    IonChannelModelUnion,
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
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP_BLOCK_GROUP,
            BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            BlockGroup.EVENTS_GROUP,
        ],
        SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS: {
            TimestampsReference.__name__: DEFAULT_TIMESTAMPS_NAME,
        },
        SchemaKey.PROPERTY_ENDPOINTS: {
            MappedPropertiesGroup.ION_CHANNEL_MODEL: "/mapped-ion-channel-properties",
        },
    }

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
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
                SchemaKey.UNITS: Units.MILLISECONDS,
            },
        )

        temperature: NonNegativeFloat | list[NonNegativeFloat] = Field(
            title="Temperature (in °C)",
            description="Temperature of the simulation.",
            default=34.0,
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
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
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 2,
        },
    )

    info: Info = Field(
        title="Info",
        description="Information about the campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    # contains models and their conductances
    ion_channel_models: dict[str, IonChannelModelUnion] = Field(
        default_factory=dict,
        min_length=1,
        title="Ion Channel Models",
        description="Ion channel models and their conductance / max permeability.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.GROUP: BlockGroup.SETUP_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
            SchemaKey.SINGULAR_NAME: "Ion Channel Model",
            SchemaKey.REFERENCE_TYPES: [IonChannelModelReference.__name__],
        },
    )

    # have to define Union. Will probably be same as MEModel + SEClamp.
    # will have to wait for meeting with HPC team to confirm
    stimuli: dict[str, IonChannelModelStimulusUnion] = Field(
        default_factory=dict,
        title="Stimuli",
        description="Stimuli for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.GROUP: BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
            SchemaKey.SINGULAR_NAME: "Stimulus",
            SchemaKey.REFERENCE_TYPES: [StimulusReference.__name__],
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
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.GROUP: BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
            SchemaKey.SINGULAR_NAME: "Recording",
            SchemaKey.REFERENCE_TYPES: [RecordingReference.__name__],
        },
    )

    timestamps: dict[str, TimestampsUnion] = Field(
        default_factory=dict,
        title="Timestamps",
        description="Timestamps for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.GROUP: BlockGroup.EVENTS_GROUP,
            SchemaKey.GROUP_ORDER: 0,
            SchemaKey.SINGULAR_NAME: "Timestamps",
            SchemaKey.REFERENCE_TYPES: [TimestampsReference.__name__],
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
    IonChannelModelSimulationScanConfig, SimulationSingleConfigMixin
):
    """Only allows single values."""
