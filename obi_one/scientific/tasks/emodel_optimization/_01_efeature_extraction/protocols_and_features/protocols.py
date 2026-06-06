"""Ephys protocol Pydantic models.

Each :class:`Protocol` subclass declares its valid eFEL features as typed
Pydantic fields (one per feature subclass from :mod:`.efeatures`), plus the
per-protocol timing (``ton``/``toff``/``tmid``/``tmid2``) and ``amplitudes``
inherited from the base. Whether each feature is actually extracted is decided
by its own ``extract`` flag, surfaced through :meth:`Protocol.selected_efeatures`.

:data:`ProtocolUnion` is the discriminated union used by
``ProtocolAndFeatureSelection.protocols``.
"""

from typing import Annotated, ClassVar

from pydantic import Discriminator, Field

from obi_one.core.base import OBIBaseModel
from obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.protocols_and_features.efeatures import (
    AdaptationIndex,
    AHPDepth,
    AHPTimeFromPeak,
    AP1Amp,
    APAmplitude,
    APBeginVoltage,
    APBeginWidth,
    APDurationHalfWidth,
    DecayTimeConstantAfterStim,
    DepolBlockBool,
    DoubletISI,
    EFeature,
    InvFirstISI,
    InvLastISI,
    InvSecondISI,
    InvThirdISI,
    InvTimeToFirstSpike,
    IrregularityIndex,
    ISICV,
    ISILogSlope,
    MeanFrequency,
    MinAHPValues,
    NumberInitialSpikes,
    OhmicInputResistanceVbSsse,
    SagAmplitude,
    SagRatio1,
    SagRatio2,
    Spikecount,
    StrictBurstMeanFreq,
    StrictBurstNumber,
    TimeToFirstSpike,
    TimeToLastSpike,
    VoltageAfterStim,
    VoltageBase,
)


class Protocol(OBIBaseModel):
    """Base class for ephys protocols.

    Subclasses declare ``name`` (the protocol identifier used in bluepyefe
    target rows and the recordings' NWB metadata) and one typed field per
    valid eFEL feature. Protocol-level metadata (stimulus timing, step
    amplitudes, liquid junction potential) is read from each
    ``ElectricalCellRecording``'s NWB asset at task execution time, so it
    isn't exposed here as a user parameter.
    """

    name: ClassVar[str]

    def selected_efeatures(self) -> list[EFeature]:
        """Return every :class:`EFeature` field whose ``extract`` flag is set."""
        out: list[EFeature] = []
        for field_name in type(self).model_fields:
            value = getattr(self, field_name)
            if isinstance(value, EFeature) and value.extract:
                out.append(value)
        return out


class IDrest(Protocol):
    name: ClassVar[str] = "IDrest"

    spikecount: Spikecount = Field(default_factory=Spikecount)
    depol_block_bool: DepolBlockBool = Field(default_factory=DepolBlockBool)
    voltage_base: VoltageBase = Field(default_factory=VoltageBase)
    voltage_after_stim: VoltageAfterStim = Field(default_factory=VoltageAfterStim)
    mean_frequency: MeanFrequency = Field(default_factory=MeanFrequency)
    time_to_first_spike: TimeToFirstSpike = Field(default_factory=TimeToFirstSpike)
    time_to_last_spike: TimeToLastSpike = Field(default_factory=TimeToLastSpike)
    inv_time_to_first_spike: InvTimeToFirstSpike = Field(default_factory=InvTimeToFirstSpike)
    inv_first_isi: InvFirstISI = Field(default_factory=InvFirstISI)
    inv_second_isi: InvSecondISI = Field(default_factory=InvSecondISI)
    inv_third_isi: InvThirdISI = Field(default_factory=InvThirdISI)
    inv_last_isi: InvLastISI = Field(default_factory=InvLastISI)
    isi_cv: ISICV = Field(default_factory=ISICV)
    isi_log_slope: ISILogSlope = Field(default_factory=ISILogSlope)
    doublet_isi: DoubletISI = Field(default_factory=DoubletISI)
    ahp_depth: AHPDepth = Field(default_factory=AHPDepth)
    ahp_time_from_peak: AHPTimeFromPeak = Field(default_factory=AHPTimeFromPeak)
    min_ahp_values: MinAHPValues = Field(default_factory=MinAHPValues)
    strict_burst_number: StrictBurstNumber = Field(default_factory=StrictBurstNumber)
    strict_burst_mean_freq: StrictBurstMeanFreq = Field(default_factory=StrictBurstMeanFreq)
    number_initial_spikes: NumberInitialSpikes = Field(default_factory=NumberInitialSpikes)
    irregularity_index: IrregularityIndex = Field(default_factory=IrregularityIndex)
    adaptation_index: AdaptationIndex = Field(default_factory=AdaptationIndex)


