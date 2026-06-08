"""Global eFEL + BluePyEModel/bluepyefe settings for the extraction stage.

This block exposes the extraction-wide knobs that BluePyEModel's
``extract_save_features_protocols`` forwards to ``bluepyefe.extract`` and eFEL:

* the global eFEL settings (the ``efel_settings`` dict), assembled by
  :meth:`Settings.efel_to_dict`;
* the bluepyefe / ``EModelPipelineSettings`` extraction-flow knobs that the
  BluePyEModel extraction entry point actually plumbs through.

Per-protocol and per-feature overrides of the eFEL settings live on the
``Protocol`` and ``EFeature`` classes respectively and take priority over the
values set here (global -> protocol -> feature). Rheobase configuration lives
in its own per-strategy ``RheobaseStrategy`` block union.

Only the eFEL settings that influence at least one feature in this stage's
feature catalogue (directly or as a dependency) are exposed. eFEL settings that
solely drive features the catalogue cannot extract -- ``current_base_*``,
``rise_*_perc``, ``sahp_start``, ``burst_factor``, ``initburst_*``,
``impedance_max_freq``, ``AP_phaseslope_range``, ``inactivation_tc_end_skip``,
``min_spike_height`` -- are intentionally omitted, as are the bluepyefe args
``extract_save_features_protocols`` does not forward (``protocol_mode``,
``low_memory_mode``, ``extract_per_cell``) and the ``extraction_reader``.
"""

from typing import Literal

from pydantic import Field, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units


