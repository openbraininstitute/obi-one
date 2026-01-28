"""Ion channel modeling scan config."""

import json
import logging
import subprocess  # noqa: S404
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal

import entitysdk
from entitysdk import models
from entitysdk.types import AssetLabel, ContentType
from pydantic import Field, StringConstraints

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.from_id.ion_channel_recording_from_id import IonChannelRecordingFromID

L = logging.getLogger(__name__)

try:
    from ion_channel_builder.create_model.main import extract_all_equations
    from ion_channel_builder.io.write_output import write_vgate_output
    from ion_channel_builder.run_model.run_model import run_ion_channel_model
except ImportError:

    def extract_all_equations(
        data_paths: list[Path],
        ljps: list,
        eq_names: list[str],
        voltage_exclusion: dict,
        stim_timings: dict,
        stim_timings_corrections: dict,
        output_folder: Path,
    ) -> None:
        pass

    def write_vgate_output(
        eq_names: dict[str, str],
        eq_popt: dict[str, list[float]],
        suffix: str,
        ion: str,
        m_power: int,
        h_power: int,
        output_name: str,
    ) -> None:
        pass

    def run_ion_channel_model(
        mech_suffix: str,
        # current is defined like this in mod file, see ion_channel_builder.io.write_output
        mech_current: float,
        # no need to actually give temperature because model is not temperature-dependent
        temperature: float,
        mech_conductance_name: str,
        output_folder: Path,
        savefig: bool,  # noqa: FBT001
        show: bool,  # noqa: FBT001
    ) -> None:
        pass


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    EQUATIONS = "Equations"
    MODEL = "Model"


class HodgkinHuxleyIonChannelModel(Block):
    m_power: int | list[int] = Field(
        title="m exponent in channel equation",
        default=1,
        ge=1,
        le=4,
        description=(
            r"Exponent \(p\) of \(m\) in the channel equation: "
            r"\(g = \bar{g} \cdot m^p \cdot h^q\)"
        ),
        json_schema_extra={"ui_element": "int_parameter_sweep"},
    )
    h_power: int | list[int] = Field(
        title="h exponent in channel equation",
        default=1,
        ge=0,
        le=4,
        description=(
            r"Exponent \(q\) of \(h\) in the channel equation: "
            r"\(g = \bar{g} \cdot m^p \cdot h^q\)"
        ),
        json_schema_extra={"ui_element": "int_parameter_sweep"},
    )

    minf_eq: Literal["sig_fit_minf"] = Field(
        title="m_{inf} equation",
        description="Equation to use for m_{inf}.",
        default="sig_fit_minf",
        json_schema_extra={"ui_element": "string_constant_enhanced",
                           "latex_by_key": {
                                "sig_fit_minf": r"\frac{1}{1 + e^{\frac{ -(v - v_{half})}{k}}}" 
                            },
                            "description_by_key": {
                                "sig_fit_minf": "Sigmoid equation for m_{inf}."
                            }
        }
    )

    mtau_eq: Literal[
        "sig_fit_mtau", "thermo_fit_mtau", "thermo_fit_mtau_v2", "bell_fit_mtau", "1"
    ] = Field(
        title=r"\tau_m equation",
        description="Equation to use for \tau_m.",
        default="sig_fit_mtau",
        json_schema_extra={"ui_element": "string_selection_enhanced",
                           "latex_by_key": {
                                "sig_fit_mtau": r"",
                                "thermo_fit_mtau": r"",
                                "thermo_fit_mtau_v2": r"",
                                "bell_fit_mtau": r""
                                },
                            "description_by_key": {
                                "sig_fit_mtau": "",
                                "thermo_fit_mtau": "",
                                "thermo_fit_mtau_v2": "",
                                "bell_fit_mtau": "",
                            }
        }
    ),

    hinf_eq: Literal["sig_fit_hinf"] = Field(
        title="h_{inf} equation",
        description="Equation to use for h_{inf}.",
        default="sig_fit_hinf",
        json_schema_extra={"ui_element": "string_constant_enhanced",
                           "latex_by_key": {
                                "sig_fit_hinf": r""
                            },
                            "description_by_key": {
                                "sig_fit_hinf": ""
                            }
        }
    )

    htau_eq: Literal["sig_fit_htau"] = Field(
        title=r"\tau_h equation",
        description="Equation to use for \tau_h.",
        default="sig_fit_htau",
        json_schema_extra={"ui_element": "string_constant_enhanced",
                           "latex_by_key": {
                                "sig_fit_htau": r"" 
                            },
                            "description_by_key": {
                                "sig_fit_htau": ""
                            }
        }
    )


