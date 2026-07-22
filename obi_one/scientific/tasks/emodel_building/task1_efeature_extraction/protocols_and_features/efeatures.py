"""eFEL feature models and per-protocol feature sets for e-model optimisation.

One class per eFEL feature (https://efel.readthedocs.io/en/latest/eFeatures.html).
Per-protocol feature tuples at the bottom define which features are valid for
each protocol.
"""

import abc
from typing import Annotated, ClassVar

from pydantic import Discriminator, Field, PositiveFloat

from obi_one.core.base import OBIBaseModel
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units


class EFeature(OBIBaseModel):
    """Generic eFEL feature with per-feature tunable parameters.

    Each instance carries:
    - ``efel_name``: the eFEL feature key, fixed by the concrete class
    - ``extract``: on/off switch for inclusion in extraction
    - ``weight``, ``tolerance``: fitness function parameters
    - Per-feature eFEL setting overrides (threshold, stim window, custom)

    The three always-present eFEL settings (``Threshold``,
    ``strict_stiminterval``, ``interp_step``) default to eFEL's own defaults
    and are always emitted in ``efel_settings_override()``. Two additional
    optional fields (``stim_start``, ``stim_end``) are emitted only when set.
    Further eFEL settings can be added via ``custom_efel_settings``.
    """

    efel_name: ClassVar[str] = ""
    """The eFEL feature key, fixed by each concrete feature class."""
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

# =========================================================================
# Concrete feature classes and per-protocol unions.
# Everything below is generated; see the module docstring for the source.
# =========================================================================


class SpikeEventFeature(EFeature, abc.ABC):
    """eFEL spike-event features; groups its subclasses, adds no fields."""


class SpikeShapeFeature(EFeature, abc.ABC):
    """eFEL spike-shape features; groups its subclasses, adds no fields."""


class SubthresholdFeature(EFeature, abc.ABC):
    """eFEL subthreshold features; groups its subclasses, adds no fields."""

# -------------------------------------------------------------------------
# Spike event features
# -------------------------------------------------------------------------


class ISICVFeature(SpikeEventFeature):
    """eFEL ``ISI_CV``."""

    efel_name: ClassVar[str] = "ISI_CV"


class ISILogSlopeFeature(SpikeEventFeature):
    """eFEL ``ISI_log_slope``."""

    efel_name: ClassVar[str] = "ISI_log_slope"


class SpikecountFeature(SpikeEventFeature):
    """eFEL ``Spikecount``."""

    efel_name: ClassVar[str] = "Spikecount"


class AdaptationIndexFeature(SpikeEventFeature):
    """eFEL ``adaptation_index``."""

    efel_name: ClassVar[str] = "adaptation_index"


class DepolBlockBoolFeature(SpikeEventFeature):
    """eFEL ``depol_block_bool``."""

    efel_name: ClassVar[str] = "depol_block_bool"


class DoubletISIFeature(SpikeEventFeature):
    """eFEL ``doublet_ISI``."""

    efel_name: ClassVar[str] = "doublet_ISI"


class InvFirstISIFeature(SpikeEventFeature):
    """eFEL ``inv_first_ISI``."""

    efel_name: ClassVar[str] = "inv_first_ISI"


class InvLastISIFeature(SpikeEventFeature):
    """eFEL ``inv_last_ISI``."""

    efel_name: ClassVar[str] = "inv_last_ISI"


class InvSecondISIFeature(SpikeEventFeature):
    """eFEL ``inv_second_ISI``."""

    efel_name: ClassVar[str] = "inv_second_ISI"


class InvThirdISIFeature(SpikeEventFeature):
    """eFEL ``inv_third_ISI``."""

    efel_name: ClassVar[str] = "inv_third_ISI"


class InvTimeToFirstSpikeFeature(SpikeEventFeature):
    """eFEL ``inv_time_to_first_spike``."""

    efel_name: ClassVar[str] = "inv_time_to_first_spike"


class IrregularityIndexFeature(SpikeEventFeature):
    """eFEL ``irregularity_index``."""

    efel_name: ClassVar[str] = "irregularity_index"


class MeanFrequencyFeature(SpikeEventFeature):
    """eFEL ``mean_frequency``."""

    efel_name: ClassVar[str] = "mean_frequency"


