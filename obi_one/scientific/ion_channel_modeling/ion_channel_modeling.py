"""Ion channel modeling form."""

from typing import ClassVar

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.form import Form


class IonChannelModelingForm(Form):
    """Form for modeling an ion channel model from a set of ion channel traces."""

    single_coord_class_name: ClassVar[str] = "IonChannelModeling"
    name: ClassVar[str] = "IonChannelModeling Metrics"
    description: ClassVar[str] = "Models ion channel model from a set of ion channel traces."

    class Initialize(Block):
        # traces
        trace_ids: list[str] = Field(description="IDs of the traces of interest.")

        # equations
        minf_eq: str = Field(
            default="sig_fit_minf",
            description=(
                "Name of the equation to use to fit minf. "
                "Should correspond to a key of ion_channel_builder.create_model.model_equations_mapping"
            )
        )
        mtau_eq: str = Field(
            default="sig_fit_mtau",
            description=(
                "Name of the equation to use to fit mtau. "
                "Should correspond to a key of ion_channel_builder.create_model.model_equations_mapping"
            )
        )
        hinf_eq: str = Field(
            default="sig_fit_hinf",
            description=(
                "Name of the equation to use to fit hinf. "
                "Should correspond to a key of ion_channel_builder.create_model.model_equations_mapping"
            )
        )
        htau_eq: str = Field(
            default="sig_fit_htau",
            description=(
                "Name of the equation to use to fit htau. "
                "Should correspond to a key of ion_channel_builder.create_model.model_equations_mapping"
            )
        )

        # trace loading customisation: voltage exclusion
        act_voltages_to_exclude: list[int] = Field(
            default=[],
            description=(
                "Input voltages to exclude when building traces used for activation computation"
            ),
            units="mV",
        )
        inact_voltages_to_exclude: list[int] = Field(
            default=[],
            description=(
                "Input voltages to exclude when building traces used for inactivation computation"
            ),
            units="mV",
        )

        # trace loading customisation: stimulus timings
        act_stim_start: int|None = Field(
            default=None,
            description=(
                "Activation stimulus start timing. "
                "If None, this value will be taken from nwb and will be corrected with act_stim_start_correction."
            ),
            units="ms"
        )
        act_stim_end: int|None = Field(
            default=None,
            description=(
                "Activation stimulus end timing. "
                "If None, this value will be taken from nwb and will be corrected with act_stim_end_correction."
            ),
            units="ms"
        )
        inact_iv_stim_start: int|None = Field(
            default=None,
            description=(
                "Inactivation stimulus start timing for IV computation. "
                "If None, this value will be taken from nwb and will be corrected with inact_iv_stim_start_correction."
            ),
            units="ms"
        )
        inact_iv_stim_end: int|None = Field(
            default=None,
            description=(
                "Inactivation stimulus end timing for IV computation. "
                "If None, this value will be taken from nwb and will be corrected with inact_iv_stim_end_correction."
            ),
            units="ms"
        )
        inact_tc_stim_start: int|None = Field(
            default=None,
            description=(
                "Inactivation stimulus start timing for time constant computation. "
                "If None, this value will be taken from nwb and will be corrected with inact_tc_stim_start_correction."
            ),
            units="ms"
        )
        inact_tc_stim_end: int|None = Field(
            default=None,
            description=(
                "Inactivation stimulus end timing for time constant computation. "
                "If None, this value will be taken from nwb and will be corrected with inact_tc_stim_end_correction."
            ),
            units="ms"
        )

        # trace loading customisation: stimulus timings corrections
        act_stim_start_correction: int = Field(
            default=0,
            description=(
                "Correction to add to the timing taken from nwb file for activation stimulus start."
            ),
            units="ms"
        )
        act_stim_end_correction: int = Field(
            default=-1,
            description=(
                "Correction to add to the timing taken from nwb file for activation stimulus end."
            ),
            units="ms"
        )
        inact_iv_stim_start_correction: int = Field(
            default=5,
            description=(
                "Correction to add to the timing taken from nwb file for inactivation stimulus start for IV computation."
            ),
            units="ms"
        )
        inact_iv_stim_end_correction: int = Field(
            default=-1,
            description=(
                "Correction to add to the timing taken from nwb file for inactivation stimulus end for IV computation."
            ),
            units="ms"
        )
        inact_tc_stim_start_correction: int = Field(
            default=0,
            description=(
                "Correction to add to the timing taken from nwb file for inactivation stimulus start for time constant computation."
            ),
            units="ms"
        )
        inact_tc_stim_end_correction: int = Field(
            default=-1,
            description=(
                "Correction to add to the timing taken from nwb file for inactivation stimulus end for time constant computation."
            ),
            units="ms"
        )

        # mod file creation
        suffix: str = Field(
            description=(
                "SUFFIX to use in the mod file. Will also be used for the mod file name."
            )
        )
        ion: str = Field(
            default="k",
            description=(
                "Ion to use in the mod file."
            )
        )
        m_power: int = Field(
            default=1,
            description=(
                "Raise m to this power in the BREAKPOINT equation."
            )
        )
        h_power: int = Field(
            default=1,
            description=(
                "Raise h to this power in the BREAKPOINT equation."
            )
        )

    initialize: Initialize