class IonChannelFittingBetaScanConfig(ScanConfig):
    """Form for modeling an ion channel model from a set of ion channel traces."""

    single_coord_class_name: ClassVar[str] = "IonChannelFittingBetaSingleConfig"
    name: ClassVar[str] = "IonChannelFittingBetaScanConfig"
    description: ClassVar[str] = "Models ion channel model from a set of ion channel traces."

    class Config:
        json_schema_extra: ClassVar[dict] = {
            "ui_enabled": True,
            "group_order": [
                BlockGroup.SETUP,
                BlockGroup.MODEL,
            ]
        }

    class Initialize(Block):
        recordings: IonChannelRecordingFromID = Field(
            title="Ion channel recording", 
            description="IDs of the traces of interest.",
            json_schema_extra={"ui_element": "model_identifier"},
        )

        ion_channel_name: Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")] = (
            Field(
                title="Ion channel name",
                description=(
                    "The name you want to give to the generated ion channel model "
                    "(used as SUFFIX in the mod file). "
                    "Name must start with a letter or underscore, and can only contain "
                    "letters, numbers, and underscores."
                ),
                min_length=1,
                default="DefaultIonChannelName",
                json_schema_extra={"ui_element": "string_input"},
            )
        )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the simulation.",
        json_schema_extra={"ui_element": "block_single",
                           "group_order": 0,
                           "group": BlockGroup.SETUP},
    )
    info: Info = Field(
        title="Info",
        description="Information about the ion channel modeling campaign.",
        json_schema_extra={"ui_element": "block_single",
                           "group_order": 0,
                            "group": BlockGroup.SETUP},
    )

    model_type: HodgkinHuxleyIonChannelModel = Field(
        title="Model",
        description="Hodgkin-Huxley type ion channel model to fit.",
        json_schema_extra={"ui_element": "block_single",
                           "group_order": 0,
                           "group": BlockGroup.MODEL},
    )

    def create_campaign_entity_with_config(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: entitysdk.client.Client = None,
    ) -> entitysdk.models.IonChannelModelingCampaign:
        """Initializes the ion channel modeling campaign in the database."""
        L.info("1. Initializing ion channel modeling campaign in the database...")
        if multiple_value_parameters_dictionary is None:
            multiple_value_parameters_dictionary = {}

        L.info("-- Register IonChannelModelingCampaign Entity")
        self._campaign = db_client.register_entity(
            entitysdk.models.IonChannelModelingCampaign(
                name=self.info.campaign_name,
                description=self.info.campaign_description,
                input_recordings=[self.initialize.recordings.entity(db_client=db_client)],
                scan_parameters=multiple_value_parameters_dictionary,
            )
        )

        L.info("-- Upload campaign_generation_config")
        _ = db_client.upload_file(
            entity_id=self._campaign.id,
            entity_type=entitysdk.models.IonChannelModelingCampaign,
            file_path=output_root / "obi_one_scan.json",
            file_content_type="application/json",
            asset_label="campaign_generation_config",
        )

        return self._campaign

    def create_campaign_generation_entity(
        self,
        ion_channel_modelings: list[entitysdk.models.IonChannelModelingConfig],
        db_client: entitysdk.client.Client,
    ) -> None:
        """Register the activity generating the ion channel modeling tasks in the database."""
        L.info("3. Saving completed ion channel modeling campaign generation")

        L.info("-- Register IonChannelModelingGeneration Entity")
        db_client.register_entity(
            entitysdk.models.IonChannelModelingConfigGeneration(
                start_time=datetime.now(UTC),
                used=[self._campaign],
                generated=ion_channel_modelings,
            )
        )


class IonChannelFittingBetaSingleConfig(IonChannelFittingBetaScanConfig, SingleConfigMixin):
    """Only allows single values and ensures nested attributes follow the same rule."""

    _single_entity: entitysdk.models.IonChannelModelingConfig

    @property
    def single_entity(self) -> entitysdk.models.IonChannelModelingConfig:
        return self._single_entity

    def create_single_entity_with_config(
        self,
        campaign: entitysdk.models.IonChannelModelingCampaign,
        db_client: entitysdk.client.Client,
    ) -> entitysdk.models.IonChannelModelingConfig:
        """Saves the simulation to the database."""
        L.info(f"2.{self.idx} Saving ion channel modeling config {self.idx} to database...")

        # For now, we only support a single recording
        if not isinstance(self.initialize.recordings, IonChannelRecordingFromID):
            msg = (
                "IonChannelModeling currently only supports a single IonChannelRecordingFromID. "
                f"Got {type(self.initialize.recordings).__name__}"
            )
            raise OBIONEError(msg)

        # Convert single recording to a list for future compatibility
        recordings = [self.initialize.recordings]

        # This loop will be useful when we support multiple recordings
        for recording in recordings:
            if not isinstance(recording, IonChannelRecordingFromID):
                msg = (
                    "IonChannelModeling can only be saved to entitycore if all input recordings "
                    "are IonChannelRecordingFromID"
                )
                raise OBIONEError(msg)

        L.info("-- Register IonChannelModeling Entity")
        self._single_entity = db_client.register_entity(
            entitysdk.models.IonChannelModelingConfig(
                name=f"IonChannelModelingConfig {self.idx}",
                description=f"IonChannelModelingConfig {self.idx}",
                scan_parameters=self.single_coordinate_scan_params.dictionary_representaiton(),
                ion_channel_modeling_campaign_id=campaign.id,
            )
        )

        L.info("-- Upload ion_channel_modeling_generation_config")
        _ = db_client.upload_file(
            entity_id=self.single_entity.id,
            entity_type=entitysdk.models.IonChannelModelingConfig,
            file_path=Path(self.coordinate_output_root, "obi_one_coordinate.json"),
            file_content_type="application/json",
            asset_label="ion_channel_modeling_generation_config",
        )