class NumberInitialSpikesFeature(SpikeEventFeature):
    """eFEL ``number_initial_spikes``."""

    efel_name: ClassVar[str] = "number_initial_spikes"


class StrictBurstMeanFreqFeature(SpikeEventFeature):
    """eFEL ``strict_burst_mean_freq``."""

    efel_name: ClassVar[str] = "strict_burst_mean_freq"


class StrictBurstNumberFeature(SpikeEventFeature):
    """eFEL ``strict_burst_number``."""

    efel_name: ClassVar[str] = "strict_burst_number"


class TimeToFirstSpikeFeature(SpikeEventFeature):
    """eFEL ``time_to_first_spike``."""

    efel_name: ClassVar[str] = "time_to_first_spike"


class TimeToLastSpikeFeature(SpikeEventFeature):
    """eFEL ``time_to_last_spike``."""

    efel_name: ClassVar[str] = "time_to_last_spike"


class TimeToSecondSpikeFeature(SpikeEventFeature):
    """eFEL ``time_to_second_spike``."""

    efel_name: ClassVar[str] = "time_to_second_spike"


class InvFourthISIFeature(SpikeEventFeature):
    """eFEL ``inv_fourth_ISI``."""

    efel_name: ClassVar[str] = "inv_fourth_ISI"


class InvFifthISIFeature(SpikeEventFeature):
    """eFEL ``inv_fifth_ISI``."""

    efel_name: ClassVar[str] = "inv_fifth_ISI"


class ISISemilogSlopeFeature(SpikeEventFeature):
    """eFEL ``ISI_semilog_slope``."""

    efel_name: ClassVar[str] = "ISI_semilog_slope"


class ISILogSlopeSkipFeature(SpikeEventFeature):
    """eFEL ``ISI_log_slope_skip``."""

    efel_name: ClassVar[str] = "ISI_log_slope_skip"


class AdaptationIndex2Feature(SpikeEventFeature):
    """eFEL ``adaptation_index_2``."""

    efel_name: ClassVar[str] = "adaptation_index_2"


class BurstNumberFeature(SpikeEventFeature):
    """eFEL ``burst_number``."""

    efel_name: ClassVar[str] = "burst_number"


class SingleBurstRatioFeature(SpikeEventFeature):
    """eFEL ``single_burst_ratio``."""

    efel_name: ClassVar[str] = "single_burst_ratio"


class SpikeCountStimintFeature(SpikeEventFeature):
    """eFEL ``spike_count_stimint``."""

    efel_name: ClassVar[str] = "spike_count_stimint"


class SpikesPerBurstFeature(SpikeEventFeature):
    """eFEL ``spikes_per_burst``."""

    efel_name: ClassVar[str] = "spikes_per_burst"


class BurstMeanFreqFeature(SpikeEventFeature):
    """eFEL ``burst_mean_freq``."""

    efel_name: ClassVar[str] = "burst_mean_freq"


class InterburstVoltageFeature(SpikeEventFeature):
    """eFEL ``strict_interburst_voltage``."""

    efel_name: ClassVar[str] = "strict_interburst_voltage"


class InterburstMinValuesFeature(SpikeEventFeature):
    """eFEL ``interburst_min_values``."""

    efel_name: ClassVar[str] = "interburst_min_values"


class PeakTimeFeature(SpikeEventFeature):
    """eFEL ``peak_time``."""

    efel_name: ClassVar[str] = "peak_time"


class ISIValuesFeature(SpikeEventFeature):
    """eFEL ``ISI_values``."""

    efel_name: ClassVar[str] = "ISI_values"


class AllISIValuesFeature(SpikeEventFeature):
    """eFEL ``all_ISI_values``."""

    efel_name: ClassVar[str] = "all_ISI_values"


class InvISIValuesFeature(SpikeEventFeature):
    """eFEL ``inv_ISI_values``."""

    efel_name: ClassVar[str] = "inv_ISI_values"


class InterburstDurationFeature(SpikeEventFeature):
    """eFEL ``interburst_duration``."""

    efel_name: ClassVar[str] = "interburst_duration"


class TimeToInterburstMinFeature(SpikeEventFeature):
    """eFEL ``time_to_interburst_min``."""

    efel_name: ClassVar[str] = "time_to_interburst_min"


