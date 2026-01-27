"""Ion channel model simulation scan config."""

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
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID
from obi_one.scientific.library.constants import (
    _COORDINATE_CONFIG_FILENAME,
    _DEFAULT_SIMULATION_LENGTH_MILLISECONDS,
    _MAX_SIMULATION_LENGTH_MILLISECONDS,
    _MIN_SIMULATION_LENGTH_MILLISECONDS,
    _SCAN_CONFIG_FILENAME,
)
from obi_one.scientific.tasks.generate_simulation_configs import (
    DEFAULT_NODE_SET_NAME,
    DEFAULT_TIMESTAMPS_NAME,
)
from obi_one.scientific.unions.unions_ion_channel_model import (
    IonChannelModelReference,
    IonChannelModelUnion,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
)
from obi_one.scientific.unions.unions_recordings import (
    RecordingReference,
)
from obi_one.scientific.unions.unions_stimuli import (
    StimulusReference,
)
from obi_one.scientific.unions.unions_timestamps import (
    TimestampsReference,
    TimestampsUnion,
)

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    STIMULI_RECORDINGS = "Stimuli & Recordings"


class IonChannelModelSimulationScanConfig(ScanConfig):
    """Form for simulating ion channel model(s)."""

    single_coord_class_name: ClassVar[str] = "IonChannelSimulationSingleConfig"
    name: ClassVar[str] = "Ion Channel Model Simulation Campaign"
    description: ClassVar[str] = "Ion Channal Model SONATA simulation campaign"

    class Config:
        json_schema_extra: ClassVar[dict] = {
            "ui_enabled": True,
            "group_order": [
                BlockGroup.SETUP,
                BlockGroup.STIMULI_RECORDINGS,
            ],
            "default_block_reference_labels": {
                NeuronSetReference.__name__: DEFAULT_NODE_SET_NAME,
                TimestampsReference.__name__: DEFAULT_TIMESTAMPS_NAME,
            },
        }

    class Initialize(Block):
        # contains models and their conductances
        ion_channel_models: dict[str, IonChannelModelUnion] = Field(
            ui_element="block_dictionary",
            default_factory=dict,
            title="Ion Channel Models",
            reference_type=IonChannelModelReference.__name__,
            description="Ion channel models and their conductances.",
            singular_name="Ion Channel Models",
            group=BlockGroup.SETUP,
            group_order=1,
        )

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
            ui_element="float_parameter_sweep",
            default=_DEFAULT_SIMULATION_LENGTH_MILLISECONDS,
            title="Duration",
            description="Simulation length in milliseconds (ms).",
            units="ms",
        )

        temperature: NonNegativeFloat | list[NonNegativeFloat] = Field(
            ui_element="float_parameter_sweep",
            title="Temperature (in °C)",
            description="Temperature of the simulation.",
            default=34.0,
        )

        v_init: float | list[float] = Field(
            ui_element="float_parameter_sweep",
            default=-80.0,
            title="Initial Voltage",
            description="Initial membrane potential in millivolts (mV).",
            units="mV",
        )
        random_seed: int | list[int] = Field(
            ui_element="int_parameter_sweep",
            default=1,
            title="Random Seed",
            description="Random seed for the simulation.",
        )
        _timestep: PositiveFloat | list[PositiveFloat] = PrivateAttr(
            default=0.025
        )  # Simulation time step in ms

        @property
        def timestep(self) -> PositiveFloat | list[PositiveFloat]:
            return self._timestep

    initialize: Initialize = Field(
        ui_element="root_block",
        title="Initialization",
        description="Parameters for initializing the simulation.",
        group=BlockGroup.SETUP,
        group_order=2,
    )

    info: Info = Field(
        ui_element="root_block",
        title="Info",
        description="Information about the ion channel model simulation campaign.",
        group=BlockGroup.SETUP,
        group_order=0,
    )

    # have to define Union. Will probably be same as MEModel + SEClamp.
    # will have to wait for meeting with HPC team to confirm
    stimuli: dict[str, IonChannelModelStimulusUnion] = Field(
        ui_element="block_dictionary",
        default_factory=dict,
        title="Stimuli",
        reference_type=StimulusReference.__name__,
        description="Stimuli for the simulation.",
        singular_name="Stimulus",
        group=BlockGroup.STIMULI_RECORDINGS,
        group_order=0,
    )
    # can we have recording union depending on what model we choose?
    # should allow user to choose any recording in {SUFFIX}.{RANGE variable} list
    # should also allow simple voltage recording
    # attention! For cadynamics, should use `cai`, not `{SUFFIX}.cai`.
    recordings: dict[str, IonChannelModelRecordingUnion] = Field(
        ui_element="block_dictionary",
        default_factory=dict,
        reference_type=RecordingReference.__name__,
        title="Recordings",
        description="Recordings for the simulation.",
        singular_name="Recording",
        group=BlockGroup.STIMULI_RECORDINGS,
        group_order=1,
    )

    timestamps: dict[str, TimestampsUnion] = Field(
        ui_element="block_dictionary",
        default_factory=dict,
        title="Timestamps",
        reference_type=TimestampsReference.__name__,
        description="Timestamps for the simulation.",
        singular_name="Timestamps",
        group=BlockGroup.SETUP,
        group_order=0,
    )

    def create_campaign_entity_with_config(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: entitysdk.client.Client = None,
    ) -> entitysdk.models.IonChannelModelSimulationCampaign:
        """Initializes the ion channel simulation campaign in the database."""
        L.info("1. Initializing ion channel simulation campaign in the database...")
        if multiple_value_parameters_dictionary is None:
            multiple_value_parameters_dictionary = {}

        L.info("-- Register IonChannelModelSimulationCampaign Entity")
        self._campaign = db_client.register_entity(
            entitysdk.models.IonChannelModelSimulationCampaign(  # TODO: implement in entitycore/entitysdk
                name=self.info.campaign_name,
                description=self.info.campaign_description,
                input_models=[
                    icm.entity(db_client=db_client) for icm in self.initialize.ion_channel_models
                ],
                scan_parameters=multiple_value_parameters_dictionary,
            )
        )

        L.info("-- Upload campaign_generation_config")
        _ = db_client.upload_file(
            entity_id=self._campaign.id,
            entity_type=entitysdk.models.IonChannelModelSimulationCampaign,
            file_path=output_root / _SCAN_CONFIG_FILENAME,
            file_content_type="application/json",
            asset_label="campaign_generation_config",
        )

        return self._campaign

    def create_campaign_generation_entity(
        self,
        ion_channel_simulations: list[entitysdk.models.IonChannelModelSimulationConfig],
        db_client: entitysdk.client.Client,
    ) -> None:
        """Register the activity generating the ion channel simulation tasks in the database."""
        L.info("3. Saving completed ion channel simulation campaign generation")

        L.info("-- Register IonChannelModelSimulationGeneration Entity")
        db_client.register_entity(
            entitysdk.models.IonChannelModelSimulationConfigGeneration(  # TODO: implement in entitycore/entitysdk
                start_time=datetime.now(UTC),
                used=[self._campaign],
                generated=ion_channel_simulations,
            )
        )


