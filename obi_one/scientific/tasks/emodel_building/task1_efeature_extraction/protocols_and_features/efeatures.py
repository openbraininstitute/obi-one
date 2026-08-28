"""eFEL feature models and per-protocol feature sets for e-model optimisation.

One class per eFEL feature (https://efel.readthedocs.io/en/latest/eFeatures.html).
Per-protocol feature tuples at the bottom define which features are valid for
each protocol.
"""

import abc
from typing import Annotated, Any, ClassVar

from pydantic import Discriminator, Field, PositiveFloat
from pydantic.json_schema import GetJsonSchemaHandler, JsonSchemaValue
from pydantic_core import CoreSchema

from obi_one.core.base import OBIBaseModel
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.constants import (
    INHERIT_NOTE,
    SPIKE_DETECTION_THRESHOLD_DESCRIPTION,
    SPIKE_DETECTION_THRESHOLD_TITLE,
    TRACE_RESAMPLING_TIMESTEP_DESCRIPTION,
    TRACE_RESAMPLING_TIMESTEP_TITLE,
)


def _stim_timing_field(title: str, description: str) -> Any:
    """Build a per-feature eFEL stimulus-timing override (ms); 0.0 uses the protocol value."""
    return Field(
        default=0.0,
        title=title,
        description=description,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )


def stim_start_field() -> Any:
    """Per-feature ``stim_start`` override, declared by the feature-category subclasses."""
    return _stim_timing_field(
        "Stim start",
        "eFEL ``stim_start``: stimulus onset for this feature (ms). Overrides the"
        " protocol-level value; set to 0 to use the protocol's detected onset.",
    )


def stim_end_field() -> Any:
    """Per-feature ``stim_end`` override, declared by the feature-category subclasses."""
    return _stim_timing_field(
        "Stim end",
        "eFEL ``stim_end``: stimulus end for this feature (ms). Overrides the"
        " protocol-level value; set to 0 to use the protocol's detected end.",
    )


def stim_mid_field() -> Any:
    """Per-feature ``stim_mid`` override, declared by two-step (sAHP) features only."""
    return _stim_timing_field(
        "Stim mid",
        "First mid-transition for two-step (sAHP) protocols (ms). Overrides the"
        " protocol-level value; set to 0 to use the protocol's detected value.",
    )


def stim_mid_2_field() -> Any:
    """Per-feature ``stim_mid_2`` override, declared by two-step (sAHP) features only."""
    return _stim_timing_field(
        "Stim mid 2",
        "Second mid-transition for two-step (sAHP) protocols (ms). Overrides the"
        " protocol-level value; set to 0 to use the protocol's detected value.",
    )