class TimeToPostburstSlowAhpFeature(SpikeEventFeature):
    """eFEL ``time_to_postburst_slow_ahp``."""

    efel_name: ClassVar[str] = "time_to_postburst_slow_ahp"


class PostburstMinValuesFeature(SpikeEventFeature):
    """eFEL ``postburst_min_values``."""

    efel_name: ClassVar[str] = "postburst_min_values"


class PostburstSlowAhpValuesFeature(SpikeEventFeature):
    """eFEL ``postburst_slow_ahp_values``."""

    efel_name: ClassVar[str] = "postburst_slow_ahp_values"


class PostburstFastAhpValuesFeature(SpikeEventFeature):
    """eFEL ``postburst_fast_ahp_values``."""

    efel_name: ClassVar[str] = "postburst_fast_ahp_values"


class PostburstAdpPeakValuesFeature(SpikeEventFeature):
    """eFEL ``postburst_adp_peak_values``."""

    efel_name: ClassVar[str] = "postburst_adp_peak_values"


class TimeToPostburstFastAhpFeature(SpikeEventFeature):
    """eFEL ``time_to_postburst_fast_ahp``."""

    efel_name: ClassVar[str] = "time_to_postburst_fast_ahp"


class TimeToPostburstAdpPeakFeature(SpikeEventFeature):
    """eFEL ``time_to_postburst_adp_peak``."""

    efel_name: ClassVar[str] = "time_to_postburst_adp_peak"


class SpikesPerBurstDiffFeature(SpikeEventFeature):
    """eFEL ``spikes_per_burst_diff``."""

    efel_name: ClassVar[str] = "spikes_per_burst_diff"


class SpikesInBurst1Burst2DiffFeature(SpikeEventFeature):
    """eFEL ``spikes_in_burst1_burst2_diff``."""

    efel_name: ClassVar[str] = "spikes_in_burst1_burst2_diff"


class SpikesInBurst1BurstlastDiffFeature(SpikeEventFeature):
    """eFEL ``spikes_in_burst1_burstlast_diff``."""

    efel_name: ClassVar[str] = "spikes_in_burst1_burstlast_diff"


class Interburst15PercentValuesFeature(SpikeEventFeature):
    """eFEL ``interburst_15percent_values``."""

    efel_name: ClassVar[str] = "interburst_15percent_values"


class Interburst20PercentValuesFeature(SpikeEventFeature):
    """eFEL ``interburst_20percent_values``."""

    efel_name: ClassVar[str] = "interburst_20percent_values"


class Interburst25PercentValuesFeature(SpikeEventFeature):
    """eFEL ``interburst_25percent_values``."""

    efel_name: ClassVar[str] = "interburst_25percent_values"


class Interburst30PercentValuesFeature(SpikeEventFeature):
    """eFEL ``interburst_30percent_values``."""

    efel_name: ClassVar[str] = "interburst_30percent_values"


class Interburst40PercentValuesFeature(SpikeEventFeature):
    """eFEL ``interburst_40percent_values``."""

    efel_name: ClassVar[str] = "interburst_40percent_values"


class Interburst60PercentValuesFeature(SpikeEventFeature):
    """eFEL ``interburst_60percent_values``."""

    efel_name: ClassVar[str] = "interburst_60percent_values"


class Interburst15PercentVoltageFeature(SpikeEventFeature):
    """eFEL ``interburst_voltage`` (ISI Python efeature variant)."""

    efel_name: ClassVar[str] = "interburst_voltage"

# -------------------------------------------------------------------------
# Spike shape features
# -------------------------------------------------------------------------


class AHPDepthFeature(SpikeShapeFeature):
    """eFEL ``AHP_depth``."""

    efel_name: ClassVar[str] = "AHP_depth"


class AHPTimeFromPeakFeature(SpikeShapeFeature):
    """eFEL ``AHP_time_from_peak``."""

    efel_name: ClassVar[str] = "AHP_time_from_peak"


class AP1AmpFeature(SpikeShapeFeature):
    """eFEL ``AP1_amp``."""

    efel_name: ClassVar[str] = "AP1_amp"


class APAmplitudeFeature(SpikeShapeFeature):
    """eFEL ``AP_amplitude``."""

    efel_name: ClassVar[str] = "AP_amplitude"


class APBeginVoltageFeature(SpikeShapeFeature):
    """eFEL ``AP_begin_voltage``."""

    efel_name: ClassVar[str] = "AP_begin_voltage"


