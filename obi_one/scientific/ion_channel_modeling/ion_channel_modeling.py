"""Ion channel modeling form."""

from typing import Any, ClassVar

import entitysdk
from fastapi import HTTPException
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.form import Form
from obi_one.core.single import SingleCoordinateMixin
from obi_one.scientific.ion_channel_modeling.equations import MInfUnion, MTauUnion, HInfUnion, HTauUnion


# TODO: give proper title to each field
# TODO: also arrange stuff in nice blocks, including an 'Expert settings' block
class IonChannelFittingForm(Form):
    """Form for modeling an ion channel model from a set of ion channel traces."""

    single_coord_class_name: ClassVar[str] = "IonChannelFittingForm"
    name: ClassVar[str] = "IonChannelFittingForm"
    description: ClassVar[str] = "Models ion channel model from a set of ion channel traces."

    class Initialize(Block):
        # traces
        trace_ids: tuple[str] = Field(description="IDs of the traces of interest.")

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

    class Equations(Block):
        # equations
        minf_eq: ClassVar[Any] = MInfUnion
        mtau_eq: ClassVar[Any] = MTauUnion
        hinf_eq: ClassVar[Any] = HInfUnion
        htau_eq: ClassVar[Any] = HTauUnion

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
                "Do not use any activation traces responses from input voltages above this value. "
                "Use 'None' not to exclude any trace."
            ),
            units="mV",
        )
        act_exclude_voltages_below: float | None = Field(
            title="Exclude activation voltages below",
            default=None,
            description=(
                "Do not use any activation traces responses from input voltages below this value. "
                "Use 'None' not to exclude any trace."
            ),
            units="mV",
        )
        inact_exclude_voltages_above: float | None = Field(
            title="Exclude inactivation voltages above",
            default=None,
            description=(
                "Do not use any inactivation traces responses from input voltages above this value. "
                "Use 'None' not to exclude any trace."
            ),
            units="mV",
        )
        inact_exclude_voltages_below: float | None = Field(
            title="Exclude inactivation voltages below",
            default=None,
            description=(
                "Do not use any inactivation traces responses from input voltages below this value. "
                "Use 'None' not to exclude any trace."
            ),
            units="mV",
        )

        # trace loading customisation: stimulus timings
        act_stim_start: int | None = Field(
            title="Activation stimulus start time",
            default=None,
            description=(
                "Activation stimulus start timing. "
                "If None, this value will be taken from nwb and will be corrected with act_stim_start_correction."
            ),
            units="ms",
        )
        act_stim_end: int | None = Field(
            title="Activation stimulus end time",
            default=None,
            description=(
                "Activation stimulus end timing. "
                "If None, this value will be taken from nwb and will be corrected with act_stim_end_correction."
            ),
            units="ms",
        )
        inact_iv_stim_start: int | None = Field(
            title="Inactivation stimulus start time for IV computation",
            default=None,
            description=(
                "Inactivation stimulus start timing for IV computation. "
                "If None, this value will be taken from nwb and will be corrected with inact_iv_stim_start_correction."
            ),
            units="ms",
        )
        inact_iv_stim_end: int | None = Field(
            title="Inactivation stimulus end time for IV computation",
            default=None,
            description=(
                "Inactivation stimulus end timing for IV computation. "
                "If None, this value will be taken from nwb and will be corrected with inact_iv_stim_end_correction."
            ),
            units="ms",
        )
        inact_tc_stim_start: int | None = Field(
            title="Inactivation stimulus start time for time constant computation",
            default=None,
            description=(
                "Inactivation stimulus start timing for time constant computation. "
                "If None, this value will be taken from nwb and will be corrected with inact_tc_stim_start_correction."
            ),
            units="ms",
        )
        inact_tc_stim_end: int | None = Field(
            title="Inactivation stimulus end time for time constant computation",
            default=None,
            description=(
                "Inactivation stimulus end timing for time constant computation. "
                "If None, this value will be taken from nwb and will be corrected with inact_tc_stim_end_correction."
            ),
            units="ms",
        )

        # trace loading customisation: stimulus timings corrections
        act_stim_start_correction: int = Field(
            title="Correction to apply to activation stimulus start time taken from source file, in ms.",
            default=0,
            description=(
                "Correction to add to the timing taken from nwb file for activation stimulus start."
            ),
            units="ms",
        )
        act_stim_end_correction: int = Field(
            title="Correction to apply to activation stimulus end time taken from source file, in ms.",
            default=-1,
            description=(
                "Correction to add to the timing taken from nwb file for activation stimulus end."
            ),
            units="ms",
        )
        inact_iv_stim_start_correction: int = Field(
            title="Correction to apply to inactivation stimulus start time for IV computation taken from source file, in ms.",
            default=5,
            description=(
                "Correction to add to the timing taken from nwb file for inactivation stimulus start for IV computation."
            ),
            units="ms",
        )
        inact_iv_stim_end_correction: int = Field(
            title="Correction to apply to inactivation stimulus end time for IV computation taken from source file, in ms.",
            default=-1,
            description=(
                "Correction to add to the timing taken from nwb file for inactivation stimulus end for IV computation."
            ),
            units="ms",
        )
        inact_tc_stim_start_correction: int = Field(
            title="Correction to apply to inactivation stimulus start time for time constant computation taken from source file, in ms.",
            default=0,
            description=(
                "Correction to add to the timing taken from nwb file for inactivation stimulus start for time constant computation."
            ),
            units="ms",
        )
        inact_tc_stim_end_correction: int = Field(
            title="Correction to apply to inactivation stimulus end time for time constant computation taken from source file, in ms.",
            default=-1,
            description=(
                "Correction to add to the timing taken from nwb file for inactivation stimulus end for time constant computation."
            ),
            units="ms",
        )

    initialize: Initialize
    equations: Equations
    expert: Expert

    def as_dict():
        """Returns the form as a dict to pass it down as input to the task laucnher."""
        NotImplemented()


