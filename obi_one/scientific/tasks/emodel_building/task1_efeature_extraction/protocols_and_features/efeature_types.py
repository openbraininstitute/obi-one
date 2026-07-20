"""One Pydantic class per eFEL feature, grouped by eFEL category.

Mirrors the protocol hierarchy: a category intermediate fixes ``category``,
and each concrete class fixes ``efel_name``. Every editable knob (weight,
tolerance, per-feature eFEL settings) is inherited from :class:`EFeature`.

The unions at the bottom are the features valid for each protocol, so a
protocol's ``features`` tuple can only hold features it can actually extract.
The category intermediates give the UI its grouping.

These mirror BluePyEfe's ``PROTOCOL_EFEATURES`` but are held here so obi-one
never imports them at runtime, keeping the schema buildable without
BluePyEfe's unreleased ``features_per_ecode`` branch installed.

Source of truth, kept in sync by hand:

* eCode registry -- https://github.com/openbraininstitute/BluePyEfe/blob/
  ce16c359fa5ba36525355df677fdabe82b850490/bluepyefe/ecode/__init__.py
* feature sets -- https://github.com/openbraininstitute/BluePyEfe/pull/23
"""

import abc
from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.efeatures import (  # noqa: E501
    EFeature,
)


class SpikeEventFeature(EFeature, abc.ABC):
    """eFEL spike-event features."""

    category: str = "Spike event"


class SpikeShapeFeature(EFeature, abc.ABC):
    """eFEL spike-shape features."""

    category: str = "Spike shape"


class SubthresholdFeature(EFeature, abc.ABC):
    """eFEL subthreshold features."""

    category: str = "Subthreshold"


# -------------------------------------------------------------------------
# Spike event features
# -------------------------------------------------------------------------


class ISICVFeature(SpikeEventFeature):
    """eFEL ``ISI_CV``."""

    efel_name: str = "ISI_CV"


class ISILogSlopeFeature(SpikeEventFeature):
    """eFEL ``ISI_log_slope``."""

    efel_name: str = "ISI_log_slope"


class SpikecountFeature(SpikeEventFeature):
    """eFEL ``Spikecount``."""

    efel_name: str = "Spikecount"


class AdaptationIndexFeature(SpikeEventFeature):
    """eFEL ``adaptation_index``."""

    efel_name: str = "adaptation_index"


class DepolBlockBoolFeature(SpikeEventFeature):
    """eFEL ``depol_block_bool``."""

    efel_name: str = "depol_block_bool"


class DoubletISIFeature(SpikeEventFeature):
    """eFEL ``doublet_ISI``."""

    efel_name: str = "doublet_ISI"


class InvFirstISIFeature(SpikeEventFeature):
    """eFEL ``inv_first_ISI``."""

    efel_name: str = "inv_first_ISI"


class InvLastISIFeature(SpikeEventFeature):
    """eFEL ``inv_last_ISI``."""

    efel_name: str = "inv_last_ISI"


class InvSecondISIFeature(SpikeEventFeature):
    """eFEL ``inv_second_ISI``."""

    efel_name: str = "inv_second_ISI"


class InvThirdISIFeature(SpikeEventFeature):
    """eFEL ``inv_third_ISI``."""

    efel_name: str = "inv_third_ISI"


class InvTimeToFirstSpikeFeature(SpikeEventFeature):
    """eFEL ``inv_time_to_first_spike``."""

    efel_name: str = "inv_time_to_first_spike"


class IrregularityIndexFeature(SpikeEventFeature):
    """eFEL ``irregularity_index``."""

    efel_name: str = "irregularity_index"


class MeanFrequencyFeature(SpikeEventFeature):
    """eFEL ``mean_frequency``."""

    efel_name: str = "mean_frequency"


class NumberInitialSpikesFeature(SpikeEventFeature):
    """eFEL ``number_initial_spikes``."""

    efel_name: str = "number_initial_spikes"


class StrictBurstMeanFreqFeature(SpikeEventFeature):
    """eFEL ``strict_burst_mean_freq``."""

    efel_name: str = "strict_burst_mean_freq"


class StrictBurstNumberFeature(SpikeEventFeature):
    """eFEL ``strict_burst_number``."""

    efel_name: str = "strict_burst_number"


class TimeToFirstSpikeFeature(SpikeEventFeature):
    """eFEL ``time_to_first_spike``."""

    efel_name: str = "time_to_first_spike"


class TimeToLastSpikeFeature(SpikeEventFeature):
    """eFEL ``time_to_last_spike``."""

    efel_name: str = "time_to_last_spike"


# -------------------------------------------------------------------------
# Spike shape features
# -------------------------------------------------------------------------


class AHPDepthFeature(SpikeShapeFeature):
    """eFEL ``AHP_depth``."""

    efel_name: str = "AHP_depth"


class AHPTimeFromPeakFeature(SpikeShapeFeature):
    """eFEL ``AHP_time_from_peak``."""

    efel_name: str = "AHP_time_from_peak"


class AP1AmpFeature(SpikeShapeFeature):
    """eFEL ``AP1_amp``."""

    efel_name: str = "AP1_amp"


class APAmplitudeFeature(SpikeShapeFeature):
    """eFEL ``AP_amplitude``."""

    efel_name: str = "AP_amplitude"


class APBeginVoltageFeature(SpikeShapeFeature):
    """eFEL ``AP_begin_voltage``."""

    efel_name: str = "AP_begin_voltage"


class APBeginWidthFeature(SpikeShapeFeature):
    """eFEL ``AP_begin_width``."""

    efel_name: str = "AP_begin_width"


class APDurationHalfWidthFeature(SpikeShapeFeature):
    """eFEL ``AP_duration_half_width``."""

    efel_name: str = "AP_duration_half_width"


# -------------------------------------------------------------------------
# Subthreshold features
# -------------------------------------------------------------------------


class DecayTimeConstantAfterStimFeature(SubthresholdFeature):
    """eFEL ``decay_time_constant_after_stim``."""

    efel_name: str = "decay_time_constant_after_stim"


class OhmicInputResistanceVbSsseFeature(SubthresholdFeature):
    """eFEL ``ohmic_input_resistance_vb_ssse``."""

    efel_name: str = "ohmic_input_resistance_vb_ssse"


class SagAmplitudeFeature(SubthresholdFeature):
    """eFEL ``sag_amplitude``."""

    efel_name: str = "sag_amplitude"


class SagRatio1Feature(SubthresholdFeature):
    """eFEL ``sag_ratio1``."""

    efel_name: str = "sag_ratio1"


class SagRatio2Feature(SubthresholdFeature):
    """eFEL ``sag_ratio2``."""

    efel_name: str = "sag_ratio2"


class VoltageAfterStimFeature(SubthresholdFeature):
    """eFEL ``voltage_after_stim``."""

    efel_name: str = "voltage_after_stim"


class VoltageBaseFeature(SubthresholdFeature):
    """eFEL ``voltage_base``."""

    efel_name: str = "voltage_base"


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
