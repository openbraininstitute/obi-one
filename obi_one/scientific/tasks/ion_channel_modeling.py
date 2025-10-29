"""Ion channel modeling scan config."""

import json
import logging
import subprocess  # noqa: S404
import uuid
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, Literal

import entitysdk
from entitysdk import models
from entitysdk.types import AssetLabel, ContentType
from fastapi import HTTPException
from pydantic import Field, NonNegativeFloat

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.blocks import ion_channel_equations as equations_module
from obi_one.scientific.from_id.ion_channel_recording_from_id import IonChannelRecordingFromID

L = logging.getLogger(__name__)

"""
from ion_channel_builder.create_model.main import extract_all_equations
from ion_channel_builder.io.write_output import write_vgate_output
from ion_channel_builder.run_model.run_model import run_ion_channel_model
"""


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
    GATEEXPONENTS = "Gates Exponents"
    ADVANCED = "Advanced"


class IonChannelFittingScanConfig(ScanConfig):
    """Form for modeling an ion channel model from a set of ion channel traces."""

    single_coord_class_name: ClassVar[str] = "IonChannelFittingSingleConfig"
    name: ClassVar[str] = "IonChannelFittingScanConfig"
    description: ClassVar[str] = "Models ion channel model from a set of ion channel traces."

    class Config:
        json_schema_extra: ClassVar[dict] = {
            "block_block_group_order": [
                BlockGroup.SETUP,
                BlockGroup.EQUATIONS,
                BlockGroup.GATEEXPONENTS,
                BlockGroup.ADVANCED,
            ]
        }

    class Initialize(Block):
        # traces
        recordings: tuple[IonChannelRecordingFromID] = Field(
            description="IDs of the traces of interest."
        )

        # mod file creation
        suffix: str = Field(
            title="Ion channel SUFFIX (ion channel name to use in the mod file)",
            description=("SUFFIX to use in the mod file. Will also be used for the mod file name."),
            min_length=1,
        )
        ion: Literal["k"] = Field(
            # we will only have potassium recordings first,
            # so it makes sense to have this default value here
            title="Ion",
            default="k",
            description=("Ion to use in the mod file."),
        )
        temperature: int = Field(
            title="Temperature",
            description=(
                "Temperature of the model. "
                "Should be consistent with the one at which the recordings were made. "
            ),
            units="C",
            ge=-273,
        )

    class GateExponents(Block):
        # mod file creation
        m_power: int = Field(
            title="m exponent in channel equation",
            default=1,
            ge=0,  # can be zero
            le=4,  # should be 4 or lower
            description=("Raise m to this power in the BREAKPOINT equation."),
        )
        h_power: int = Field(
            title="h exponent in channel equation",
            default=1,
            ge=0,  # can be zero
            le=4,  # should be 4 or lower
            description=("Raise h to this power in the BREAKPOINT equation."),
        )

    class StimulusVoltageExclusion(Block):
        # trace loading customisation: voltage exclusion
        act_exclude_voltages_above: float | None = Field(
            title="Exclude activation voltages above",
            default=None,
            description=(
                "Do not use any activation traces responses from input voltages "
                "above this value. Use 'None' not to exclude any trace."
            ),
            units="mV",
        )
        act_exclude_voltages_below: float | None = Field(
            title="Exclude activation voltages below",
            default=None,
            description=(
                "Do not use any activation traces responses from input voltages "
                "below this value. Use 'None' not to exclude any trace."
            ),
            units="mV",
        )
        inact_exclude_voltages_above: float | None = Field(
            title="Exclude inactivation voltages above",
            default=None,
            description=(
                "Do not use any inactivation traces responses from input voltages "
                "above this value. Use 'None' not to exclude any trace."
            ),
            units="mV",
        )
        inact_exclude_voltages_below: float | None = Field(
            title="Exclude inactivation voltages below",
            default=None,
            description=(
                "Do not use any inactivation traces responses from input voltages "
                "below this value. Use 'None' not to exclude any trace."
            ),
            units="mV",
        )

    class StimulusTimings(Block):
        # trace loading customisation: stimulus timings
        act_stim_start: NonNegativeFloat | None = Field(
            title="Activation stimulus start time",
            default=None,
            description=(
                "Activation stimulus start timing. "
                "If None, this value will be taken from nwb "
                "and will be corrected with act_stim_start_correction."
            ),
            units="ms",
        )
        act_stim_end: NonNegativeFloat | None = Field(
            title="Activation stimulus end time",
            default=None,
            description=(
                "Activation stimulus end timing. "
                "If None, this value will be taken from nwb "
                "and will be corrected with act_stim_end_correction."
            ),
            units="ms",
        )
        inact_iv_stim_start: NonNegativeFloat | None = Field(
            title="Inactivation stimulus start time for IV computation",
            default=None,
            description=(
                "Inactivation stimulus start timing for IV computation. "
                "If None, this value will be taken from nwb "
                "and will be corrected with inact_iv_stim_start_correction."
            ),
            units="ms",
        )
        inact_iv_stim_end: NonNegativeFloat | None = Field(
            title="Inactivation stimulus end time for IV computation",
            default=None,
            description=(
                "Inactivation stimulus end timing for IV computation. "
                "If None, this value will be taken from nwb "
                "and will be corrected with inact_iv_stim_end_correction."
            ),
            units="ms",
        )
        inact_tc_stim_start: NonNegativeFloat | None = Field(
            title="Inactivation stimulus start time for time constant computation",
            default=None,
            description=(
                "Inactivation stimulus start timing for time constant computation. "
                "If None, this value will be taken from nwb "
                "and will be corrected with inact_tc_stim_start_correction."
            ),
            units="ms",
        )
        inact_tc_stim_end: NonNegativeFloat | None = Field(
            title="Inactivation stimulus end time for time constant computation",
            default=None,
            description=(
                "Inactivation stimulus end timing for time constant computation. "
                "If None, this value will be taken from nwb "
                "and will be corrected with inact_tc_stim_end_correction."
            ),
            units="ms",
        )

        # trace loading customisation: stimulus timings corrections
        act_stim_start_correction: float = Field(
            title=(
                "Correction to apply to activation stimulus start time taken from source file, "
                "in ms."
            ),
            default=0,
            description=(
                "Correction to add to the timing taken from nwb file for activation stimulus start."
                "This is mainly used to remove artefacts "
                "that appear when stimulus is applied/removed."
                "Positive values are expected since we usually want to remove the response "
                "right after the beginning of the stimulus, but negative values are also accepted."
            ),
            units="ms",
        )
        act_stim_end_correction: float = Field(
            title=(
                "Correction to apply to activation stimulus end time taken from source file, in ms."
            ),
            default=-1,
            description=(
                "Correction to add to the timing taken from nwb file for activation stimulus end."
                "This is mainly used to remove artefacts "
                "that appear when stimulus is applied/removed."
                "Negative values are expected since we usually want to remove the response "
                "right before the end of the stimulus, but positive values are also accepted."
            ),
            units="ms",
        )
        inact_iv_stim_start_correction: float = Field(
            title=(
                "Correction to apply to inactivation stimulus start time "
                "for IV computation taken from source file, in ms."
            ),
            default=5,
            description=(
                "Correction to add to the timing taken from nwb file "
                "for inactivation stimulus start for IV computation."
                "This is mainly used to remove artefacts "
                "that appear when stimulus is applied/removed."
                "Positive values are expected since we usually want to remove the response "
                "right after the beginning of the stimulus, but negative values are also accepted."
            ),
            units="ms",
        )
        inact_iv_stim_end_correction: float = Field(
            title=(
                "Correction to apply to inactivation stimulus end time "
                "for IV computation taken from source file, in ms."
            ),
            default=-1,
            description=(
                "Correction to add to the timing taken from nwb file "
                "for inactivation stimulus end for IV computation."
                "This is mainly used to remove artefacts "
                "that appear when stimulus is applied/removed."
                "Negative values are expected since we usually want to remove the response "
                "right before the end of the stimulus, but positive values are also accepted."
            ),
            units="ms",
        )
        inact_tc_stim_start_correction: float = Field(
            title=(
                "Correction to apply to inactivation stimulus start time "
                "for time constant computation taken from source file, in ms."
            ),
            default=0,
            description=(
                "Correction to add to the timing taken from nwb file "
                "for inactivation stimulus start for time constant computation."
                "This is mainly used to remove artefacts "
                "that appear when stimulus is applied/removed."
                "Positive values are expected since we usually want to remove the response "
                "right after the beginning of the stimulus, but negative values are also accepted."
            ),
            units="ms",
        )
        inact_tc_stim_end_correction: float = Field(
            title=(
                "Correction to apply to inactivation stimulus end time "
                "for time constant computation taken from source file, in ms."
            ),
            default=-1,
            description=(
                "Correction to add to the timing taken from nwb file "
                "for inactivation stimulus end for time constant computation."
                "This is mainly used to remove artefacts "
                "that appear when stimulus is applied/removed."
                "Negative values are expected since we usually want to remove the response "
                "right before the end of the stimulus, but positive values are also accepted."
            ),
            units="ms",
        )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the simulation.",
        group=BlockGroup.SETUP,
        group_order=1,
    )

    info: Info = Field(
        title="Info",
        description="Information about the ion channel modeling campaign.",
        group=BlockGroup.SETUP,
        group_order=0,
    )

    minf_eq: equations_module.MInfUnion = Field(
        title="m_{inf} equation",
        reference_type=equations_module.MInfReference.__name__,
        group=BlockGroup.EQUATIONS,
        group_order=0,
    )
    mtau_eq: equations_module.MTauUnion = Field(
        title=r"\tau_m equation",
        reference_type=equations_module.MTauReference.__name__,
        group=BlockGroup.EQUATIONS,
        group_order=1,
    )
    hinf_eq: equations_module.HInfUnion = Field(
        title="h_{inf} equation",
        reference_type=equations_module.HInfReference.__name__,
        group=BlockGroup.EQUATIONS,
        group_order=2,
    )
    htau_eq: equations_module.HTauUnion = Field(
        title=r"\tau_h equation",
        reference_type=equations_module.HTauReference.__name__,
        group=BlockGroup.EQUATIONS,
        group_order=3,
    )

    gate_exponents: GateExponents = Field(
        title="m & h gate exponents",
        description="Set the power of m and h gates used in HH formalism equations.",
        group=BlockGroup.GATEEXPONENTS,
        group_order=0,
    )

    stimulus_voltage_exclusion: StimulusVoltageExclusion = Field(
        title="Stimulus voltage exclusion",
        description=(
            "Set the maximum and minimum voltages to consider for activation and inactivation."
        ),
        group=BlockGroup.ADVANCED,
        group_order=0,
    )

    stimulus_timings: StimulusTimings = Field(
        title="Stimulus timings",
        description="Set the stimulus start and end timings for activation and inactivation.",
        group=BlockGroup.ADVANCED,
        group_order=1,
    )

    def create_campaign_entity_with_config(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: entitysdk.client.Client = None,
    ) -> None:
        """Initializes the ion channel modeling campaign in the database."""
        # TODO: and implement related entities on entitysdk

    def create_campaign_generation_entity(
        self,
        ion_channel_modelings: list,
        db_client: entitysdk.client.Client,
    ) -> None:
        """Register the activity generating the ion channel modeling tasks in the database."""
        # TODO: also implement entitysdk related entities