class APBeginWidthFeature(SpikeShapeFeature):
    """eFEL ``AP_begin_width``."""

    efel_name: ClassVar[str] = "AP_begin_width"


class APDurationHalfWidthFeature(SpikeShapeFeature):
    """eFEL ``AP_duration_half_width``."""

    efel_name: ClassVar[str] = "AP_duration_half_width"


class AP2AmpFeature(SpikeShapeFeature):
    """eFEL ``AP2_amp``."""

    efel_name: ClassVar[str] = "AP2_amp"


class APlastAmpFeature(SpikeShapeFeature):
    """eFEL ``APlast_amp``."""

    efel_name: ClassVar[str] = "APlast_amp"


class MeanAPAmplitudeFeature(SpikeShapeFeature):
    """eFEL ``mean_AP_amplitude``."""

    efel_name: ClassVar[str] = "mean_AP_amplitude"


class APAmplitudeChangeFeature(SpikeShapeFeature):
    """eFEL ``AP_amplitude_change``."""

    efel_name: ClassVar[str] = "AP_amplitude_change"


class APDurationHalfWidthChangeFeature(SpikeShapeFeature):
    """eFEL ``AP_duration_half_width_change``."""

    efel_name: ClassVar[str] = "AP_duration_half_width_change"


class AP1PeakFeature(SpikeShapeFeature):
    """eFEL ``AP1_peak``."""

    efel_name: ClassVar[str] = "AP1_peak"


class AP2PeakFeature(SpikeShapeFeature):
    """eFEL ``AP2_peak``."""

    efel_name: ClassVar[str] = "AP2_peak"


class AP2AP1DiffFeature(SpikeShapeFeature):
    """eFEL ``AP2_AP1_diff``."""

    efel_name: ClassVar[str] = "AP2_AP1_diff"


class AP2AP1PeakDiffFeature(SpikeShapeFeature):
    """eFEL ``AP2_AP1_peak_diff``."""

    efel_name: ClassVar[str] = "AP2_AP1_peak_diff"


class AmpDropFirstSecondFeature(SpikeShapeFeature):
    """eFEL ``amp_drop_first_second``."""

    efel_name: ClassVar[str] = "amp_drop_first_second"


class AmpDropFirstLastFeature(SpikeShapeFeature):
    """eFEL ``amp_drop_first_last``."""

    efel_name: ClassVar[str] = "amp_drop_first_last"


class AmpDropSecondLastFeature(SpikeShapeFeature):
    """eFEL ``amp_drop_second_last``."""

    efel_name: ClassVar[str] = "amp_drop_second_last"


class MaxAmpDifferenceFeature(SpikeShapeFeature):
    """eFEL ``max_amp_difference``."""

    efel_name: ClassVar[str] = "max_amp_difference"


class AHPDepthFromPeakFeature(SpikeShapeFeature):
    """eFEL ``AHP_depth_from_peak``."""

    efel_name: ClassVar[str] = "AHP_depth_from_peak"


class AHP1DepthFromPeakFeature(SpikeShapeFeature):
    """eFEL ``AHP1_depth_from_peak``."""

    efel_name: ClassVar[str] = "AHP1_depth_from_peak"


class AHP2DepthFromPeakFeature(SpikeShapeFeature):
    """eFEL ``AHP2_depth_from_peak``."""

    efel_name: ClassVar[str] = "AHP2_depth_from_peak"


class AHPDepthAbsFeature(SpikeShapeFeature):
    """eFEL ``AHP_depth_abs`` (same as min_AHP_values)."""

    efel_name: ClassVar[str] = "AHP_depth_abs"


class AHPDepthDiffFeature(SpikeShapeFeature):
    """eFEL ``AHP_depth_diff``."""

    efel_name: ClassVar[str] = "AHP_depth_diff"


class AHPDepthAbsSlowFeature(SpikeShapeFeature):
    """eFEL ``AHP_depth_abs_slow``."""

    efel_name: ClassVar[str] = "AHP_depth_abs_slow"


class AHPDepthSlowFeature(SpikeShapeFeature):
    """eFEL ``AHP_depth_slow``."""

    efel_name: ClassVar[str] = "AHP_depth_slow"


