"""eFEL feature models: the shared base, then one class per feature.

:class:`EFeature` is the base, carrying what the user can tune for a single
feature: whether to extract it, its weight and tolerance, and per-feature eFEL
detection settings. It is never used directly.

Below it, a category intermediate groups its subclasses following the eFEL
documentation (https://efel.readthedocs.io/en/latest/eFeatures.html) — spike
event, spike shape, subthreshold — and each concrete class fixes ``efel_name``.

The unions at the bottom are the features valid for each protocol, so a
protocol's ``features`` tuple can only hold features it can actually extract.

The feature sets mirror BluePyEfe's ``PROTOCOL_EFEATURES`` but are held here so
obi-one never imports them at runtime, keeping the schema buildable without
BluePyEfe's unreleased ``features_per_ecode`` branch installed.

Source of truth, kept in sync by hand:

* eCode registry -- https://github.com/openbraininstitute/BluePyEfe/blob/
  ce16c359fa5ba36525355df677fdabe82b850490/bluepyefe/ecode/__init__.py
* feature sets -- https://github.com/openbraininstitute/BluePyEfe/pull/23
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


# -------------------------------------------------------------------------
# Valid features per protocol: class tuples and discriminated unions
# -------------------------------------------------------------------------

SPIKING_STEP_FEATURES: tuple[type[EFeature], ...] = (
    SpikecountFeature,
    DepolBlockBoolFeature,
    VoltageBaseFeature,
    VoltageAfterStimFeature,
    MeanFrequencyFeature,
    TimeToFirstSpikeFeature,
    TimeToLastSpikeFeature,
    InvTimeToFirstSpikeFeature,
    InvFirstISIFeature,
    InvSecondISIFeature,
    InvThirdISIFeature,
    InvLastISIFeature,
    ISICVFeature,
    ISILogSlopeFeature,
    DoubletISIFeature,
    AHPDepthFeature,
    AHPTimeFromPeakFeature,
    StrictBurstNumberFeature,
    StrictBurstMeanFreqFeature,
    NumberInitialSpikesFeature,
    IrregularityIndexFeature,
    AdaptationIndexFeature,
)

_SPIKING_STEP = (
    SpikecountFeature
    | DepolBlockBoolFeature
    | VoltageBaseFeature
    | VoltageAfterStimFeature
    | MeanFrequencyFeature
    | TimeToFirstSpikeFeature
    | TimeToLastSpikeFeature
    | InvTimeToFirstSpikeFeature
    | InvFirstISIFeature
    | InvSecondISIFeature
    | InvThirdISIFeature
    | InvLastISIFeature
    | ISICVFeature
    | ISILogSlopeFeature
    | DoubletISIFeature
    | AHPDepthFeature
    | AHPTimeFromPeakFeature
    | StrictBurstNumberFeature
    | StrictBurstMeanFreqFeature
    | NumberInitialSpikesFeature
    | IrregularityIndexFeature
    | AdaptationIndexFeature
)
SpikingStepFeatureUnion = Annotated[_SPIKING_STEP, Discriminator("type")]

THRESHOLD_STEP_FEATURES: tuple[type[EFeature], ...] = (
    SpikecountFeature,
    MeanFrequencyFeature,
    VoltageBaseFeature,
    VoltageAfterStimFeature,
    AHPDepthFeature,
)

_THRESHOLD_STEP = (
    SpikecountFeature
    | MeanFrequencyFeature
    | VoltageBaseFeature
    | VoltageAfterStimFeature
    | AHPDepthFeature
)
ThresholdStepFeatureUnion = Annotated[_THRESHOLD_STEP, Discriminator("type")]

AP_WAVEFORM_FEATURES: tuple[type[EFeature], ...] = (
    APAmplitudeFeature,
    AP1AmpFeature,
    APDurationHalfWidthFeature,
    AHPDepthFeature,
    APBeginVoltageFeature,
    APBeginWidthFeature,
)

_AP_WAVEFORM = (
    APAmplitudeFeature
    | AP1AmpFeature
    | APDurationHalfWidthFeature
    | AHPDepthFeature
    | APBeginVoltageFeature
    | APBeginWidthFeature
)
APWaveformFeatureUnion = Annotated[_AP_WAVEFORM, Discriminator("type")]

IV_FEATURES: tuple[type[EFeature], ...] = (
    VoltageBaseFeature,
    OhmicInputResistanceVbSsseFeature,
    SagAmplitudeFeature,
    SagRatio1Feature,
    SagRatio2Feature,
    DecayTimeConstantAfterStimFeature,
)

_IV = (
    VoltageBaseFeature
    | OhmicInputResistanceVbSsseFeature
    | SagAmplitudeFeature
    | SagRatio1Feature
    | SagRatio2Feature
    | DecayTimeConstantAfterStimFeature
)
IVFeatureUnion = Annotated[_IV, Discriminator("type")]

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

SUBTHRESHOLD_FEATURES: tuple[type[EFeature], ...] = (
    VoltageBaseFeature,
    OhmicInputResistanceVbSsseFeature,
)

_SUBTHRESHOLD = VoltageBaseFeature | OhmicInputResistanceVbSsseFeature
SubthresholdFeatureUnion = Annotated[_SUBTHRESHOLD, Discriminator("type")]
