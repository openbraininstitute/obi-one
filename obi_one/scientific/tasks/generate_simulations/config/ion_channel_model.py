import logging
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar

import entitysdk
from pydantic import Field, NonNegativeFloat, PositiveFloat, PrivateAttr

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.unions.unions_ion_channel_model import (
    IonChannelModelUnion,
    IonChannelModelReference
)
from obi_one.scientific.from_id.ion_channel_model_from_id import (
    IonChannelModelFromID,
)
from obi_one.scientific.library.constants import (
    _COORDINATE_CONFIG_FILENAME,
    _DEFAULT_SIMULATION_LENGTH_MILLISECONDS,
    _MAX_SIMULATION_LENGTH_MILLISECONDS,
    _MIN_SIMULATION_LENGTH_MILLISECONDS,
    _SCAN_CONFIG_FILENAME,
)
from obi_one.scientific.library.ion_channel_model_circuit import FakeCircuitFromIonChannelModels
from obi_one.scientific.tasks.generate_simulations.config.base import (
    SimulationScanConfig,
    SimulationSingleConfigMixin,
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


DEFAULT_NODE_SET_NAME = "Default: All Biophysical Neurons"
DEFAULT_TIMESTAMPS_NAME = "Default: Simulation Start (0 ms)"


class BlockGroup(StrEnum):
    """Authentication and authorization errors."""

    SETUP_BLOCK_GROUP = "Setup"
    STIMULI_RECORDINGS_BLOCK_GROUP = "Stimuli & Recordings"
    CIRUIT_COMPONENTS_BLOCK_GROUP = "Circuit Components"
    EVENTS_GROUP = "Events"
    CIRCUIT_MANIPULATIONS_GROUP = "Circuit Manipulations"


TARGET_SIMULATOR = "NEURON"
SONATA_VERSION = 2.4


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
    def circuit(self) -> FakeCircuitFromIonChannelModels:
        return FakeCircuitFromIonChannelModels(self.ion_channel_models)

    def create_campaign_entity_with_config(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: entitysdk.client.Client = None,
        # ) -> entitysdk.models.Campaign:  # TODO: generic campaign PR
    ) -> entitysdk.models.Entity:  # TODO: use line above when generic campaign PR is merged
        """Initializes the ion channel simulation campaign in the database."""
        L.info("1. Initializing ion channel simulation campaign in the database...")
        if multiple_value_parameters_dictionary is None:
            multiple_value_parameters_dictionary = {}

        L.info("-- Register Campaign Entity")
        self._campaign = db_client.register_entity(
            entitysdk.models.Campaign(  # TODO: generic PR
                name=self.info.campaign_name,
                description=self.info.campaign_description,
                inputs=[
                    icm.entity(db_client=db_client) for icm in self.ion_channel_models
                ],  # new field for generic Campaign entity
                scan_parameters=multiple_value_parameters_dictionary,
            )
        )

        L.info("-- Upload campaign_generation_config")
        _ = db_client.upload_file(
            entity_id=self._campaign.id,
            entity_type=entitysdk.models.Campaign,  # TODO: generic PR
            file_path=output_root / _SCAN_CONFIG_FILENAME,
            file_content_type="application/json",
            asset_label="campaign_generation_config",
        )

        return self._campaign

    def create_campaign_generation_entity(
        self,
        # simulations: list[entitysdk.models.TaskConfig]  # noqa: ERA001 TODO: generic PR
        simulations: list,  # TODO: # use line above when generic PR is merged
        db_client: entitysdk.client.Client,
    ) -> None:
        L.info("3. Saving completed simulation campaign generation")

        L.info("-- Register TaskConfigGeneration Entity")
        db_client.register_entity(
            entitysdk.models.TaskConfigGeneration(
                start_time=datetime.now(UTC),
                used=[self._campaign],
                generated=simulations,
            )
        )


class IonChannelModelSimulationSingleConfig(
    IonChannelModelSimulationScanConfig, SingleConfigMixin, SimulationSingleConfigMixin
):
    """Only allows single values and ensures nested attributes follow the same rule."""

    def create_single_entity_with_config(
        self,
        # campaign: entitysdk.models.Campaign,  # TODO: generic PR
        campaign,  # noqa: ANN001 # TODO: replace with line above
        db_client: entitysdk.client.Client,
        # ) -> entitysdk.models.TaskConfig:  # TODO: generic PR
    ) -> entitysdk.models.Entity:  # TODO: replace with line above when generic PR is merged
        """Saves the simulation config to the database."""
        L.info(f"2.{self.idx} Saving ion channel model simulation config {self.idx} to database...")

        # This loop will be useful when we support multiple recordings
        for model in self.ion_channel_models:
            if not isinstance(model, IonChannelModelFromID):
                msg = (
                    "TaskConfig can only be saved to entitycore if all input "
                    "models are IonChannelModelFromID"
                )
                raise OBIONEError(msg)

        L.info("-- Register TaskConfig Entity")
        self._single_entity = db_client.register_entity(
            entitysdk.models.TaskConfig(  # TODO: generic PR
                name=f"TaskConfig {self.idx}",
                description=f"TaskConfig {self.idx}",
                scan_parameters=self.single_coordinate_scan_params.dictionary_representaiton(),
                campaign_id=campaign.id,
                inputs=[icm.entity(db_client=db_client) for icm in self.ion_channel_models],
            )
        )

        L.info("-- Upload IonChannelModelSimulationGenerationConfig")
        _ = db_client.upload_file(
            entity_id=self.single_entity.id,
            entity_type=entitysdk.models.TaskConfig,
            file_path=Path(self.coordinate_output_root, _COORDINATE_CONFIG_FILENAME),
            file_content_type="application/json",
            asset_label="simulation_generation_config",
        )