class AHPSlowTimeFeature(SpikeShapeFeature):
    """eFEL ``AHP_slow_time``."""

    efel_name: ClassVar[str] = "AHP_slow_time"


class FastAHPFeature(SpikeShapeFeature):
    """eFEL ``fast_AHP``."""

    efel_name: ClassVar[str] = "fast_AHP"


class FastAHPChangeFeature(SpikeShapeFeature):
    """eFEL ``fast_AHP_change``."""

    efel_name: ClassVar[str] = "fast_AHP_change"


class APRiseTimeFeature(SpikeShapeFeature):
    """eFEL ``AP_rise_time``."""

    efel_name: ClassVar[str] = "AP_rise_time"


class APFallTimeFeature(SpikeShapeFeature):
    """eFEL ``AP_fall_time``."""

    efel_name: ClassVar[str] = "AP_fall_time"


class APRiseRateFeature(SpikeShapeFeature):
    """eFEL ``AP_rise_rate``."""

    efel_name: ClassVar[str] = "AP_rise_rate"


class APFallRateFeature(SpikeShapeFeature):
    """eFEL ``AP_fall_rate``."""

    efel_name: ClassVar[str] = "AP_fall_rate"


class APRiseRateChangeFeature(SpikeShapeFeature):
    """eFEL ``AP_rise_rate_change``."""

    efel_name: ClassVar[str] = "AP_rise_rate_change"


class APFallRateChangeFeature(SpikeShapeFeature):
    """eFEL ``AP_fall_rate_change``."""

    efel_name: ClassVar[str] = "AP_fall_rate_change"


class APPeakUpstrokeFeature(SpikeShapeFeature):
    """eFEL ``AP_peak_upstroke``."""

    efel_name: ClassVar[str] = "AP_peak_upstroke"


class APPeakDownstrokeFeature(SpikeShapeFeature):
    """eFEL ``AP_peak_downstroke``."""

    efel_name: ClassVar[str] = "AP_peak_downstroke"


class APPhaseslopeFeature(SpikeShapeFeature):
    """eFEL ``AP_phaseslope``."""

    efel_name: ClassVar[str] = "AP_phaseslope"


class APWidthFeature(SpikeShapeFeature):
    """eFEL ``AP_width``."""

    efel_name: ClassVar[str] = "AP_width"


class APDurationFeature(SpikeShapeFeature):
    """eFEL ``AP_duration``."""

    efel_name: ClassVar[str] = "AP_duration"


class APDurationChangeFeature(SpikeShapeFeature):
    """eFEL ``AP_duration_change``."""

    efel_name: ClassVar[str] = "AP_duration_change"


class SpikeHalfWidthFeature(SpikeShapeFeature):
    """eFEL ``spike_half_width``."""

    efel_name: ClassVar[str] = "spike_half_width"


class AP1WidthFeature(SpikeShapeFeature):
    """eFEL ``AP1_width``."""

    efel_name: ClassVar[str] = "AP1_width"


class AP2WidthFeature(SpikeShapeFeature):
    """eFEL ``AP2_width``."""

    efel_name: ClassVar[str] = "AP2_width"


class APlastWidthFeature(SpikeShapeFeature):
    """eFEL ``APlast_width``."""

    efel_name: ClassVar[str] = "APlast_width"


class MinVoltageBetweenSpikesFeature(SpikeShapeFeature):
    """eFEL ``min_voltage_between_spikes``."""

    efel_name: ClassVar[str] = "min_voltage_between_spikes"


class DepolarizedBaseFeature(SpikeShapeFeature):
    """eFEL ``depolarized_base``."""

    efel_name: ClassVar[str] = "depolarized_base"


class PeakVoltageFeature(SpikeShapeFeature):
    """eFEL ``peak_voltage``."""

    efel_name: ClassVar[str] = "peak_voltage"


class APAmplitudeFromVoltagebaseFeature(SpikeShapeFeature):
    """eFEL ``AP_amplitude_from_voltagebase``."""

    efel_name: ClassVar[str] = "AP_amplitude_from_voltagebase"


class APHeightFeature(SpikeShapeFeature):
    """eFEL ``AP_height`` (same as peak_voltage)."""

    efel_name: ClassVar[str] = "AP_height"


class MinAHPValuesFeature(SpikeShapeFeature):
    """eFEL ``min_AHP_values``."""

    efel_name: ClassVar[str] = "min_AHP_values"