class IonChannelFittingSingleConfig(IonChannelFittingScanConfig, SingleConfigMixin):
    """Only allows single values and ensures nested attributes follow the same rule."""

    _single_entity: Any

    @property
    def single_entity(self) -> Any:
        return self._single_entity

    def create_single_entity_with_config(
        self,
        campaign: Any,
        db_client: entitysdk.client.Client,
    ) -> None:
        """Saves the simulation to the database."""
        # TODO: also add related entities in entitysdk


class IonChannelFittingTask(Task):
    config: IonChannelFittingSingleConfig

    def download_input(
        self, db_client: entitysdk.client.Client = None
    ) -> tuple[list[Path], list[float]]:
        """Download all the recordings, and return their traces and ljp values."""
        trace_paths = []
        trace_ljps = []
        for recording in self.config.initialize.recordings:
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
            ion_name=self.config.initialize.ion,
            read=f"e{self.config.initialize.ion}",
            write=f"i{self.config.initialize.ion}",
            valence=None,  # should we put None or 1 here?
            main_ion=True,
        )
        neuron_block = entitysdk.models.NeuronBlock(
            global_=None,
            range=[
                [
                    {f"g{self.config.initialize.suffix}bar": "S/cm2"},
                    {"g{self.config.initialize.suffix}": "S/cm2"},
                    {"i{self.config.initialize.ion}": "mA/cm2"},
                ]
            ],
            useion=useion,
            nonspecific=None,
        )
        model = db_client.register_entity(
            entitysdk.models.IonChannelModel(
                name=self.config.initialize.suffix,
                nmodl_suffix=self.config.initialize.suffix,
                description=(
                    f"Ion channel model of {self.config.initialize.suffix} "
                    f"at {self.config.initialize.temperature} C."
                ),
                contributions=None,  # TBD
                is_ljp_corrected=True,
                is_temperature_dependent=False,
                temperature_celsius=self.config.initialize.temperature,
                is_stochastic=False,
                neuron_block=neuron_block,
            )
        )

        _ = db_client.upload_file(
            entity_id=model.id,
            entity_type=entitysdk.models.IonChannelModel,
            file_path=mod_filepath,
            file_content_type=ContentType.application_mod,
            asset_label="mod file",
        )

        self.register_plots_and_json(db_client, figure_filepaths, model.id)

        # register the Activity
        L.info("-- Register IonChannelExecution Entity")
        # TODO: re-implement this when entitysdk is ready

        return model.id

    def execute(
        self, db_client: entitysdk.client.Client = None
    ) -> str:  # returns the id of the generated ion channel model
        """Download traces from entitycore, use them to build an ion channel, then register it."""
        try:
            # download traces asset and metadata given id.
            # Get ljp (liquid junction potential) voltage corection from metadata
            trace_paths, trace_ljps = self.download_input(db_client=db_client)

            # prepare data to feed
            eq_names = {
                "minf": self.config.minf_eq.equation_key,
                "mtau": self.config.mtau_eq.equation_key,
                "hinf": self.config.hinf_eq.equation_key,
                "htau": self.config.htau_eq.equation_key,
            }
            voltage_exclusion = {
                "activation": {
                    "above": self.config.expert.act_exclude_voltages_above,
                    "below": self.config.expert.act_exclude_voltages_below,
                },
                "inactivation": {
                    "above": self.config.expert.inact_exclude_voltages_above,
                    "below": self.config.expert.inact_exclude_voltages_below,
                },
            }
            stim_timings = {
                "activation": {
                    "start": self.config.expert.act_stim_start,
                    "end": self.config.expert.act_stim_end,
                },
                "inactivation_iv": {
                    "start": self.config.expert.inact_iv_stim_start,
                    "end": self.config.expert.inact_iv_stim_end,
                },
                "inactivation_tc": {
                    "start": self.config.expert.inact_tc_stim_start,
                    "end": self.config.expert.inact_tc_stim_end,
                },
            }
            stim_timings_corrections = {
                "activation": {
                    "start": self.config.expert.act_stim_start_correction,
                    "end": self.config.expert.act_stim_end_correction,
                },
                "inactivation_iv": {
                    "start": self.config.expert.inact_iv_stim_start_correction,
                    "end": self.config.expert.inact_iv_stim_end_correction,
                },
                "inactivation_tc": {
                    "start": self.config.expert.inact_tc_stim_start_correction,
                    "end": self.config.expert.inact_tc_stim_end_correction,
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
            output_name = mechanisms_dir / f"{self.config.initialize.suffix}.mod"
            write_vgate_output(
                eq_names=eq_names,
                eq_popt=eq_popt,
                suffix=self.config.initialize.suffix,
                ion=self.config.initialize.ion,
                m_power=self.config.gate_exponents.m_power,
                h_power=self.config.gate_exponents.h_power,
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

            # run ion_channel_builder mod file runner to produce plots
            figure_paths_dict = run_ion_channel_model(
                mech_suffix=self.config.initialize.suffix,
                # current is defined like this in mod file, see ion_channel_builder.io.write_output
                mech_current=f"i{self.config.initialize.ion}",
                # no need to actually give temperature because model is not temperature-dependent
                temperature=self.config.initialize.temperature,
                mech_conductance_name=f"g{self.config.initialize.suffix}bar",
                output_folder=self.config.coordinate_output_root,
                savefig=True,
                show=False,
            )

            # register the mod file and figures to the platform
            model_id = self.save(
                mod_filepath=output_name, figure_filepaths=figure_paths_dict, db_client=db_client
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}") from e
        else:
            return model_id