class EFeature(OBIBaseModel):
    """Generic eFEL feature with per-feature setting overrides.

    A concrete feature fixes ``efel_name``; instances carry only the eFEL
    detection knobs the user may override for this feature:
    ``spike_detection_threshold`` and ``trace_resampling_timestep`` (``None`` =
    inherit the protocol, then global, value), plus
    the stimulus-window overrides ``stim_start``/``stim_end`` (and
    ``stim_mid``/``stim_mid_2`` on two-step features) declared on the
    feature-category subclasses.

    ``efel_settings_overrides()`` returns only the settings this feature actually
    sets, so the extraction task can cascade them: feature > protocol > global.
    """

    efel_name: ClassVar[str] = ""
    """The eFEL feature key, fixed by each concrete feature class."""

    efel_doc_anchor: ClassVar[str] = ""
    """The eFEL documentation anchor, fixed by each concrete feature class."""

    feature_category: ClassVar[str] = ""
    """Category group for UI rendering (spike_event, spike_shape, subthreshold)."""

    # ------------------------------------------------------------------
    # Always-present eFEL settings with eFEL defaults pre-filled
    # ------------------------------------------------------------------
    spike_detection_threshold: float | None = Field(
        default=None,
        title=SPIKE_DETECTION_THRESHOLD_TITLE,
        description=f"{SPIKE_DETECTION_THRESHOLD_DESCRIPTION} {INHERIT_NOTE}",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL,
            SchemaKey.UNITS: Units.MILLIVOLTS,
        },
    )
    trace_resampling_timestep: PositiveFloat | None = Field(
        default=None,
        title=TRACE_RESAMPLING_TIMESTEP_TITLE,
        description=f"{TRACE_RESAMPLING_TIMESTEP_DESCRIPTION} {INHERIT_NOTE}",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    @classmethod
    def __get_pydantic_json_schema__(  # ruff: ignore[bad-dunder-method-name]
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        """Inject ``efel_feature_category`` and ``efel_doc_anchor`` into the JSON schema."""
        schema = handler(core_schema)
        extra = schema.setdefault("extra", {})
        if cls.feature_category:
            extra[SchemaKey.EFEL_FEATURE_CATEGORY] = cls.feature_category
        if cls.efel_doc_anchor:
            extra[SchemaKey.EFEL_DOC_ANCHOR] = cls.efel_doc_anchor
        return schema

    def efel_settings_overrides(self) -> dict:
        """Return this feature's own eFEL setting overrides (only what it sets).

        Unset (``None``) values are omitted so the extraction task can cascade
        feature > protocol > global. ``stim_start``/``stim_end`` (declared on the
        feature-category subclasses) are included only when non-zero.
        """
        overrides: dict[str, float | bool] = {}
        if self.spike_detection_threshold is not None:
            overrides["Threshold"] = self.spike_detection_threshold
        if self.trace_resampling_timestep is not None:
            overrides["interp_step"] = self.trace_resampling_timestep
        for key in ("stim_start", "stim_end"):
            value = getattr(self, key, 0.0)
            if value:
                overrides[key] = value
        return overrides


# =========================================================================
# Concrete feature classes and per-protocol unions.
# Everything below is generated; see the module docstring for the source.
# =========================================================================

_INV_ISI_DOC_ANCHOR = (
    "inv-first-isi-inv-second-isi-inv-third-isi-inv-fourth-isi-inv-fifth-isi-inv-last-isi"
)
_INTERBURST_PERCENT_VALUES_DOC_ANCHOR = (
    "interburst-15percent-values-interburst-20percent-values-interburst-25percent-values"
    "-interburst-30percent-values-interburst-40percent-values-interburst-60percent-values"
)
_AP_AMPLITUDE_DOC_ANCHOR = "ap-amplitude-ap1-amp-ap2-amp-aplast-amp"
_AP_PEAK_DOC_ANCHOR = "ap1-peak-ap2-peak"
_AHP_DEPTH_FROM_PEAK_DOC_ANCHOR = "ahp-depth-from-peak-ahp1-depth-from-peak-ahp2-depth-from-peak"
_SPIKE_WIDTH_DOC_ANCHOR = "spike-half-width-ap1-width-ap2-width-aplast-width"
_AP_BEGIN_WIDTH_DOC_ANCHOR = "ap-begin-width-ap1-begin-width-ap2-begin-width"


class SpikeEventFeature(EFeature, abc.ABC):
    """eFEL spike-event features; carries the per-feature stimulus window."""

    feature_category: ClassVar[str] = "spike_event"

    stim_start: float = stim_start_field()
    stim_end: float = stim_end_field()


class SpikeShapeFeature(EFeature, abc.ABC):
    """eFEL spike-shape features; carries the per-feature stimulus window."""

    feature_category: ClassVar[str] = "spike_shape"

    stim_start: float = stim_start_field()
    stim_end: float = stim_end_field()


class SubthresholdFeature(EFeature, abc.ABC):
    """eFEL subthreshold features; carries the per-feature stimulus window."""

    feature_category: ClassVar[str] = "subthreshold"

    stim_start: float = stim_start_field()
    stim_end: float = stim_end_field()


# -------------------------------------------------------------------------
# Spike event features
# -------------------------------------------------------------------------


class ISICVFeature(SpikeEventFeature):
    """eFEL ``ISI_CV``."""

    efel_name: ClassVar[str] = "ISI_CV"
    efel_doc_anchor: ClassVar[str] = "isi-cv"


class ISILogSlopeFeature(SpikeEventFeature):
    """eFEL ``ISI_log_slope``."""

    efel_name: ClassVar[str] = "ISI_log_slope"
    efel_doc_anchor: ClassVar[str] = "isi-log-slope"


class SpikecountFeature(SpikeEventFeature):
    """eFEL ``Spikecount``."""

    efel_name: ClassVar[str] = "Spikecount"
    efel_doc_anchor: ClassVar[str] = "spike-count"


class AdaptationIndexFeature(SpikeEventFeature):
    """eFEL ``adaptation_index``."""

    efel_name: ClassVar[str] = "adaptation_index"
    efel_doc_anchor: ClassVar[str] = "adaptation-index"


class DepolBlockBoolFeature(SpikeEventFeature):
    """eFEL ``depol_block_bool``."""

    efel_name: ClassVar[str] = "depol_block_bool"
    efel_doc_anchor: ClassVar[str] = "depol-block-bool"
    stim_mid: float = stim_mid_field()
    stim_mid_2: float = stim_mid_2_field()


class DoubletISIFeature(SpikeEventFeature):
    """eFEL ``doublet_ISI``."""

    efel_name: ClassVar[str] = "doublet_ISI"
    efel_doc_anchor: ClassVar[str] = "doublet-isi"


class InvFirstISIFeature(SpikeEventFeature):
    """eFEL ``inv_first_ISI``."""

    efel_name: ClassVar[str] = "inv_first_ISI"
    efel_doc_anchor: ClassVar[str] = _INV_ISI_DOC_ANCHOR


class InvLastISIFeature(SpikeEventFeature):
    """eFEL ``inv_last_ISI``."""

    efel_name: ClassVar[str] = "inv_last_ISI"
    efel_doc_anchor: ClassVar[str] = _INV_ISI_DOC_ANCHOR


class InvSecondISIFeature(SpikeEventFeature):
    """eFEL ``inv_second_ISI``."""

    efel_name: ClassVar[str] = "inv_second_ISI"
    efel_doc_anchor: ClassVar[str] = _INV_ISI_DOC_ANCHOR


class InvThirdISIFeature(SpikeEventFeature):
    """eFEL ``inv_third_ISI``."""

    efel_name: ClassVar[str] = "inv_third_ISI"
    efel_doc_anchor: ClassVar[str] = _INV_ISI_DOC_ANCHOR


class InvTimeToFirstSpikeFeature(SpikeEventFeature):
    """eFEL ``inv_time_to_first_spike``."""

    efel_name: ClassVar[str] = "inv_time_to_first_spike"
    efel_doc_anchor: ClassVar[str] = "inv-time-to-first-spike"


class IrregularityIndexFeature(SpikeEventFeature):
    """eFEL ``irregularity_index``."""

    efel_name: ClassVar[str] = "irregularity_index"
    efel_doc_anchor: ClassVar[str] = "irregularity-index"


class MeanFrequencyFeature(SpikeEventFeature):
    """eFEL ``mean_frequency``."""

    efel_name: ClassVar[str] = "mean_frequency"
    efel_doc_anchor: ClassVar[str] = "mean-frequency"
    stim_mid: float = stim_mid_field()
    stim_mid_2: float = stim_mid_2_field()


class NumberInitialSpikesFeature(SpikeEventFeature):
    """eFEL ``number_initial_spikes``."""

    efel_name: ClassVar[str] = "number_initial_spikes"
    efel_doc_anchor: ClassVar[str] = "number-initial-spikes"


class StrictBurstMeanFreqFeature(SpikeEventFeature):
    """eFEL ``strict_burst_mean_freq``."""

    efel_name: ClassVar[str] = "strict_burst_mean_freq"
    efel_doc_anchor: ClassVar[str] = "strict-burst-mean-freq"


class StrictBurstNumberFeature(SpikeEventFeature):
    """eFEL ``strict_burst_number``."""

    efel_name: ClassVar[str] = "strict_burst_number"
    efel_doc_anchor: ClassVar[str] = "strict-burst-number"


class TimeToFirstSpikeFeature(SpikeEventFeature):
    """eFEL ``time_to_first_spike``."""

    efel_name: ClassVar[str] = "time_to_first_spike"
    efel_doc_anchor: ClassVar[str] = "time-to-first-spike"


class TimeToLastSpikeFeature(SpikeEventFeature):
    """eFEL ``time_to_last_spike``."""

    efel_name: ClassVar[str] = "time_to_last_spike"
    efel_doc_anchor: ClassVar[str] = "time-to-last-spike"


class TimeToSecondSpikeFeature(SpikeEventFeature):
    """eFEL ``time_to_second_spike``."""

    efel_name: ClassVar[str] = "time_to_second_spike"
    efel_doc_anchor: ClassVar[str] = "time-to-second-spike"


class InvFourthISIFeature(SpikeEventFeature):
    """eFEL ``inv_fourth_ISI``."""

    efel_name: ClassVar[str] = "inv_fourth_ISI"
    efel_doc_anchor: ClassVar[str] = _INV_ISI_DOC_ANCHOR


class InvFifthISIFeature(SpikeEventFeature):
    """eFEL ``inv_fifth_ISI``."""

    efel_name: ClassVar[str] = "inv_fifth_ISI"
    efel_doc_anchor: ClassVar[str] = _INV_ISI_DOC_ANCHOR


class ISISemilogSlopeFeature(SpikeEventFeature):
    """eFEL ``ISI_semilog_slope``."""

    efel_name: ClassVar[str] = "ISI_semilog_slope"
    efel_doc_anchor: ClassVar[str] = "isi-semilog-slope"


class ISILogSlopeSkipFeature(SpikeEventFeature):
    """eFEL ``ISI_log_slope_skip``."""

    efel_name: ClassVar[str] = "ISI_log_slope_skip"
    efel_doc_anchor: ClassVar[str] = "isi-log-slope-skip"


class AdaptationIndex2Feature(SpikeEventFeature):
    """eFEL ``adaptation_index_2``."""

    efel_name: ClassVar[str] = "adaptation_index_2"
    efel_doc_anchor: ClassVar[str] = "adaptation-index-2"


class BurstNumberFeature(SpikeEventFeature):
    """eFEL ``burst_number``."""

    efel_name: ClassVar[str] = "burst_number"
    efel_doc_anchor: ClassVar[str] = "burst-number"


class SingleBurstRatioFeature(SpikeEventFeature):
    """eFEL ``single_burst_ratio``."""

    efel_name: ClassVar[str] = "single_burst_ratio"
    efel_doc_anchor: ClassVar[str] = "single-burst-ratio"


class SpikeCountStimintFeature(SpikeEventFeature):
    """eFEL ``spike_count_stimint``."""

    efel_name: ClassVar[str] = "spike_count_stimint"
    efel_doc_anchor: ClassVar[str] = "spike-count-stimint"


class SpikesPerBurstFeature(SpikeEventFeature):
    """eFEL ``spikes_per_burst``."""

    efel_name: ClassVar[str] = "spikes_per_burst"
    efel_doc_anchor: ClassVar[str] = "spikes-per-burst"


class BurstMeanFreqFeature(SpikeEventFeature):
    """eFEL ``burst_mean_freq``."""

    efel_name: ClassVar[str] = "burst_mean_freq"
    efel_doc_anchor: ClassVar[str] = "burst-mean-freq"


class InterburstVoltageFeature(SpikeEventFeature):
    """eFEL ``strict_interburst_voltage``."""

    efel_name: ClassVar[str] = "strict_interburst_voltage"
    efel_doc_anchor: ClassVar[str] = "strict-interburst-voltage"


class InterburstMinValuesFeature(SpikeEventFeature):
    """eFEL ``interburst_min_values``."""

    efel_name: ClassVar[str] = "interburst_min_values"
    efel_doc_anchor: ClassVar[str] = "interburst-min-values"


class PeakTimeFeature(SpikeEventFeature):
    """eFEL ``peak_time``."""

    efel_name: ClassVar[str] = "peak_time"
    efel_doc_anchor: ClassVar[str] = "peak-time"


class ISIValuesFeature(SpikeEventFeature):
    """eFEL ``ISI_values``."""

    efel_name: ClassVar[str] = "ISI_values"
    efel_doc_anchor: ClassVar[str] = "isi-values"


class AllISIValuesFeature(SpikeEventFeature):
    """eFEL ``all_ISI_values``."""

    efel_name: ClassVar[str] = "all_ISI_values"
    efel_doc_anchor: ClassVar[str] = "all-isi-values"


class InvISIValuesFeature(SpikeEventFeature):
    """eFEL ``inv_ISI_values``."""

    efel_name: ClassVar[str] = "inv_ISI_values"
    efel_doc_anchor: ClassVar[str] = "inv-isi-values"


class InterburstDurationFeature(SpikeEventFeature):
    """eFEL ``interburst_duration``."""

    efel_name: ClassVar[str] = "interburst_duration"
    efel_doc_anchor: ClassVar[str] = "interburst-duration"


class TimeToInterburstMinFeature(SpikeEventFeature):
    """eFEL ``time_to_interburst_min``."""

    efel_name: ClassVar[str] = "time_to_interburst_min"
    efel_doc_anchor: ClassVar[str] = "time-to-interburst-min"


class TimeToPostburstSlowAhpFeature(SpikeEventFeature):
    """eFEL ``time_to_postburst_slow_ahp``."""

    efel_name: ClassVar[str] = "time_to_postburst_slow_ahp"
    efel_doc_anchor: ClassVar[str] = "time-to-postburst-slow-ahp"


class PostburstMinValuesFeature(SpikeEventFeature):
    """eFEL ``postburst_min_values``."""

    efel_name: ClassVar[str] = "postburst_min_values"
    efel_doc_anchor: ClassVar[str] = "postburst-min-values"


class PostburstSlowAhpValuesFeature(SpikeEventFeature):
    """eFEL ``postburst_slow_ahp_values``."""

    efel_name: ClassVar[str] = "postburst_slow_ahp_values"
    efel_doc_anchor: ClassVar[str] = "postburst-slow-ahp-values"


class PostburstFastAhpValuesFeature(SpikeEventFeature):
    """eFEL ``postburst_fast_ahp_values``."""

    efel_name: ClassVar[str] = "postburst_fast_ahp_values"
    efel_doc_anchor: ClassVar[str] = "postburst-fast-ahp-values"


class PostburstAdpPeakValuesFeature(SpikeEventFeature):
    """eFEL ``postburst_adp_peak_values``."""

    efel_name: ClassVar[str] = "postburst_adp_peak_values"
    efel_doc_anchor: ClassVar[str] = "postburst-adp-peak-values"


class TimeToPostburstFastAhpFeature(SpikeEventFeature):
    """eFEL ``time_to_postburst_fast_ahp``."""

    efel_name: ClassVar[str] = "time_to_postburst_fast_ahp"
    efel_doc_anchor: ClassVar[str] = "time-to-postburst-fast-ahp"


class TimeToPostburstAdpPeakFeature(SpikeEventFeature):
    """eFEL ``time_to_postburst_adp_peak``."""

    efel_name: ClassVar[str] = "time_to_postburst_adp_peak"
    efel_doc_anchor: ClassVar[str] = "time-to-postburst-adp-peak"


class SpikesPerBurstDiffFeature(SpikeEventFeature):
    """eFEL ``spikes_per_burst_diff``."""

    efel_name: ClassVar[str] = "spikes_per_burst_diff"
    efel_doc_anchor: ClassVar[str] = "spikes-per-burst-diff"


class SpikesInBurst1Burst2DiffFeature(SpikeEventFeature):
    """eFEL ``spikes_in_burst1_burst2_diff``."""

    efel_name: ClassVar[str] = "spikes_in_burst1_burst2_diff"
    efel_doc_anchor: ClassVar[str] = "spikes-in-burst1-burst2-diff"


class SpikesInBurst1BurstlastDiffFeature(SpikeEventFeature):
    """eFEL ``spikes_in_burst1_burstlast_diff``."""

    efel_name: ClassVar[str] = "spikes_in_burst1_burstlast_diff"
    efel_doc_anchor: ClassVar[str] = "spikes-in-burst1-burstlast-diff"


class Interburst15PercentValuesFeature(SpikeEventFeature):
    """eFEL ``interburst_15percent_values``."""

    efel_name: ClassVar[str] = "interburst_15percent_values"
    efel_doc_anchor: ClassVar[str] = _INTERBURST_PERCENT_VALUES_DOC_ANCHOR


class Interburst20PercentValuesFeature(SpikeEventFeature):
    """eFEL ``interburst_20percent_values``."""

    efel_name: ClassVar[str] = "interburst_20percent_values"
    efel_doc_anchor: ClassVar[str] = _INTERBURST_PERCENT_VALUES_DOC_ANCHOR


class Interburst25PercentValuesFeature(SpikeEventFeature):
    """eFEL ``interburst_25percent_values``."""

    efel_name: ClassVar[str] = "interburst_25percent_values"
    efel_doc_anchor: ClassVar[str] = _INTERBURST_PERCENT_VALUES_DOC_ANCHOR


class Interburst30PercentValuesFeature(SpikeEventFeature):
    """eFEL ``interburst_30percent_values``."""

    efel_name: ClassVar[str] = "interburst_30percent_values"
    efel_doc_anchor: ClassVar[str] = _INTERBURST_PERCENT_VALUES_DOC_ANCHOR


class Interburst40PercentValuesFeature(SpikeEventFeature):
    """eFEL ``interburst_40percent_values``."""

    efel_name: ClassVar[str] = "interburst_40percent_values"
    efel_doc_anchor: ClassVar[str] = _INTERBURST_PERCENT_VALUES_DOC_ANCHOR


class Interburst60PercentValuesFeature(SpikeEventFeature):
    """eFEL ``interburst_60percent_values``."""

    efel_name: ClassVar[str] = "interburst_60percent_values"
    efel_doc_anchor: ClassVar[str] = _INTERBURST_PERCENT_VALUES_DOC_ANCHOR


class Interburst15PercentVoltageFeature(SpikeEventFeature):
    """eFEL ``interburst_voltage`` (ISI Python efeature variant)."""

    efel_name: ClassVar[str] = "interburst_voltage"
    efel_doc_anchor: ClassVar[str] = "interburst-voltage"


# -------------------------------------------------------------------------
# Spike shape features
# -------------------------------------------------------------------------


class AHPDepthFeature(SpikeShapeFeature):
    """eFEL ``AHP_depth``."""

    efel_name: ClassVar[str] = "AHP_depth"
    efel_doc_anchor: ClassVar[str] = "ahp-depth"
    stim_mid: float = stim_mid_field()
    stim_mid_2: float = stim_mid_2_field()


class AHPTimeFromPeakFeature(SpikeShapeFeature):
    """eFEL ``AHP_time_from_peak``."""

    efel_name: ClassVar[str] = "AHP_time_from_peak"
    efel_doc_anchor: ClassVar[str] = "ahp-time-from-peak"
    stim_mid: float = stim_mid_field()
    stim_mid_2: float = stim_mid_2_field()


class AP1AmpFeature(SpikeShapeFeature):
    """eFEL ``AP1_amp``."""

    efel_name: ClassVar[str] = "AP1_amp"
    efel_doc_anchor: ClassVar[str] = _AP_AMPLITUDE_DOC_ANCHOR


class APAmplitudeFeature(SpikeShapeFeature):
    """eFEL ``AP_amplitude``."""

    efel_name: ClassVar[str] = "AP_amplitude"
    efel_doc_anchor: ClassVar[str] = _AP_AMPLITUDE_DOC_ANCHOR


class APBeginVoltageFeature(SpikeShapeFeature):
    """eFEL ``AP_begin_voltage``."""

    efel_name: ClassVar[str] = "AP_begin_voltage"
    efel_doc_anchor: ClassVar[str] = "ap-begin-voltage-ap1-begin-voltage-ap2-begin-voltage"


class APBeginWidthFeature(SpikeShapeFeature):
    """eFEL ``AP_begin_width``."""

    efel_name: ClassVar[str] = "AP_begin_width"
    efel_doc_anchor: ClassVar[str] = _AP_BEGIN_WIDTH_DOC_ANCHOR


class APDurationHalfWidthFeature(SpikeShapeFeature):
    """eFEL ``AP_duration_half_width``."""

    efel_name: ClassVar[str] = "AP_duration_half_width"
    efel_doc_anchor: ClassVar[str] = "ap-duration-half-width"


class AP2AmpFeature(SpikeShapeFeature):
    """eFEL ``AP2_amp``."""

    efel_name: ClassVar[str] = "AP2_amp"
    efel_doc_anchor: ClassVar[str] = _AP_AMPLITUDE_DOC_ANCHOR


class APlastAmpFeature(SpikeShapeFeature):
    """eFEL ``APlast_amp``."""

    efel_name: ClassVar[str] = "APlast_amp"
    efel_doc_anchor: ClassVar[str] = _AP_AMPLITUDE_DOC_ANCHOR


class MeanAPAmplitudeFeature(SpikeShapeFeature):
    """eFEL ``mean_AP_amplitude``."""

    efel_name: ClassVar[str] = "mean_AP_amplitude"
    efel_doc_anchor: ClassVar[str] = "mean-ap-amplitude"


class APAmplitudeChangeFeature(SpikeShapeFeature):
    """eFEL ``AP_amplitude_change``."""

    efel_name: ClassVar[str] = "AP_amplitude_change"
    efel_doc_anchor: ClassVar[str] = "ap-amplitude-change"


class APDurationHalfWidthChangeFeature(SpikeShapeFeature):
    """eFEL ``AP_duration_half_width_change``."""

    efel_name: ClassVar[str] = "AP_duration_half_width_change"
    efel_doc_anchor: ClassVar[str] = "ap-duration-half-width-change"


class AP1PeakFeature(SpikeShapeFeature):
    """eFEL ``AP1_peak``."""

    efel_name: ClassVar[str] = "AP1_peak"
    efel_doc_anchor: ClassVar[str] = _AP_PEAK_DOC_ANCHOR


class AP2PeakFeature(SpikeShapeFeature):
    """eFEL ``AP2_peak``."""

    efel_name: ClassVar[str] = "AP2_peak"
    efel_doc_anchor: ClassVar[str] = _AP_PEAK_DOC_ANCHOR


class AP2AP1DiffFeature(SpikeShapeFeature):
    """eFEL ``AP2_AP1_diff``."""

    efel_name: ClassVar[str] = "AP2_AP1_diff"
    efel_doc_anchor: ClassVar[str] = "ap2-ap1-diff"


class AP2AP1PeakDiffFeature(SpikeShapeFeature):
    """eFEL ``AP2_AP1_peak_diff``."""

    efel_name: ClassVar[str] = "AP2_AP1_peak_diff"
    efel_doc_anchor: ClassVar[str] = "ap2-ap1-peak-diff"


class AmpDropFirstSecondFeature(SpikeShapeFeature):
    """eFEL ``amp_drop_first_second``."""

    efel_name: ClassVar[str] = "amp_drop_first_second"
    efel_doc_anchor: ClassVar[str] = "amp-drop-first-second"


class AmpDropFirstLastFeature(SpikeShapeFeature):
    """eFEL ``amp_drop_first_last``."""

    efel_name: ClassVar[str] = "amp_drop_first_last"
    efel_doc_anchor: ClassVar[str] = "amp-drop-first-last"


class AmpDropSecondLastFeature(SpikeShapeFeature):
    """eFEL ``amp_drop_second_last``."""

    efel_name: ClassVar[str] = "amp_drop_second_last"
    efel_doc_anchor: ClassVar[str] = "amp-drop-second-last"


class MaxAmpDifferenceFeature(SpikeShapeFeature):
    """eFEL ``max_amp_difference``."""

    efel_name: ClassVar[str] = "max_amp_difference"
    efel_doc_anchor: ClassVar[str] = "max-amp-difference"


class AHPDepthFromPeakFeature(SpikeShapeFeature):
    """eFEL ``AHP_depth_from_peak``."""

    efel_name: ClassVar[str] = "AHP_depth_from_peak"
    efel_doc_anchor: ClassVar[str] = _AHP_DEPTH_FROM_PEAK_DOC_ANCHOR


class AHP1DepthFromPeakFeature(SpikeShapeFeature):
    """eFEL ``AHP1_depth_from_peak``."""

    efel_name: ClassVar[str] = "AHP1_depth_from_peak"
    efel_doc_anchor: ClassVar[str] = _AHP_DEPTH_FROM_PEAK_DOC_ANCHOR


class AHP2DepthFromPeakFeature(SpikeShapeFeature):
    """eFEL ``AHP2_depth_from_peak``."""

    efel_name: ClassVar[str] = "AHP2_depth_from_peak"
    efel_doc_anchor: ClassVar[str] = _AHP_DEPTH_FROM_PEAK_DOC_ANCHOR


class AHPDepthAbsFeature(SpikeShapeFeature):
    """eFEL ``AHP_depth_abs`` (same as min_AHP_values)."""

    efel_name: ClassVar[str] = "AHP_depth_abs"
    efel_doc_anchor: ClassVar[str] = "ahp-depth-abs"


class AHPDepthDiffFeature(SpikeShapeFeature):
    """eFEL ``AHP_depth_diff``."""

    efel_name: ClassVar[str] = "AHP_depth_diff"
    efel_doc_anchor: ClassVar[str] = "ahp-depth-diff"


class AHPDepthAbsSlowFeature(SpikeShapeFeature):
    """eFEL ``AHP_depth_abs_slow``."""

    efel_name: ClassVar[str] = "AHP_depth_abs_slow"
    efel_doc_anchor: ClassVar[str] = "ahp-depth-abs-slow"


class AHPDepthSlowFeature(SpikeShapeFeature):
    """eFEL ``AHP_depth_slow``."""

    efel_name: ClassVar[str] = "AHP_depth_slow"
    efel_doc_anchor: ClassVar[str] = "ahp-depth-slow"


class AHPSlowTimeFeature(SpikeShapeFeature):
    """eFEL ``AHP_slow_time``."""

    efel_name: ClassVar[str] = "AHP_slow_time"
    efel_doc_anchor: ClassVar[str] = "ahp-slow-time"


class FastAHPFeature(SpikeShapeFeature):
    """eFEL ``fast_AHP``."""

    efel_name: ClassVar[str] = "fast_AHP"
    efel_doc_anchor: ClassVar[str] = "fast-ahp"


class FastAHPChangeFeature(SpikeShapeFeature):
    """eFEL ``fast_AHP_change``."""

    efel_name: ClassVar[str] = "fast_AHP_change"
    efel_doc_anchor: ClassVar[str] = "fast-ahp-change"


class APRiseTimeFeature(SpikeShapeFeature):
    """eFEL ``AP_rise_time``."""

    efel_name: ClassVar[str] = "AP_rise_time"
    efel_doc_anchor: ClassVar[str] = "ap-rise-time"


class APFallTimeFeature(SpikeShapeFeature):
    """eFEL ``AP_fall_time``."""

    efel_name: ClassVar[str] = "AP_fall_time"
    efel_doc_anchor: ClassVar[str] = "ap-fall-time"


class APRiseRateFeature(SpikeShapeFeature):
    """eFEL ``AP_rise_rate``."""

    efel_name: ClassVar[str] = "AP_rise_rate"
    efel_doc_anchor: ClassVar[str] = "ap-rise-rate"


class APFallRateFeature(SpikeShapeFeature):
    """eFEL ``AP_fall_rate``."""

    efel_name: ClassVar[str] = "AP_fall_rate"
    efel_doc_anchor: ClassVar[str] = "ap-fall-rate"


class APRiseRateChangeFeature(SpikeShapeFeature):
    """eFEL ``AP_rise_rate_change``."""

    efel_name: ClassVar[str] = "AP_rise_rate_change"
    efel_doc_anchor: ClassVar[str] = "ap-rise-rate-change"


class APFallRateChangeFeature(SpikeShapeFeature):
    """eFEL ``AP_fall_rate_change``."""

    efel_name: ClassVar[str] = "AP_fall_rate_change"
    efel_doc_anchor: ClassVar[str] = "ap-fall-rate-change"


class APPeakUpstrokeFeature(SpikeShapeFeature):
    """eFEL ``AP_peak_upstroke``."""

    efel_name: ClassVar[str] = "AP_peak_upstroke"
    efel_doc_anchor: ClassVar[str] = "ap-peak-upstroke"


class APPeakDownstrokeFeature(SpikeShapeFeature):
    """eFEL ``AP_peak_downstroke``."""

    efel_name: ClassVar[str] = "AP_peak_downstroke"
    efel_doc_anchor: ClassVar[str] = "ap-peak-downstroke"


class APPhaseslopeFeature(SpikeShapeFeature):
    """eFEL ``AP_phaseslope``."""

    efel_name: ClassVar[str] = "AP_phaseslope"
    efel_doc_anchor: ClassVar[str] = "ap-phaseslope"


class APWidthFeature(SpikeShapeFeature):
    """eFEL ``AP_width``."""

    efel_name: ClassVar[str] = "AP_width"
    efel_doc_anchor: ClassVar[str] = "ap-width"


class APDurationFeature(SpikeShapeFeature):
    """eFEL ``AP_duration``."""

    efel_name: ClassVar[str] = "AP_duration"
    efel_doc_anchor: ClassVar[str] = "ap-duration"


class APDurationChangeFeature(SpikeShapeFeature):
    """eFEL ``AP_duration_change``."""

    efel_name: ClassVar[str] = "AP_duration_change"
    efel_doc_anchor: ClassVar[str] = "ap-duration-change"


class SpikeHalfWidthFeature(SpikeShapeFeature):
    """eFEL ``spike_half_width``."""

    efel_name: ClassVar[str] = "spike_half_width"
    efel_doc_anchor: ClassVar[str] = _SPIKE_WIDTH_DOC_ANCHOR


class AP1WidthFeature(SpikeShapeFeature):
    """eFEL ``AP1_width``."""

    efel_name: ClassVar[str] = "AP1_width"
    efel_doc_anchor: ClassVar[str] = _SPIKE_WIDTH_DOC_ANCHOR


class AP2WidthFeature(SpikeShapeFeature):
    """eFEL ``AP2_width``."""

    efel_name: ClassVar[str] = "AP2_width"
    efel_doc_anchor: ClassVar[str] = _SPIKE_WIDTH_DOC_ANCHOR


class APlastWidthFeature(SpikeShapeFeature):
    """eFEL ``APlast_width``."""

    efel_name: ClassVar[str] = "APlast_width"
    efel_doc_anchor: ClassVar[str] = _SPIKE_WIDTH_DOC_ANCHOR


class MinVoltageBetweenSpikesFeature(SpikeShapeFeature):
    """eFEL ``min_voltage_between_spikes``."""

    efel_name: ClassVar[str] = "min_voltage_between_spikes"
    efel_doc_anchor: ClassVar[str] = "min-voltage-between-spikes"


class DepolarizedBaseFeature(SpikeShapeFeature):
    """eFEL ``depolarized_base``."""

    efel_name: ClassVar[str] = "depolarized_base"
    efel_doc_anchor: ClassVar[str] = "depolarized-base"


class PeakVoltageFeature(SpikeShapeFeature):
    """eFEL ``peak_voltage``."""

    efel_name: ClassVar[str] = "peak_voltage"
    efel_doc_anchor: ClassVar[str] = "peak-voltage"


class APAmplitudeFromVoltagebaseFeature(SpikeShapeFeature):
    """eFEL ``AP_amplitude_from_voltagebase``."""

    efel_name: ClassVar[str] = "AP_amplitude_from_voltagebase"
    efel_doc_anchor: ClassVar[str] = "ap-amplitude-from-voltagebase"


class APHeightFeature(SpikeShapeFeature):
    """eFEL ``AP_height`` (same as peak_voltage)."""

    efel_name: ClassVar[str] = "AP_height"
    efel_doc_anchor: ClassVar[str] = "ap-height"


class MinAHPValuesFeature(SpikeShapeFeature):
    """eFEL ``min_AHP_values``."""

    efel_name: ClassVar[str] = "min_AHP_values"
    efel_doc_anchor: ClassVar[str] = "min-ahp-values"


class APBeginTimeFeature(SpikeShapeFeature):
    """eFEL ``AP_begin_time``."""

    efel_name: ClassVar[str] = "AP_begin_time"
    efel_doc_anchor: ClassVar[str] = "ap-begin-time"


class SpikeWidth2Feature(SpikeShapeFeature):
    """eFEL ``spike_width2``."""

    efel_name: ClassVar[str] = "spike_width2"
    efel_doc_anchor: ClassVar[str] = "spike-width2"


class APWidthBetweenThresholdFeature(SpikeShapeFeature):
    """eFEL ``AP_width_between_threshold``."""

    efel_name: ClassVar[str] = "AP_width_between_threshold"
    efel_doc_anchor: ClassVar[str] = "ap-width-between-threshold"


class AP2AP1BeginWidthDiffFeature(SpikeShapeFeature):
    """eFEL ``AP2_AP1_begin_width_diff``."""

    efel_name: ClassVar[str] = "AP2_AP1_begin_width_diff"
    efel_doc_anchor: ClassVar[str] = "ap2-ap1-begin-width-diff"


class ADPPeakValuesFeature(SpikeShapeFeature):
    """eFEL ``ADP_peak_values``."""

    efel_name: ClassVar[str] = "ADP_peak_values"
    efel_doc_anchor: ClassVar[str] = "adp-peak-values"


class ADPPeakAmplitudeFeature(SpikeShapeFeature):
    """eFEL ``ADP_peak_amplitude``."""

    efel_name: ClassVar[str] = "ADP_peak_amplitude"
    efel_doc_anchor: ClassVar[str] = "adp-peak-amplitude"


class PhaseslopeMaxFeature(SpikeShapeFeature):
    """eFEL ``phaseslope_max``."""

    efel_name: ClassVar[str] = "phaseslope_max"
    efel_doc_anchor: ClassVar[str] = "phaseslope-max"


class InitburstSahpFeature(SpikeShapeFeature):
    """eFEL ``initburst_sahp``."""

    efel_name: ClassVar[str] = "initburst_sahp"
    efel_doc_anchor: ClassVar[str] = "initburst-sahp"


class InitburstSahpSsseFeature(SpikeShapeFeature):
    """eFEL ``initburst_sahp_ssse``."""

    efel_name: ClassVar[str] = "initburst_sahp_ssse"
    efel_doc_anchor: ClassVar[str] = "initburst-sahp-ssse"


class InitburstSahpVbFeature(SpikeShapeFeature):
    """eFEL ``initburst_sahp_vb``."""

    efel_name: ClassVar[str] = "initburst_sahp_vb"
    efel_doc_anchor: ClassVar[str] = "initburst-sahp-vb"


class MinBetweenPeaksValuesFeature(SpikeShapeFeature):
    """eFEL ``min_between_peaks_values``."""

    efel_name: ClassVar[str] = "min_between_peaks_values"
    efel_doc_anchor: ClassVar[str] = "min-between-peaks-values"


class APAmplitudeDiffFeature(SpikeShapeFeature):
    """eFEL ``AP_amplitude_diff``."""

    efel_name: ClassVar[str] = "AP_amplitude_diff"
    efel_doc_anchor: ClassVar[str] = "ap-amplitude-diff"


class AP1BeginWidthFeature(SpikeShapeFeature):
    """eFEL ``AP1_begin_width``."""

    efel_name: ClassVar[str] = "AP1_begin_width"
    efel_doc_anchor: ClassVar[str] = _AP_BEGIN_WIDTH_DOC_ANCHOR


class AP2BeginWidthFeature(SpikeShapeFeature):
    """eFEL ``AP2_begin_width``."""

    efel_name: ClassVar[str] = "AP2_begin_width"
    efel_doc_anchor: ClassVar[str] = _AP_BEGIN_WIDTH_DOC_ANCHOR


# -------------------------------------------------------------------------
# Subthreshold features
# -------------------------------------------------------------------------


class DecayTimeConstantAfterStimFeature(SubthresholdFeature):
    """eFEL ``decay_time_constant_after_stim``."""

    efel_name: ClassVar[str] = "decay_time_constant_after_stim"
    efel_doc_anchor: ClassVar[str] = "decay-time-constant-after-stim"


class OhmicInputResistanceVbSsseFeature(SubthresholdFeature):
    """eFEL ``ohmic_input_resistance_vb_ssse``."""

    efel_name: ClassVar[str] = "ohmic_input_resistance_vb_ssse"
    efel_doc_anchor: ClassVar[str] = "ohmic-input-resistance-vb-ssse"


class SagAmplitudeFeature(SubthresholdFeature):
    """eFEL ``sag_amplitude``."""

    efel_name: ClassVar[str] = "sag_amplitude"
    efel_doc_anchor: ClassVar[str] = "sag-amplitude"


class SagRatio1Feature(SubthresholdFeature):
    """eFEL ``sag_ratio1``."""

    efel_name: ClassVar[str] = "sag_ratio1"
    efel_doc_anchor: ClassVar[str] = "sag-ratio1"


class SagRatio2Feature(SubthresholdFeature):
    """eFEL ``sag_ratio2``."""

    efel_name: ClassVar[str] = "sag_ratio2"
    efel_doc_anchor: ClassVar[str] = "sag-ratio2"


class VoltageAfterStimFeature(SubthresholdFeature):
    """eFEL ``voltage_after_stim``."""

    efel_name: ClassVar[str] = "voltage_after_stim"
    efel_doc_anchor: ClassVar[str] = "voltage-after-stim"


class VoltageBaseFeature(SubthresholdFeature):
    """eFEL ``voltage_base``."""

    efel_name: ClassVar[str] = "voltage_base"
    efel_doc_anchor: ClassVar[str] = "voltage-base"
    stim_mid: float = stim_mid_field()
    stim_mid_2: float = stim_mid_2_field()


class SteadyStateVoltageStimendFeature(SubthresholdFeature):
    """eFEL ``steady_state_voltage_stimend``."""

    efel_name: ClassVar[str] = "steady_state_voltage_stimend"
    efel_doc_anchor: ClassVar[str] = "steady-state-voltage-stimend"


class SteadyStateHyperFeature(SubthresholdFeature):
    """eFEL ``steady_state_hyper``."""

    efel_name: ClassVar[str] = "steady_state_hyper"
    efel_doc_anchor: ClassVar[str] = "steady-state-hyper"


class SteadyStateVoltageFeature(SubthresholdFeature):
    """eFEL ``steady_state_voltage``."""

    efel_name: ClassVar[str] = "steady_state_voltage"
    efel_doc_anchor: ClassVar[str] = "steady-state-voltage"


class TimeConstantFeature(SubthresholdFeature):
    """eFEL ``time_constant``."""

    efel_name: ClassVar[str] = "time_constant"
    efel_doc_anchor: ClassVar[str] = "time-constant"


class SagTimeConstantFeature(SubthresholdFeature):
    """eFEL ``sag_time_constant``."""

    efel_name: ClassVar[str] = "sag_time_constant"
    efel_doc_anchor: ClassVar[str] = "sag-time-constant"


class MinimumVoltageFeature(SubthresholdFeature):
    """eFEL ``minimum_voltage``."""

    efel_name: ClassVar[str] = "minimum_voltage"
    efel_doc_anchor: ClassVar[str] = "minimum-voltage"


class MaximumVoltageFeature(SubthresholdFeature):
    """eFEL ``maximum_voltage``."""

    efel_name: ClassVar[str] = "maximum_voltage"
    efel_doc_anchor: ClassVar[str] = "maximum-voltage"


class MaximumVoltageFromVoltagebaseFeature(SubthresholdFeature):
    """eFEL ``maximum_voltage_from_voltagebase``."""

    efel_name: ClassVar[str] = "maximum_voltage_from_voltagebase"
    efel_doc_anchor: ClassVar[str] = "maximum-voltage-from-voltagebase"


class VoltageDeflectionVbSsseFeature(SubthresholdFeature):
    """eFEL ``voltage_deflection_vb_ssse``."""

    efel_name: ClassVar[str] = "voltage_deflection_vb_ssse"
    efel_doc_anchor: ClassVar[str] = "voltage-deflection-vb-ssse"


class VoltageDeflectionFeature(SubthresholdFeature):
    """eFEL ``voltage_deflection``."""

    efel_name: ClassVar[str] = "voltage_deflection"
    efel_doc_anchor: ClassVar[str] = "voltage-deflection"


class VoltageDeflectionBeginFeature(SubthresholdFeature):
    """eFEL ``voltage_deflection_begin``."""

    efel_name: ClassVar[str] = "voltage_deflection_begin"
    efel_doc_anchor: ClassVar[str] = "voltage-deflection-begin"


class OhmicInputResistanceFeature(SubthresholdFeature):
    """eFEL ``ohmic_input_resistance``."""

    efel_name: ClassVar[str] = "ohmic_input_resistance"
    efel_doc_anchor: ClassVar[str] = "ohmic-input-resistance"


class SteadyStateCurrentStimendFeature(SubthresholdFeature):
    """eFEL ``steady_state_current_stimend``."""

    efel_name: ClassVar[str] = "steady_state_current_stimend"
    efel_doc_anchor: ClassVar[str] = "steady-state-current-stimend"


class CurrentBaseFeature(SubthresholdFeature):
    """eFEL ``current_base``."""

    efel_name: ClassVar[str] = "current_base"
    efel_doc_anchor: ClassVar[str] = "current-base"


class MultipleDecayTimeConstantAfterStimFeature(SubthresholdFeature):
    """eFEL ``multiple_decay_time_constant_after_stim``."""

    efel_name: ClassVar[str] = "multiple_decay_time_constant_after_stim"
    efel_doc_anchor: ClassVar[str] = "multiple-decay-time-constant-after-stim"


class ImpedanceFeature(SubthresholdFeature):
    """eFEL ``impedance``."""

    efel_name: ClassVar[str] = "impedance"
    efel_doc_anchor: ClassVar[str] = "impedance"


class ActivationTimeConstantFeature(SubthresholdFeature):
    """eFEL ``activation_time_constant``."""

    efel_name: ClassVar[str] = "activation_time_constant"
    efel_doc_anchor: ClassVar[str] = "activation-time-constant"


class DeactivationTimeConstantFeature(SubthresholdFeature):
    """eFEL ``deactivation_time_constant``."""

    efel_name: ClassVar[str] = "deactivation_time_constant"
    efel_doc_anchor: ClassVar[str] = "deactivation-time-constant"


class InactivationTimeConstantFeature(SubthresholdFeature):
    """eFEL ``inactivation_time_constant``."""

    efel_name: ClassVar[str] = "inactivation_time_constant"
    efel_doc_anchor: ClassVar[str] = "inactivation-time-constant"


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

# -- Universal union (all concrete efeatures across all categories) --------

_ALL_FEATURES = (
    ISICVFeature
    | ISILogSlopeFeature
    | SpikecountFeature
    | AdaptationIndexFeature
    | DepolBlockBoolFeature
    | DoubletISIFeature
    | InvFirstISIFeature
    | InvLastISIFeature
    | InvSecondISIFeature
    | InvThirdISIFeature
    | InvTimeToFirstSpikeFeature
    | IrregularityIndexFeature
    | MeanFrequencyFeature
    | NumberInitialSpikesFeature
    | StrictBurstMeanFreqFeature
    | StrictBurstNumberFeature
    | TimeToFirstSpikeFeature
    | TimeToLastSpikeFeature
    | TimeToSecondSpikeFeature
    | InvFourthISIFeature
    | InvFifthISIFeature
    | ISISemilogSlopeFeature
    | ISILogSlopeSkipFeature
    | AdaptationIndex2Feature
    | BurstNumberFeature
    | SingleBurstRatioFeature
    | SpikeCountStimintFeature
    | SpikesPerBurstFeature
    | BurstMeanFreqFeature
    | InterburstVoltageFeature
    | InterburstMinValuesFeature
    | PeakTimeFeature
    | ISIValuesFeature
    | AllISIValuesFeature
    | InvISIValuesFeature
    | InterburstDurationFeature
    | TimeToInterburstMinFeature
    | TimeToPostburstSlowAhpFeature
    | PostburstMinValuesFeature
    | PostburstSlowAhpValuesFeature
    | PostburstFastAhpValuesFeature
    | PostburstAdpPeakValuesFeature
    | TimeToPostburstFastAhpFeature
    | TimeToPostburstAdpPeakFeature
    | SpikesPerBurstDiffFeature
    | SpikesInBurst1Burst2DiffFeature
    | SpikesInBurst1BurstlastDiffFeature
    | Interburst15PercentValuesFeature
    | Interburst20PercentValuesFeature
    | Interburst25PercentValuesFeature
    | Interburst30PercentValuesFeature
    | Interburst40PercentValuesFeature
    | Interburst60PercentValuesFeature
    | Interburst15PercentVoltageFeature
    | AHPDepthFeature
    | AHPTimeFromPeakFeature
    | AP1AmpFeature
    | APAmplitudeFeature
    | APBeginVoltageFeature
    | APBeginWidthFeature
    | APDurationHalfWidthFeature
    | AP2AmpFeature
    | APlastAmpFeature
    | MeanAPAmplitudeFeature
    | APAmplitudeChangeFeature
    | APDurationHalfWidthChangeFeature
    | AP1PeakFeature
    | AP2PeakFeature
    | AP2AP1DiffFeature
    | AP2AP1PeakDiffFeature
    | AmpDropFirstSecondFeature
    | AmpDropFirstLastFeature
    | AmpDropSecondLastFeature
    | MaxAmpDifferenceFeature
    | AHPDepthFromPeakFeature
    | AHP1DepthFromPeakFeature
    | AHP2DepthFromPeakFeature
    | AHPDepthAbsFeature
    | AHPDepthDiffFeature
    | AHPDepthAbsSlowFeature
    | AHPDepthSlowFeature
    | AHPSlowTimeFeature
    | FastAHPFeature
    | FastAHPChangeFeature
    | APRiseTimeFeature
    | APFallTimeFeature
    | APRiseRateFeature
    | APFallRateFeature
    | APRiseRateChangeFeature
    | APFallRateChangeFeature
    | APPeakUpstrokeFeature
    | APPeakDownstrokeFeature
    | APPhaseslopeFeature
    | APWidthFeature
    | APDurationFeature
    | APDurationChangeFeature
    | SpikeHalfWidthFeature
    | AP1WidthFeature
    | AP2WidthFeature
    | APlastWidthFeature
    | MinVoltageBetweenSpikesFeature
    | DepolarizedBaseFeature
    | PeakVoltageFeature
    | APAmplitudeFromVoltagebaseFeature
    | APHeightFeature
    | MinAHPValuesFeature
    | APBeginTimeFeature
    | SpikeWidth2Feature
    | APWidthBetweenThresholdFeature
    | AP2AP1BeginWidthDiffFeature
    | ADPPeakValuesFeature
    | ADPPeakAmplitudeFeature
    | PhaseslopeMaxFeature
    | InitburstSahpFeature
    | InitburstSahpSsseFeature
    | InitburstSahpVbFeature
    | MinBetweenPeaksValuesFeature
    | APAmplitudeDiffFeature
    | AP1BeginWidthFeature
    | AP2BeginWidthFeature
    | DecayTimeConstantAfterStimFeature
    | OhmicInputResistanceVbSsseFeature
    | SagAmplitudeFeature
    | SagRatio1Feature
    | SagRatio2Feature
    | VoltageAfterStimFeature
    | VoltageBaseFeature
    | SteadyStateVoltageStimendFeature
    | SteadyStateHyperFeature
    | SteadyStateVoltageFeature
    | TimeConstantFeature
    | SagTimeConstantFeature
    | MinimumVoltageFeature
    | MaximumVoltageFeature
    | MaximumVoltageFromVoltagebaseFeature
    | VoltageDeflectionVbSsseFeature
    | VoltageDeflectionFeature
    | VoltageDeflectionBeginFeature
    | OhmicInputResistanceFeature
    | SteadyStateCurrentStimendFeature
    | CurrentBaseFeature
    | MultipleDecayTimeConstantAfterStimFeature
    | ImpedanceFeature
    | ActivationTimeConstantFeature
    | DeactivationTimeConstantFeature
    | InactivationTimeConstantFeature
)
EFeatureUnion = Annotated[_ALL_FEATURES, Discriminator("type")]