class APBeginTimeFeature(SpikeShapeFeature):
    """eFEL ``AP_begin_time``."""

    efel_name: ClassVar[str] = "AP_begin_time"


class SpikeWidth2Feature(SpikeShapeFeature):
    """eFEL ``spike_width2``."""

    efel_name: ClassVar[str] = "spike_width2"


class APWidthBetweenThresholdFeature(SpikeShapeFeature):
    """eFEL ``AP_width_between_threshold``."""

    efel_name: ClassVar[str] = "AP_width_between_threshold"


class AP2AP1BeginWidthDiffFeature(SpikeShapeFeature):
    """eFEL ``AP2_AP1_begin_width_diff``."""

    efel_name: ClassVar[str] = "AP2_AP1_begin_width_diff"


class ADPPeakValuesFeature(SpikeShapeFeature):
    """eFEL ``ADP_peak_values``."""

    efel_name: ClassVar[str] = "ADP_peak_values"


class ADPPeakAmplitudeFeature(SpikeShapeFeature):
    """eFEL ``ADP_peak_amplitude``."""

    efel_name: ClassVar[str] = "ADP_peak_amplitude"


class PhaseslopeMaxFeature(SpikeShapeFeature):
    """eFEL ``phaseslope_max``."""

    efel_name: ClassVar[str] = "phaseslope_max"


class InitburstSahpFeature(SpikeShapeFeature):
    """eFEL ``initburst_sahp``."""

    efel_name: ClassVar[str] = "initburst_sahp"


class InitburstSahpSsseFeature(SpikeShapeFeature):
    """eFEL ``initburst_sahp_ssse``."""

    efel_name: ClassVar[str] = "initburst_sahp_ssse"


class InitburstSahpVbFeature(SpikeShapeFeature):
    """eFEL ``initburst_sahp_vb``."""

    efel_name: ClassVar[str] = "initburst_sahp_vb"


class MinBetweenPeaksValuesFeature(SpikeShapeFeature):
    """eFEL ``min_between_peaks_values``."""

    efel_name: ClassVar[str] = "min_between_peaks_values"


class APAmplitudeDiffFeature(SpikeShapeFeature):
    """eFEL ``AP_amplitude_diff``."""

    efel_name: ClassVar[str] = "AP_amplitude_diff"


class AP1BeginWidthFeature(SpikeShapeFeature):
    """eFEL ``AP1_begin_width``."""

    efel_name: ClassVar[str] = "AP1_begin_width"


class AP2BeginWidthFeature(SpikeShapeFeature):
    """eFEL ``AP2_begin_width``."""

    efel_name: ClassVar[str] = "AP2_begin_width"

# -------------------------------------------------------------------------
# Subthreshold features
# -------------------------------------------------------------------------


class DecayTimeConstantAfterStimFeature(SubthresholdFeature):
    """eFEL ``decay_time_constant_after_stim``."""

    efel_name: ClassVar[str] = "decay_time_constant_after_stim"


class OhmicInputResistanceVbSsseFeature(SubthresholdFeature):
    """eFEL ``ohmic_input_resistance_vb_ssse``."""

    efel_name: ClassVar[str] = "ohmic_input_resistance_vb_ssse"


class SagAmplitudeFeature(SubthresholdFeature):
    """eFEL ``sag_amplitude``."""

    efel_name: ClassVar[str] = "sag_amplitude"


class SagRatio1Feature(SubthresholdFeature):
    """eFEL ``sag_ratio1``."""

    efel_name: ClassVar[str] = "sag_ratio1"


class SagRatio2Feature(SubthresholdFeature):
    """eFEL ``sag_ratio2``."""

    efel_name: ClassVar[str] = "sag_ratio2"


class VoltageAfterStimFeature(SubthresholdFeature):
    """eFEL ``voltage_after_stim``."""

    efel_name: ClassVar[str] = "voltage_after_stim"


class VoltageBaseFeature(SubthresholdFeature):
    """eFEL ``voltage_base``."""

    efel_name: ClassVar[str] = "voltage_base"


class SteadyStateVoltageStimendFeature(SubthresholdFeature):
    """eFEL ``steady_state_voltage_stimend``."""

    efel_name: ClassVar[str] = "steady_state_voltage_stimend"