class IDthresh(Protocol):
    name: ClassVar[str] = "IDthresh"

    spikecount: Spikecount = Field(default_factory=Spikecount)
    mean_frequency: MeanFrequency = Field(default_factory=MeanFrequency)
    voltage_base: VoltageBase = Field(default_factory=VoltageBase)
    voltage_after_stim: VoltageAfterStim = Field(default_factory=VoltageAfterStim)
    ahp_depth: AHPDepth = Field(default_factory=AHPDepth)


class IV(Protocol):
    name: ClassVar[str] = "IV"

    voltage_base: VoltageBase = Field(default_factory=VoltageBase)
    ohmic_input_resistance_vb_ssse: OhmicInputResistanceVbSsse = Field(
        default_factory=OhmicInputResistanceVbSsse,
    )
    sag_amplitude: SagAmplitude = Field(default_factory=SagAmplitude)
    sag_ratio1: SagRatio1 = Field(default_factory=SagRatio1)
    sag_ratio2: SagRatio2 = Field(default_factory=SagRatio2)
    decay_time_constant_after_stim: DecayTimeConstantAfterStim = Field(
        default_factory=DecayTimeConstantAfterStim,
    )


class APWaveform(Protocol):
    name: ClassVar[str] = "APWaveform"

    ap_amplitude: APAmplitude = Field(default_factory=APAmplitude)
    ap1_amp: AP1Amp = Field(default_factory=AP1Amp)
    ap_duration_half_width: APDurationHalfWidth = Field(default_factory=APDurationHalfWidth)
    ahp_depth: AHPDepth = Field(default_factory=AHPDepth)
    ap_begin_voltage: APBeginVoltage = Field(default_factory=APBeginVoltage)
    ap_begin_width: APBeginWidth = Field(default_factory=APBeginWidth)


class SAHP(Protocol):
    name: ClassVar[str] = "sAHP"

    mean_frequency: MeanFrequency = Field(default_factory=MeanFrequency)
    voltage_base: VoltageBase = Field(default_factory=VoltageBase)
    depol_block_bool: DepolBlockBool = Field(default_factory=DepolBlockBool)
    ahp_depth: AHPDepth = Field(default_factory=AHPDepth)
    ahp_time_from_peak: AHPTimeFromPeak = Field(default_factory=AHPTimeFromPeak)


class IDhyperpol(Protocol):
    name: ClassVar[str] = "IDhyperpol"

    mean_frequency: MeanFrequency = Field(default_factory=MeanFrequency)
    voltage_base: VoltageBase = Field(default_factory=VoltageBase)
    depol_block_bool: DepolBlockBool = Field(default_factory=DepolBlockBool)


# Discriminated union over every concrete Protocol so pydantic can round-trip
# ``ProtocolAndFeatureSelection.protocols`` (a ``list[ProtocolUnion]``) by the
# ``type`` literal stamped on each subclass by :class:`OBIBaseModel`.
ProtocolUnion = Annotated[
    IDrest | IDthresh | IV | APWaveform | SAHP | IDhyperpol,
    Discriminator("type"),
]


PROTOCOL_CATALOGUE: tuple[type[Protocol], ...] = (
    IDrest,
    IDthresh,
    IV,
    APWaveform,
    SAHP,
    IDhyperpol,
)


def available_features_by_protocol_name() -> dict[str, list[str]]:
    """Catalogue as ``{protocol_name: [efel_feature_name, ...]}``.

    Mirrors the legacy ``EFEATURE_CATALOGUE_BY_PROTOCOL`` shape so the
    frontend's ``available_efeatures_by_protocol`` UI hint stays unchanged.
    Derived by introspecting each protocol class's :class:`EFeature` fields.
    """
    result: dict[str, list[str]] = {}
    for p_cls in PROTOCOL_CATALOGUE:
        names: list[str] = []
        for field_info in p_cls.model_fields.values():
            ann = field_info.annotation
            if isinstance(ann, type) and issubclass(ann, EFeature):
                names.append(ann.efel_name)
        result[p_cls.name] = names
    return result
