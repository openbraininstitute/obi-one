"""eFEL feature Pydantic model with per-feature tunable parameters.

A single generic :class:`EFeature` class represents any eFEL feature. The
``efel_name`` field identifies which eFEL feature is being extracted, and
``category`` groups it for the UI's "Add feature" modal (matching the 4
categories from the eFEL documentation).

The :data:`EFEATURE_REGISTRY` maps every eFEL feature name to the
:class:`EFeature` class. Each concrete ``Protocol`` subclass instantiates
features from this registry with the correct ``efel_name`` and ``category``.

Categories (from https://efel.readthedocs.io/en/latest/eFeatures.html):
  - Spike event: firing rate, timing, ISIs, adaptation, burst metrics
  - Spike shape: AP morphology, AHP, ADP, rise/fall rates
  - Subthreshold: voltage base, sag, input resistance, time constants
  - Python efeature: ISI-derived and other Python-implemented features
"""

from typing import ClassVar

from pydantic import Field, PositiveFloat

from obi_one.core.base import OBIBaseModel
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units

# Forward declaration; populated at the end of the module.
EFEATURE_REGISTRY: dict[str, type["EFeature"]] = {}


class EFeature(OBIBaseModel):
    """Generic eFEL feature with per-feature tunable parameters.

    Each instance carries:
    - ``efel_name``: the eFEL feature key (e.g. ``"mean_frequency"``)
    - ``category``: UI grouping (one of the 4 eFEL doc categories)
    - ``extract``: on/off switch for inclusion in extraction
    - ``weight``, ``tolerance``: fitness function parameters
    - Per-feature eFEL setting overrides (threshold, stim window, custom)

    The three always-present eFEL settings (``Threshold``,
    ``strict_stiminterval``, ``interp_step``) default to eFEL's own defaults
    and are always emitted in ``efel_settings_override()``. Two additional
    optional fields (``stim_start``, ``stim_end``) are emitted only when set.
    Further eFEL settings can be added via ``custom_efel_settings``.
    """

    efel_name: str = Field(
        default="",
        title="eFEL feature name",
        description="The eFEL feature key (e.g. 'mean_frequency', 'AP_amplitude').",
    )
    category: str = Field(
        default="Spike event",
        title="Category",
        description=(
            "Feature category for UI grouping. One of: 'Spike event',"
            " 'Spike shape', 'Subthreshold'."
        ),
    )

    efel_doc_url: ClassVar[str] = "https://efel.readthedocs.io/en/latest/eFeatures.html"

    json_schema_extra_additions: ClassVar[dict] = {
        "efel_doc_url": "https://efel.readthedocs.io/en/latest/eFeatures.html",
    }

    extract: bool = Field(
        default=False,
        title="Extract",
        description="Whether to include this efeature in the bluepyefe extraction.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    weight: PositiveFloat = Field(
        default=1.0,
        title="Weight",
        description=(
            "Relative weight of this efeature in the fitness function (passed to"
            " ``bluepyefe``'s Target ``weight`` parameter)."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    tolerance: PositiveFloat = Field(
        default=20.0,
        title="Tolerance",
        description=(
            "Amplitude tolerance (in % of rheobase, or pA when"
            " ``extract_absolute_amplitudes=True``) used to match recordings to"
            " the requested target amplitude."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    efeature_name: str = Field(
        default="",
        title="Feature name",
        description=(
            "Custom name for this target (bluepyefe ``efeature_name``). Lets the"
            " same eFEL feature be extracted under a distinct label, e.g."
            " ``Spikecount_phase1``. Leave empty to use the eFEL feature name."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    # ------------------------------------------------------------------
    # Always-present eFEL settings with eFEL defaults pre-filled
    # ------------------------------------------------------------------
    threshold: float = Field(
        default=-20.0,
        title="Threshold",
        description="eFEL ``Threshold``: voltage above which a spike is detected (mV).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLIVOLTS,
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
    interp_step: PositiveFloat = Field(
        default=0.025,
        title="Interpolation step",
        description=(
            "eFEL ``interp_step``: time step the trace is resampled to before extraction (ms)."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    # ------------------------------------------------------------------
    # Optional per-feature stimulus window overrides
    # ------------------------------------------------------------------
    stim_start: float = Field(
        default=0.0,
        title="Stim start",
        description=(
            "eFEL ``stim_start``: stimulus onset time for this feature (ms)."
            " Overrides the protocol-level value. Set to 0 to use the"
            " protocol's detected onset."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    stim_end: float = Field(
        default=0.0,
        title="Stim end",
        description=(
            "eFEL ``stim_end``: stimulus end time for this feature (ms)."
            " Overrides the protocol-level value. Set to 0 to use the"
            " protocol's detected end."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    # ------------------------------------------------------------------
    # Additional eFEL settings (picker)
    # ------------------------------------------------------------------
    custom_efel_settings: dict[str, float | bool] = Field(
        default_factory=dict,
        title="Custom eFEL settings",
        description=(
            "Additional eFEL settings beyond the always-present Threshold,"
            " strict_stiminterval, and interp_step. Keys are eFEL setting names."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY},
    )

    def efel_settings_override(self) -> dict:
        """Build the per-feature ``efel_settings`` overrides for this target row.

        The 3 always-present settings are always emitted. ``stim_start`` and
        ``stim_end`` are emitted only when non-zero. Additional settings from
        ``custom_efel_settings`` are merged on top. Each setting overrides the
        protocol- and global-level eFEL setting for this feature.
        """
        overrides: dict[str, float | bool] = {
            "Threshold": self.threshold,
            "strict_stiminterval": self.strict_stiminterval,
            "interp_step": self.interp_step,
        }
        if self.stim_start:
            overrides["stim_start"] = self.stim_start
        if self.stim_end:
            overrides["stim_end"] = self.stim_end
        if self.custom_efel_settings:
            overrides.update(self.custom_efel_settings)
        return overrides


# ---------------------------------------------------------------------------
# Feature categories — from eFEL documentation
# https://efel.readthedocs.io/en/latest/eFeatures.html
#
# The docs group features under 4 section headings:
#   1. "Spike event features" (SpikeEvent) — firing rate, timing, ISIs, bursts
#   2. "Spike shape features" (SpikeShape) — AP morphology, AHP, ADP
#   3. "Subthreshold features" (Subthreshold) — passive properties, sag, Rin
#   4. "Extracellular features" — waveform-based (not in get_feature_names())
#
# Since extracellular features operate on spike waveforms rather than voltage
# traces, they are not part of efel.get_feature_names() and do not appear
# in EFEATURE_REGISTRY. The 3 categories below cover all intracellular features.
# ---------------------------------------------------------------------------

_SPIKE_EVENT_FEATURES: frozenset[str] = frozenset(
    {
        "Spikecount",
        "Spikecount_stimint",
        "spike_count",
        "spike_count_stimint",
        "peak_indices",
        "peak_time",
        "time_to_first_spike",
        "time_to_second_spike",
        "time_to_last_spike",
        "inv_time_to_first_spike",
        "all_ISI_values",
        "doublet_ISI",
        "mean_frequency",
        "adaptation_index",
        "adaptation_index2",
        "burst_number",
        "burst_mean_freq",
        "burst_ISI_indices",
        "burst_begin_indices",
        "burst_end_indices",
        "interburst_voltage",
        "strict_interburst_voltage",
        "interburst_duration",
        "interburst_min_indices",
        "interburst_min_values",
        "time_to_interburst_min",
        "interburst_15percent_indices",
        "interburst_15percent_values",
        "interburst_20percent_indices",
        "interburst_20percent_values",
        "interburst_25percent_indices",
        "interburst_25percent_values",
        "interburst_30percent_indices",
        "interburst_30percent_values",
        "interburst_40percent_indices",
        "interburst_40percent_values",
        "interburst_60percent_indices",
        "interburst_60percent_values",
        "strict_burst_number",
        "strict_burst_mean_freq",
        "number_initial_spikes",
        "amp_drop_first_last",
        "amp_drop_first_second",
        "amp_drop_second_last",
        "max_amp_difference",
        "depol_block",
        "depol_block_bool",
        "spikes_per_burst",
        "spikes_per_burst_diff",
        "spikes_in_burst1_burst2_diff",
        "spikes_in_burst1_burstlast_diff",
        "is_not_stuck",
        "trace_check",
    }
)

_SPIKE_SHAPE_FEATURES: frozenset[str] = frozenset(
    {
        "peak_voltage",
        "AP_height",
        "AP_amplitude",
        "AP_amplitude_change",
        "AP_amplitude_diff",
        "AP_amplitude_from_voltagebase",
        "mean_AP_amplitude",
        "AP1_amp",
        "AP2_amp",
        "APlast_amp",
        "AP1_peak",
        "AP2_peak",
        "AP2_AP1_diff",
        "AP2_AP1_peak_diff",
        "AP2_AP1_begin_width_diff",
        "AP_duration",
        "AP_duration_change",
        "AP_duration_half_width",
        "AP_duration_half_width_change",
        "AP_width",
        "AP_width_between_threshold",
        "AP1_width",
        "AP2_width",
        "APlast_width",
        "spike_half_width",
        "spike_width2",
        "AP_begin_voltage",
        "AP_begin_width",
        "AP_begin_indices",
        "AP_begin_time",
        "AP1_begin_voltage",
        "AP1_begin_width",
        "AP2_begin_voltage",
        "AP2_begin_width",
        "AP_end_indices",
        "AP_rise_time",
        "AP_rise_rate",
        "AP_rise_rate_change",
        "AP_rise_indices",
        "AP_fall_time",
        "AP_fall_rate",
        "AP_fall_rate_change",
        "AP_fall_indices",
        "AP_peak_upstroke",
        "AP_peak_downstroke",
        "AP_phaseslope",
        "phaseslope_max",
        "AHP_depth",
        "AHP_depth_abs",
        "AHP_depth_abs_slow",
        "AHP_depth_diff",
        "AHP_depth_from_peak",
        "AHP_depth_slow",
        "AHP_slow_time",
        "AHP_time_from_peak",
        "AHP1_depth_from_peak",
        "AHP2_depth_from_peak",
        "fast_AHP",
        "fast_AHP_change",
        "min_AHP_indices",
        "min_AHP_values",
        "min_between_peaks_indices",
        "min_between_peaks_values",
        "min_voltage_between_spikes",
        "ADP_peak_amplitude",
        "ADP_peak_indices",
        "ADP_peak_values",
    }
)

_SUBTHRESHOLD_FEATURES: frozenset[str] = frozenset(
    {
        "voltage_base",
        "voltage_after_stim",
        "voltage_deflection",
        "voltage_deflection_begin",
        "voltage_deflection_vb_ssse",
        "steady_state_voltage",
        "steady_state_voltage_stimend",
        "steady_state_hyper",
        "steady_state_current_stimend",
        "depolarized_base",
        "minimum_voltage",
        "maximum_voltage",
        "maximum_voltage_from_voltagebase",
        "ohmic_input_resistance",
        "ohmic_input_resistance_vb_ssse",
        "sag_amplitude",
        "sag_ratio1",
        "sag_ratio2",
        "sag_time_constant",
        "decay_time_constant_after_stim",
        "multiple_decay_time_constant_after_stim",
        "time_constant",
        "impedance",
        "activation_time_constant",
        "deactivation_time_constant",
        "inactivation_time_constant",
    }
)

# Everything else (ISI Python efeatures, burst post-processing, etc.)
# falls into "Python efeature" — the catch-all 4th category from the docs.


def get_feature_category(efel_name: str) -> str:
    """Return the eFEL documentation category for a feature name.

    Categories match the eFEL docs (https://efel.readthedocs.io/en/latest/eFeatures.html):
      - "Spike event" — firing rate, timing, ISIs, bursts, adaptation
      - "Spike shape" — AP morphology, AHP, ADP, rise/fall
      - "Subthreshold" — voltage base, sag, input resistance, time constants
    """
    if efel_name in _SPIKE_EVENT_FEATURES:
        return "Spike event"
    if efel_name in _SPIKE_SHAPE_FEATURES:
        return "Spike shape"
    if efel_name in _SUBTHRESHOLD_FEATURES:
        return "Subthreshold"
    # ISI Python efeatures and burst post-processing features are listed
    # under "Spike event features" in the eFEL docs.
    return "Spike event"


# ---------------------------------------------------------------------------
# Auto-populate EFEATURE_REGISTRY from all eFEL features
# ---------------------------------------------------------------------------

try:
    import efel as _efel

    for _name in _efel.get_feature_names():
        EFEATURE_REGISTRY[_name] = EFeature
except ImportError:
    # eFEL not installed — registry will be empty. Features can still be
    # instantiated manually via EFeature(efel_name="...").
    pass