class SteadyStateHyperFeature(SubthresholdFeature):
    """eFEL ``steady_state_hyper``."""

    efel_name: ClassVar[str] = "steady_state_hyper"


class SteadyStateVoltageFeature(SubthresholdFeature):
    """eFEL ``steady_state_voltage``."""

    efel_name: ClassVar[str] = "steady_state_voltage"


class TimeConstantFeature(SubthresholdFeature):
    """eFEL ``time_constant``."""

    efel_name: ClassVar[str] = "time_constant"


class SagTimeConstantFeature(SubthresholdFeature):
    """eFEL ``sag_time_constant``."""

    efel_name: ClassVar[str] = "sag_time_constant"


class MinimumVoltageFeature(SubthresholdFeature):
    """eFEL ``minimum_voltage``."""

    efel_name: ClassVar[str] = "minimum_voltage"


class MaximumVoltageFeature(SubthresholdFeature):
    """eFEL ``maximum_voltage``."""

    efel_name: ClassVar[str] = "maximum_voltage"


class MaximumVoltageFromVoltagebaseFeature(SubthresholdFeature):
    """eFEL ``maximum_voltage_from_voltagebase``."""

    efel_name: ClassVar[str] = "maximum_voltage_from_voltagebase"


class VoltageDeflectionVbSsseFeature(SubthresholdFeature):
    """eFEL ``voltage_deflection_vb_ssse``."""

    efel_name: ClassVar[str] = "voltage_deflection_vb_ssse"


class VoltageDeflectionFeature(SubthresholdFeature):
    """eFEL ``voltage_deflection``."""

    efel_name: ClassVar[str] = "voltage_deflection"


class VoltageDeflectionBeginFeature(SubthresholdFeature):
    """eFEL ``voltage_deflection_begin``."""

    efel_name: ClassVar[str] = "voltage_deflection_begin"


class OhmicInputResistanceFeature(SubthresholdFeature):
    """eFEL ``ohmic_input_resistance``."""

    efel_name: ClassVar[str] = "ohmic_input_resistance"


class SteadyStateCurrentStimendFeature(SubthresholdFeature):
    """eFEL ``steady_state_current_stimend``."""

    efel_name: ClassVar[str] = "steady_state_current_stimend"


class CurrentBaseFeature(SubthresholdFeature):
    """eFEL ``current_base``."""

    efel_name: ClassVar[str] = "current_base"


class MultipleDecayTimeConstantAfterStimFeature(SubthresholdFeature):
    """eFEL ``multiple_decay_time_constant_after_stim``."""

    efel_name: ClassVar[str] = "multiple_decay_time_constant_after_stim"


class ImpedanceFeature(SubthresholdFeature):
    """eFEL ``impedance``."""

    efel_name: ClassVar[str] = "impedance"


class ActivationTimeConstantFeature(SubthresholdFeature):
    """eFEL ``activation_time_constant``."""

    efel_name: ClassVar[str] = "activation_time_constant"


class DeactivationTimeConstantFeature(SubthresholdFeature):
    """eFEL ``deactivation_time_constant``."""

    efel_name: ClassVar[str] = "deactivation_time_constant"


class InactivationTimeConstantFeature(SubthresholdFeature):
    """eFEL ``inactivation_time_constant``."""

    efel_name: ClassVar[str] = "inactivation_time_constant"

# -------------------------------------------------------------------------
# Valid features per protocol: class tuples and discriminated unions
#
# Per-protocol feature sets derived from SSCx e-model configurations
# (https://github.com/BlueBrain/SSCxEModelExamples). Shape hierarchy
# determines timing fields; feature sets are per protocol name.
# -------------------------------------------------------------------------

# -- IDrest / FirePattern / Step (spiking, firing pattern) ----------------


IDREST_FEATURES: tuple[type[EFeature], ...] = (
    VoltageBaseFeature,
    VoltageAfterStimFeature,
    APAmplitudeFeature,
    APlastAmpFeature,
    AHPDepthFeature,
    MeanFrequencyFeature,
    InvTimeToFirstSpikeFeature,
    TimeToLastSpikeFeature,
    InvFirstISIFeature,
    InvSecondISIFeature,
    InvThirdISIFeature,
    InvFourthISIFeature,
    InvFifthISIFeature,
    InvLastISIFeature,
    BurstNumberFeature,
    ISICVFeature,
)