class IonChannelModelSimulationSingleConfig(IonChannelModelSimulationScanConfig, SingleConfigMixin):
    """Only allows single values and ensures nested attributes follow the same rule."""

    _single_entity: entitysdk.models.IonChannelModelSimulationConfig

    @property
    def single_entity(self) -> entitysdk.models.IonChannelModelSimulationConfig:
        return self._single_entity

    def create_single_entity_with_config(
        self,
        campaign: entitysdk.models.IonChannelModelSimulationCampaign,
        db_client: entitysdk.client.Client,
    ) -> entitysdk.models.IonChannelModelSimulationConfig:
        """Saves the simulation config to the database."""
        L.info(f"2.{self.idx} Saving ion channel model simulation config {self.idx} to database...")

        # This loop will be useful when we support multiple recordings
        for model in self.initialize.ion_channel_models:
            if not isinstance(model, IonChannelModelFromID):
                msg = (
                    "IonChannelModelSimulationConfig can only be saved to entitycore if all input "
                    "models are IonChannelModelFromID"
                )
                raise OBIONEError(msg)

        L.info("-- Register IonChannelModelSimulationConfig Entity")
        self._single_entity = db_client.register_entity(
            entitysdk.models.IonChannelModelSimulationConfig(  # TODO: implement in entitycore/entitysdk
                name=f"IonChannelModelSimulationConfig {self.idx}",
                description=f"IonChannelModelSimulationConfig {self.idx}",
                scan_parameters=self.single_coordinate_scan_params.dictionary_representaiton(),
                ion_channel_model_simulation_campaign_id=campaign.id,
            )
        )

        L.info("-- Upload IonChannelModelSimulationGenerationConfig")
        _ = db_client.upload_file(
            entity_id=self.single_entity.id,
            entity_type=entitysdk.models.IonChannelModelSimulationConfig,
            file_path=Path(self.coordinate_output_root, _COORDINATE_CONFIG_FILENAME),
            file_content_type="application/json",
            asset_label="ion_channel_model_simulation_generation_config",
        )