class IonChannelFittingBetaTask(Task):
    config: IonChannelFittingBetaSingleConfig

    def download_input(
        self, db_client: entitysdk.client.Client = None
    ) -> tuple[list[Path], list[float]]:
        """Download all the recordings, and return their traces and ljp values."""
        trace_paths = []
        trace_ljps = []

        # Convert single recording to a list for future compatibility
        recordings = [self.config.initialize.recordings]

        for recording in recordings:
            trace_paths.append(
                recording.download_asset(
                    dest_dir=self.config.coordinate_output_root, db_client=db_client
                )
            )
            trace_ljps.append(recording.entity(db_client=db_client).ljp)

        return trace_paths, trace_ljps

    @staticmethod
    def register_json(
        client: entitysdk.client.Client, id_: str | uuid.UUID, json_path: str | Path
    ) -> None:
        client.upload_file(
            entity_id=id_,
            entity_type=models.IonChannelModel,
            file_path=json_path,
            file_content_type=ContentType.application_json,
            asset_label=AssetLabel.ion_channel_model_figure_summary_json,
        )

    @staticmethod
    def register_thumbnail(
        client: entitysdk.client.Client, id_: str | uuid.UUID, path_to_register: str | Path
    ) -> None:
        client.upload_file(
            entity_id=id_,
            entity_type=models.IonChannelModel,
            file_path=path_to_register,
            file_content_type=ContentType.image_png,
            asset_label=AssetLabel.ion_channel_model_thumbnail,
        )

    def cleanup_dict(self, d: Any) -> Any:
        if isinstance(d, Path):
            return str(d.name)
        if isinstance(d, dict):
            return {key: self.cleanup_dict(value) for key, value in d.items() if key != "thumbnail"}
        return d

    @staticmethod
    def register_plots(
        client: entitysdk.client.Client, id_: str | uuid.UUID, paths_to_register: list[str | Path]
    ) -> None:
        for path in paths_to_register:
            client.upload_file(
                entity_id=id_,
                entity_type=models.IonChannelModel,
                file_path=path,
                file_content_type=ContentType.application_pdf,
                asset_label=AssetLabel.ion_channel_model_figure,
            )

    def register_plots_and_json(
        self, db_client: entitysdk.client.Client, figure_filepaths: dict, model_id: str | uuid.UUID
    ) -> None:
        # get the paths of the pdf figures
        paths_to_register = [
            value
            for key1, d in figure_filepaths.items()
            if key1 != "thumbnail"
            for key, value in d.items()
            if key != "order"
        ]
        figure_summary_dict = self.cleanup_dict(figure_filepaths)
        json_path = self.config.coordinate_output_root / "figure_summary.json"
        with json_path.open("w") as f:
            json.dump(figure_summary_dict, f, indent=4)

        self.register_plots(db_client, model_id, paths_to_register)
        if "thumbnail" in figure_filepaths:
            self.register_thumbnail(db_client, model_id, figure_filepaths["thumbnail"])

        if figure_summary_dict != {}:
            self.register_json(db_client, model_id, json_path)

    def save(
        self, mod_filepath: Path, figure_filepaths: dict[Path], db_client: entitysdk.client.Client
    ) -> None:
        # reproduce here what is being done in ion_channel_builder.io.write_output
        useion = entitysdk.models.UseIon(
            ion_name="k",  # TODO: fix this
            read=["ek"],
            write=["ik"],
            valence=1,  # putting 1 for K for now. TODO: fix this
            main_ion=True,
        )
        neuron_block = entitysdk.models.NeuronBlock(
            **{"global": [{"celsius": "degree C"}]},
            range=[
                {"gbar": "S/cm2"},
                {"g": "S/cm2"},
                {"ik": "mA/cm2"},
            ],
            useion=[useion],
            nonspecific=[],
        )

        # Get recording entity to access metadata
        recording_entity = self.config.initialize.recordings.entity(db_client=db_client)

        # Extract subject and brain_region from recording metadata
        subject = recording_entity.subject
        brain_region = recording_entity.brain_region

        model = db_client.register_entity(
            entitysdk.models.IonChannelModel(
                name=self.config.info.campaign_name,
                nmodl_suffix=self.config.initialize.ion_channel_name,
                description=(
                    f"Ion channel model: {self.config.initialize.ion_channel_name}.mod "
                    f"made using recording: {recording_entity.name} "
                    f"for (temperature: {recording_entity.temperature}), "
                    f"brain region: {brain_region.name}, "
                    f"and subject: {subject.name}."
                ),
                contributions=None,  # TODO: fix this
                is_ljp_corrected=True,
                is_temperature_dependent=False,
                temperature_celsius=recording_entity.temperature,
                is_stochastic=False,
                neuron_block=neuron_block,
                brain_region=brain_region,
                subject=subject,
            )
        )

        _ = db_client.upload_file(
            entity_id=model.id,
            entity_type=entitysdk.models.IonChannelModel,
            file_path=mod_filepath,
            file_content_type=ContentType.application_mod,
            asset_label="neuron_mechanisms",
        )

        self.register_plots_and_json(db_client, figure_filepaths, model.id)

        return model.id

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,
        entity_cache: bool = False,  # noqa: ARG002
    ) -> str:  # returns the id of the generated ion channel model
        """Download traces from entitycore, use them to build an ion channel, then register it."""
        try:
            # download traces asset and metadata given id.
            # Get ljp (liquid junction potential) voltage corection from metadata
            trace_paths, trace_ljps = self.download_input(db_client=db_client)

            # prepare data to feed
            eq_names = {
                "minf": self.config.model_type.minf_eq,
                "mtau": self.config.model_type.mtau_eq,
                "hinf": self.config.model_type.hinf_eq,
                "htau": self.config.model_type.htau_eq,
            }
            voltage_exclusion = {
                "activation": {
                    "above": None,
                    "below": None,
                },
                "inactivation": {
                    "above": None,
                    "below": None,
                },
            }
            stim_timings = {
                "activation": {
                    "start": None,
                    "end": None,
                },
                "inactivation_iv": {
                    "start": None,
                    "end": None,
                },
                "inactivation_tc": {
                    "start": None,
                    "end": None,
                },
            }
            stim_timings_corrections = {
                "activation": {
                    "start": 0.0,
                    "end": -1.0,
                },
                "inactivation_iv": {
                    "start": 5.0,
                    "end": -1.0,
                },
                "inactivation_tc": {
                    "start": 0.0,
                    "end": -1.0,
                },
            }
            # run ion_channel_builder main function to get optimised parameters
            eq_popt = extract_all_equations(
                data_paths=trace_paths,
                ljps=trace_ljps,
                eq_names=eq_names,
                voltage_exclusion=voltage_exclusion,
                stim_timings=stim_timings,
                stim_timings_corrections=stim_timings_corrections,
                output_folder=self.config.coordinate_output_root,
            )

            # create new mod file
            mechanisms_dir = self.config.coordinate_output_root / "mechanisms"
            mechanisms_dir.mkdir(parents=True, exist_ok=True)
            output_name = mechanisms_dir / f"{self.config.initialize.ion_channel_name}.mod"

            write_vgate_output(
                eq_names=eq_names,
                eq_popt=eq_popt,
                suffix=self.config.initialize.ion_channel_name,
                ion="k",
                m_power=self.config.model_type.m_power,
                h_power=self.config.model_type.h_power,
                output_name=output_name,
            )

            # compile output mod file
            subprocess.run(  # noqa: S603
                [  # noqa: S607
                    "nrnivmodl",
                    "-incflags",
                    "-DDISABLE_REPORTINGLIB",
                    str(mechanisms_dir),
                ],
                check=True,
            )

            # Get recording entity to access temperature
            recording_entity = self.config.initialize.recordings.entity(db_client=db_client)

            # run ion_channel_builder mod file runner to produce plots
            figure_paths_dict = run_ion_channel_model(
                mech_suffix=self.config.initialize.ion_channel_name,
                # current is defined like this in mod file, see ion_channel_builder.io.write_output
                mech_current="ik",
                temperature=recording_entity.temperature,
                mech_conductance_name=f"g{self.config.initialize.ion_channel_name}bar",
                output_folder=self.config.coordinate_output_root,
                savefig=True,
                show=False,
            )

            # register the mod file and figures to the platform
            model_id = self.save(
                mod_filepath=output_name, figure_filepaths=figure_paths_dict, db_client=db_client
            )

        except Exception as e:
            error_message = f"Ion channel modeling failed: {e}"
            raise Exception(error_message) from e  # noqa: TRY002
        else:
            return model_id