class Settings(Block):
    """Global eFEL and ``bluepyefe.extract`` settings for the extraction stage."""

    # ------------------------------------------------------------------
    # eFEL settings -- spike & AP-shape detection
    # ------------------------------------------------------------------
    threshold: float | list[float] = Field(
        default=-20.0,
        title="Spike threshold",
        description="eFEL ``Threshold``: voltage above which a spike is detected.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLIVOLTS,
        },
    )
    derivative_threshold: float | list[float] = Field(
        default=10.0,
        title="Derivative threshold",
        description=(
            "eFEL ``DerivativeThreshold``: dV/dt (mV/ms) above which the spike"
            " onset is detected (AP_begin_* features)."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    down_derivative_threshold: float | list[float] = Field(
        default=-12.0,
        title="Down derivative threshold",
        description=(
            "eFEL ``DownDerivativeThreshold``: dV/dt (mV/ms) used to detect the AP end"
            " (feeds AP_duration_half_width)."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    derivative_window: int | list[int] = Field(
        default=3,
        title="Derivative window",
        description=(
            "eFEL ``DerivativeWindow``: number of samples used to compute the voltage derivative."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )

    # ------------------------------------------------------------------
    # eFEL settings -- interpolation & stimulus interval
    # ------------------------------------------------------------------
    interp_step: PositiveFloat | list[PositiveFloat] = Field(
        default=0.025,
        title="Interpolation step",
        description="eFEL ``interp_step``: time step the trace is resampled to before extraction.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    strict_stiminterval: bool = Field(
        default=True,
        title="Strict stim interval",
        description=(
            "eFEL ``strict_stiminterval``: only count spikes strictly within"
            " [stim_start, stim_end]."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    # ------------------------------------------------------------------
    # eFEL settings -- spike skipping / ISI / bursting
    # ------------------------------------------------------------------
    spike_skipf: float | list[float] = Field(
        default=0.1,
        title="Spike skip fraction",
        description=(
            "eFEL ``spike_skipf``: fraction of leading spikes skipped by adaptation_index."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    max_spike_skip: int | list[int] = Field(
        default=2,
        title="Max spikes skipped",
        description=(
            "eFEL ``max_spike_skip``: absolute cap on the leading spikes skipped by"
            " adaptation_index."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    ignore_first_isi: bool = Field(
        default=True,
        title="Ignore first ISI",
        description=(
            "eFEL ``ignore_first_ISI``: exclude the first inter-spike interval from ISI"
            " features (ISI_CV, ISI_log_slope, irregularity_index)."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    strict_burst_factor: float | list[float] = Field(
        default=2.0,
        title="Strict burst factor",
        description=(
            "eFEL ``strict_burst_factor``: ISI ratio used by strict_burst_number /"
            " strict_burst_mean_freq to delimit bursts."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    initial_perc: float | list[float] = Field(
        default=0.1,
        title="Initial %",
        description=(
            "eFEL ``initial_perc``: fraction of the stimulus counted as 'initial' by"
            " number_initial_spikes."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    # ------------------------------------------------------------------
    # eFEL settings -- voltage base & misc
    # ------------------------------------------------------------------
    voltage_base_start_perc: float | list[float] = Field(
        default=0.9,
        title="Voltage base start %",
        description=(
            "eFEL ``voltage_base_start_perc``: start of the pre-stimulus window (fraction)"
            " for voltage_base."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    voltage_base_end_perc: float | list[float] = Field(
        default=1.0,
        title="Voltage base end %",
        description=(
            "eFEL ``voltage_base_end_perc``: end of the pre-stimulus window (fraction)"
            " for voltage_base."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    voltage_base_mode: Literal["mean", "median"] = Field(
        default="mean",
        title="Voltage base mode",
        description=(
            "eFEL ``voltage_base_mode``: aggregation used for voltage_base over its window."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    depol_block_min_duration: float | list[float] = Field(
        default=50.0,
        title="Depol. block min duration",
        description=(
            "eFEL ``depol_block_min_duration``: minimum plateau duration (ms) for"
            " depol_block_bool to flag a depolarisation block."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    precision_threshold: float | list[float] = Field(
        default=1e-10,
        title="Precision threshold",
        description=(
            "eFEL ``precision_threshold``: numerical tolerance used by voltage_base"
            " (and current-base) windowing."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    # ------------------------------------------------------------------
    # bluepyefe / BluePyEModel extraction-flow settings
    # ------------------------------------------------------------------
    plot_extraction: bool = Field(
        default=True,
        title="Plot extraction",
        description="Whether to render extraction figures alongside the JSON output.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    default_std_value: PositiveFloat | list[PositiveFloat] = Field(
        default=0.01,
        title="Default std value",
        description="Replaces zero standard deviations during feature extraction.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    threshold_nvalue_save: int | list[int] = Field(
        default=1,
        title="Min values to save feature",
        description=(
            "bluepyefe ``threshold_nvalue_save``: minimum number of recordings a feature"
            " must be measured on to be kept in the output."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    pickle_cells: bool = Field(
        default=False,
        title="Pickle cells",
        description=(
            "bluepyefe ``pickle_cells``: also dump the BluePyEfe ``Cell`` objects as pickles."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    bound_max_std: bool = Field(
        default=False,
        title="Bound max std",
        description=(
            "If set, cap each feature's standard deviation at its mean value after extraction."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    interpolate_rmp: bool = Field(
        default=False,
        title="Interpolate RMP",
        description=(
            "If set, estimate the resting membrane potential as ``V_hold - R_in * I_hold``"
            " when no zero-holding recording is available."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    threshold_efeature_std: float | None = Field(
        default=None,
        title="Threshold efeature std",
        description=(
            "If set, floor each feature's standard deviation at"
            " ``abs(threshold_efeature_std * mean)``. Leave empty to disable."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    minimum_protocol_delay: float | list[float] = Field(
        default=0.0,
        title="Minimum protocol delay",
        description="Protocols with a shorter initial delay are padded to this value (ms).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    name_rin_protocol: str | None = Field(
        default=None,
        title="Rin protocol name",
        description=(
            "Protocol used to compute input resistance (e.g. ``IV_-20``). Leave"
            " ``None`` to skip; set when the requested protocol is present in the"
            " recordings being extracted."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    name_rmp_protocol: str | None = Field(
        default=None,
        title="RMP protocol name",
        description=(
            "Protocol used to compute resting membrane potential (e.g. ``IV_0``)."
            " Leave ``None`` to skip; set when the requested protocol is present"
            " in the recordings being extracted."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    def efel_to_dict(self) -> dict:
        """Assemble the global ``efel_settings`` dict in eFEL's native key names."""
        return {
            "Threshold": self.threshold,
            "DerivativeThreshold": self.derivative_threshold,
            "DownDerivativeThreshold": self.down_derivative_threshold,
            "DerivativeWindow": self.derivative_window,
            "interp_step": self.interp_step,
            "strict_stiminterval": self.strict_stiminterval,
            "spike_skipf": self.spike_skipf,
            "max_spike_skip": self.max_spike_skip,
            "ignore_first_ISI": self.ignore_first_isi,
            "strict_burst_factor": self.strict_burst_factor,
            "initial_perc": self.initial_perc,
            "voltage_base_start_perc": self.voltage_base_start_perc,
            "voltage_base_end_perc": self.voltage_base_end_perc,
            "voltage_base_mode": self.voltage_base_mode,
            "depol_block_min_duration": self.depol_block_min_duration,
            "precision_threshold": self.precision_threshold,
        }