class IonChannelFitting(IonChannelFittingForm, SingleCoordinateMixin):
    def run(self, db_client: entitysdk.client.Client = None) -> str:  # returns the id of the generated ion channel model
        """Download traces from entitycore and use them to build an ion channel, then register it."""
        try:
            # call task launcher.
            # download traces asset and metadata given id. Get ljp from metadata
            # -> use self.coordinate_output_root as output dirrectory

            # run ion_channel_builder main function to create new mod file

            # compile output mod file

            # run ion_channel_builder mod file runner to produce plots

            # register the mod file and figures to the platform


            # _ = run_ion_channel_builder(
            #     trace_ids=self.initialize.trace_ids,
            #     entity_client=db_client,
            #     minf_eq=self.initialize.minf_eq,
            #     mtau_eq=self.initialize.mtau_eq,
            #     hinf_eq=self.initialize.hinf_eq,
            #     htau_eq=self.initialize.htau_eq,
            #     act_exclude_voltages_above=self.initialize.act_exclude_voltages_above,
            #     act_exclude_voltages_below=self.initialize.act_exclude_voltages_below,
            #     inact_exclude_voltages_above=self.initialize.inact_exclude_voltages_above,
            #     inact_exclude_voltages_below=self.initialize.inact_exclude_voltages_below,
            #     act_stim_start=self.initialize.act_stim_start,
            #     act_stim_end=self.initialize.act_stim_end,
            #     inact_iv_stim_start=self.initialize.inact_iv_stim_start,
            #     inact_iv_stim_end=self.initialize.inact_iv_stim_end,
            #     inact_tc_stim_start=self.initialize.inact_tc_stim_start,
            #     inact_tc_stim_end=self.initialize.inact_tc_stim_end,
            #     act_stim_start_correction=self.initialize.act_stim_start_correction,
            #     act_stim_end_correction=self.initialize.act_stim_end_correction,
            #     inact_iv_stim_start_correction=self.initialize.inact_iv_stim_start_correction,
            #     inact_iv_stim_end_correction=self.initialize.inact_iv_stim_end_correction,
            #     inact_tc_stim_start_correction=self.initialize.inact_tc_stim_start_correction,
            #     inact_tc_stim_end_correction=self.initialize.inact_tc_stim_end_correction,
            #     suffix=self.initialize.suffix,
            #     ion=self.initialize.ion,
            #     m_power=self.initialize.m_power,
            #     h_power=self.initialize.h_power,
            # )
            pass
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}") from e
