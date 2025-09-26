"""Ion channel modeling scan config."""

import subprocess  # noqa: S404
from pathlib import Path
from typing import ClassVar

import entitysdk
from entitysdk.types import ContentType
from fastapi import HTTPException
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.blocks import ion_channel_equations as equations_module
from obi_one.scientific.from_id.ion_channel_recording_from_id import IonChannelRecordingFromID

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
    output_folder: Path,
    savefig: bool,  # noqa: FBT001
    show: bool,  # noqa: FBT001
) -> None:
    pass


class IonChannelFittingScanConfig(ScanConfig):
    """Form for modeling an ion channel model from a set of ion channel traces."""

    single_coord_class_name: ClassVar[str] = "IonChannelFittingScanConfig"
    name: ClassVar[str] = "IonChannelFittingScanConfig"
    description: ClassVar[str] = "Models ion channel model from a set of ion channel traces."

    class Initialize(Block):
        # traces
        recordings: tuple[IonChannelRecordingFromID] = Field(
            description="IDs of the traces of interest."
        )

        # mod file creation
        suffix: str = Field(
            title="Ion channel SUFFIX (ion channel name to use in the mod file)",
            description=("SUFFIX to use in the mod file. Will also be used for the mod file name."),
        )
        ion: str = Field(
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
        )

    class Equations(Block):
        # equations
        minf_eq: dict[str, equations_module.MInfUnion] = Field(
            default_factory=dict,
            title="m_{inf} equation",
            reference_type=equations_module.MInfReference.__name__,
        )
        mtau_eq: dict[str, equations_module.MTauUnion] = Field(
            default_factory=dict,
            title=r"\tau_m equation",
            reference_type=equations_module.MTauReference.__name__,
        )
        hinf_eq: dict[str, equations_module.HInfUnion] = Field(
            default_factory=dict,
            title="h_{inf} equation",
            reference_type=equations_module.HInfReference.__name__,
        )
        htau_eq: dict[str, equations_module.HTauUnion] = Field(
            default_factory=dict,
            title=r"\tau_h equation",
            reference_type=equations_module.HTauReference.__name__,
        )

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

    class Expert(Block):
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

        # trace loading customisation: stimulus timings
        act_stim_start: int | None = Field(
            title="Activation stimulus start time",
            default=None,
            description=(
                "Activation stimulus start timing. "
                "If None, this value will be taken from nwb "
                "and will be corrected with act_stim_start_correction."
            ),
            units="ms",
        )
        act_stim_end: int | None = Field(
            title="Activation stimulus end time",
            default=None,
            description=(
                "Activation stimulus end timing. "
                "If None, this value will be taken from nwb "
                "and will be corrected with act_stim_end_correction."
            ),
            units="ms",
        )
        inact_iv_stim_start: int | None = Field(
            title="Inactivation stimulus start time for IV computation",
            default=None,
            description=(
                "Inactivation stimulus start timing for IV computation. "
                "If None, this value will be taken from nwb "
                "and will be corrected with inact_iv_stim_start_correction."
            ),
            units="ms",
        )
        inact_iv_stim_end: int | None = Field(
            title="Inactivation stimulus end time for IV computation",
            default=None,
            description=(
                "Inactivation stimulus end timing for IV computation. "
                "If None, this value will be taken from nwb "
                "and will be corrected with inact_iv_stim_end_correction."
            ),
            units="ms",
        )
        inact_tc_stim_start: int | None = Field(
            title="Inactivation stimulus start time for time constant computation",
            default=None,
            description=(
                "Inactivation stimulus start timing for time constant computation. "
                "If None, this value will be taken from nwb "
                "and will be corrected with inact_tc_stim_start_correction."
            ),
            units="ms",
        )
        inact_tc_stim_end: int | None = Field(
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
        act_stim_start_correction: int = Field(
            title=(
                "Correction to apply to activation stimulus start time taken from source file, "
                "in ms."
            ),
            default=0,
            description=(
                "Correction to add to the timing taken from nwb file for activation stimulus start."
            ),
            units="ms",
        )
        act_stim_end_correction: int = Field(
            title=(
                "Correction to apply to activation stimulus end time taken from source file, in ms."
            ),
            default=-1,
            description=(
                "Correction to add to the timing taken from nwb file for activation stimulus end."
            ),
            units="ms",
        )
        inact_iv_stim_start_correction: int = Field(
            title=(
                "Correction to apply to inactivation stimulus start time "
                "for IV computation taken from source file, in ms."
            ),
            default=5,
            description=(
                "Correction to add to the timing taken from nwb file "
                "for inactivation stimulus start for IV computation."
            ),
            units="ms",
        )
        inact_iv_stim_end_correction: int = Field(
            title=(
                "Correction to apply to inactivation stimulus end time "
                "for IV computation taken from source file, in ms."
            ),
            default=-1,
            description=(
                "Correction to add to the timing taken from nwb file "
                "for inactivation stimulus end for IV computation."
            ),
            units="ms",
        )
        inact_tc_stim_start_correction: int = Field(
            title=(
                "Correction to apply to inactivation stimulus start time "
                "for time constant computation taken from source file, in ms."
            ),
            default=0,
            description=(
                "Correction to add to the timing taken from nwb file "
                "for inactivation stimulus start for time constant computation."
            ),
            units="ms",
        )
        inact_tc_stim_end_correction: int = Field(
            title=(
                "Correction to apply to inactivation stimulus end time "
                "for time constant computation taken from source file, in ms."
            ),
            default=-1,
            description=(
                "Correction to add to the timing taken from nwb file "
                "for inactivation stimulus end for time constant computation."
            ),
            units="ms",
        )

    initialize: Initialize
    equations: Equations
    expert: Expert

    def as_dict(self) -> dict:
        """Return the form as a dict."""
        return {
            "initialize": {
                "recordings": [rec.id_str for rec in self.initialize.recordings],
                "suffix": self.initialize.suffix,
                "ion": self.initialize.ion,
                "temperature": self.initialize.temperature,
            },
            "equations": {
                "minf_eq": self.equations.minf_eq["minf"].__class__.__name__,
                "mtau_eq": self.equations.mtau_eq["mtau"].__class__.__name__,
                "hinf_eq": self.equations.hinf_eq["hinf"].__class__.__name__,
                "htau_eq": self.equations.htau_eq["htau"].__class__.__name__,
                "m_power": self.equations.m_power,
                "h_power": self.equations.h_power,
            },
            "expert": vars(self.expert),
        }


class IonChannelFittingSingleConfig(IonChannelFittingScanConfig, SingleConfigMixin):
    pass


class IonChannelFittingTask(Task):
    config: IonChannelFittingSingleConfig

    def generate(self, db_client: entitysdk.client.Client = None) -> tuple[list[Path], list[float]]:
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
        for key, fpath in figure_filepaths.items():
            _ = db_client.upload_file(
                entity_id=model.id,
                entity_type=entitysdk.models.IonChannelModel,
                file_path=fpath,
                file_content_type=ContentType.application_pdf,
                asset_label=key,
            )

        return model.id

    def run(
        self, db_client: entitysdk.client.Client = None
    ) -> str:  # returns the id of the generated ion channel model
        """Download traces from entitycore, use them to build an ion channel, then register it."""
        try:
            # download traces asset and metadata given id. Get ljp from metadata
            trace_paths, trace_ljps = self.generate(db_client=db_client)

            # prepare data to feed
            eq_names = {
                "minf": next(iter(self.config.equations.minf_eq.values())).equation_key,
                "mtau": next(iter(self.config.equations.mtau_eq.values())).equation_key,
                "hinf": next(iter(self.config.equations.hinf_eq.values())).equation_key,
                "htau": next(iter(self.config.equations.htau_eq.values())).equation_key,
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
                m_power=self.config.equations.m_power,
                h_power=self.config.equations.h_power,
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


def ion_channel_fitting_from_dict(icf_dict: dict) -> IonChannelFittingSingleConfig:
    """Create IonChannelFitting instance from a dict."""
    return IonChannelFittingSingleConfig(
        initialize=IonChannelFittingScanConfig.Initialize(
            recordings=[
                IonChannelRecordingFromID(id_str=icr_id)
                for icr_id in icf_dict["initialize"]["recordings"]
            ],
            suffix=icf_dict["initialize"]["suffix"],
            ion=icf_dict["initialize"]["ion"],
            temperature=icf_dict["initialize"]["temperature"],
        ),
        equations=IonChannelFittingScanConfig.Equations(
            minf_eq={"minf": getattr(equations_module, icf_dict["equations"]["minf_eq"])()},
            mtau_eq={"mtau": getattr(equations_module, icf_dict["equations"]["mtau_eq"])()},
            hinf_eq={"hinf": getattr(equations_module, icf_dict["equations"]["hinf_eq"])()},
            htau_eq={"htau": getattr(equations_module, icf_dict["equations"]["htau_eq"])()},
            m_power=icf_dict["equations"]["m_power"],
            h_power=icf_dict["equations"]["h_power"],
        ),
        expert=IonChannelFittingScanConfig.Expert(**icf_dict["expert"]),
    )