_IDREST = (
    VoltageBaseFeature
    | VoltageAfterStimFeature
    | APAmplitudeFeature
    | APlastAmpFeature
    | AHPDepthFeature
    | MeanFrequencyFeature
    | InvTimeToFirstSpikeFeature
    | TimeToLastSpikeFeature
    | InvFirstISIFeature
    | InvSecondISIFeature
    | InvThirdISIFeature
    | InvFourthISIFeature
    | InvFifthISIFeature
    | InvLastISIFeature
    | BurstNumberFeature
    | ISICVFeature
)
IDRestFeatureUnion = Annotated[_IDREST, Discriminator("type")]

# -- IDthresh (threshold search, minimal set) -----------------------------

IDTHRESH_FEATURES: tuple[type[EFeature], ...] = (
    SpikecountFeature,
    VoltageBaseFeature,
    MeanFrequencyFeature,
    AHPDepthFeature,
)

_IDTHRESH = SpikecountFeature | VoltageBaseFeature | MeanFrequencyFeature | AHPDepthFeature
IDThreshFeatureUnion = Annotated[_IDTHRESH, Discriminator("type")]

# -- APWaveform (spike shape) ---------------------------------------------

APWAVEFORM_FEATURES: tuple[type[EFeature], ...] = (
    APAmplitudeFeature,
    AP1AmpFeature,
    AP2AmpFeature,
    APDurationHalfWidthFeature,
    AHPDepthFeature,
)

_APWAVEFORM = (
    APAmplitudeFeature
    | AP1AmpFeature
    | AP2AmpFeature
    | APDurationHalfWidthFeature
    | AHPDepthFeature
)
APWaveformFeatureUnion = Annotated[_APWAVEFORM, Discriminator("type")]

# -- IV (subthreshold, input resistance) ----------------------------------

IV_FEATURES: tuple[type[EFeature], ...] = (
    VoltageBaseFeature,
    OhmicInputResistanceVbSsseFeature,
    VoltageDeflectionFeature,
    VoltageDeflectionBeginFeature,
)

_IV = (
    VoltageBaseFeature
    | OhmicInputResistanceVbSsseFeature
    | VoltageDeflectionFeature
    | VoltageDeflectionBeginFeature
)
IVFeatureUnion = Annotated[_IV, Discriminator("type")]

# -- sAHP / IDhyperpol (slow AHP) ----------------------------------------

SAHP_FEATURES: tuple[type[EFeature], ...] = (
    MeanFrequencyFeature,
    VoltageBaseFeature,
    DepolBlockBoolFeature,
    AHPDepthFeature,
    AHPTimeFromPeakFeature,
)

_SAHP = (
    MeanFrequencyFeature
    | VoltageBaseFeature
    | DepolBlockBoolFeature
    | AHPDepthFeature
    | AHPTimeFromPeakFeature
)
SAHPFeatureUnion = Annotated[_SAHP, Discriminator("type")]

# -- RMP (resting membrane potential, zero current) -----------------------

RMP_FEATURES: tuple[type[EFeature], ...] = (
    VoltageBaseFeature,
    SpikecountFeature,
)

_RMP = VoltageBaseFeature | SpikecountFeature
RMPFeatureUnion = Annotated[_RMP, Discriminator("type")]

# -- SpikeRec (multi-spike stimulus, recovery) ----------------------------

SPIKEREC_FEATURES: tuple[type[EFeature], ...] = (
    DecayTimeConstantAfterStimFeature,
    VoltageAfterStimFeature,
    SpikecountFeature,
)

_SPIKEREC = DecayTimeConstantAfterStimFeature | VoltageAfterStimFeature | SpikecountFeature
SpikeRecFeatureUnion = Annotated[_SPIKEREC, Discriminator("type")]

# -- Subthreshold / CapCheck (passive properties only) --------------------

SUBTHRESHOLD_FEATURES: tuple[type[EFeature], ...] = (
    VoltageBaseFeature,
    OhmicInputResistanceVbSsseFeature,
)

_SUBTHRESHOLD = VoltageBaseFeature | OhmicInputResistanceVbSsseFeature
SubthresholdFeatureUnion = Annotated[_SUBTHRESHOLD, Discriminator("type")]
