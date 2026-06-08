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

from pydantic import Discriminator, Field, PositiveFloat

from obi_one.core.base import OBIBaseModel
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.protocols_and_features.efeatures import (
    ISICV,
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

    # Per-protocol eFEL overrides applied to every feature extracted from this
    # protocol. ``None`` inherits the global :class:`Settings` value; a set value
    # is overridden in turn by a feature that sets the same field
    # (global -> protocol -> feature).
    threshold: float | None = Field(
        default=None,
        title="Threshold",
        description="Per-protocol override of eFEL's ``Threshold`` (spike detection, mV).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    stim_start: float | None = Field(
        default=None,
        title="Stim start",
        description="Per-protocol override of eFEL's ``stim_start`` (ms).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    stim_end: float | None = Field(
        default=None,
        title="Stim end",
        description="Per-protocol override of eFEL's ``stim_end`` (ms).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    strict_stiminterval: bool | None = Field(
        default=None,
        title="Strict stim interval",
        description="Per-protocol override of eFEL's ``strict_stiminterval``.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    interp_step: PositiveFloat | None = Field(
        default=None,
        title="Interpolation step",
        description="Per-protocol override of eFEL's ``interp_step`` (ms).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    derivative_threshold: float | None = Field(
        default=None,
        title="Derivative threshold",
        description="Per-protocol override of eFEL's ``DerivativeThreshold`` (mV/ms).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    def selected_efeatures(self) -> list["EFeature"]:
        """Return every :class:`EFeature` field whose ``extract`` flag is set."""
        out: list[EFeature] = []
        for field_name in type(self).model_fields:
            value = getattr(self, field_name)
            if isinstance(value, EFeature) and value.extract:
                out.append(value)
        return out

    def efel_settings_override(self) -> dict:
        """Build the per-protocol ``efel_settings`` overrides.

        Only fields the user explicitly set (non-``None``) are emitted; each one
        overrides the global eFEL setting for every feature of this protocol, and
        is itself overridden by a feature that sets the same field.
        """
        overrides: dict[str, float | bool] = {}
        if self.threshold is not None:
            overrides["Threshold"] = self.threshold
        if self.stim_start is not None:
            overrides["stim_start"] = self.stim_start
        if self.stim_end is not None:
            overrides["stim_end"] = self.stim_end
        if self.strict_stiminterval is not None:
            overrides["strict_stiminterval"] = self.strict_stiminterval
        if self.interp_step is not None:
            overrides["interp_step"] = self.interp_step
        if self.derivative_threshold is not None:
            overrides["DerivativeThreshold"] = self.derivative_threshold
        return overrides


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


# ---------------------------------------------------------------------------
# Additional protocols giving obi-one a Protocol class for every eCode in
# bluepyefe's ``eCodes`` registry (full bluepyefe coverage). Each subclasses the
# canonical protocol whose curated feature set best fits it and only overrides
# ``name`` (the canonical bluepyefe name), so no fields are duplicated. The
# feature sets are sensible defaults mirroring the analogous protocol -- override
# the fields on a subclass if a protocol needs a different selection, and adjust
# ``name`` if a dataset spells a protocol differently (bluepyefe itself matches
# protocol names case-insensitively). Protocols with no bluepyefe eCode -- noise
# stimuli, ADHP*, APDrop, C1HP, HighResThResp, VacuumPulses -- are not added:
# bluepyefe cannot extract from them.
#
# NOTE on stimulus timing: most eCodes auto-detect their timing, but a few don't.
# ``APThreshold``/``Ramp`` (Ramp eCode) need a stimulus onset (``ton``), which the
# extraction task reads from the NWB current and supplies. ``DeHyperPol`` also
# needs mid-transition points we can't recover, so the task skips it with a
# warning (see ``_TON_ONLY_ECODES`` / ``_TIMING_UNSUPPORTED_ECODES`` in
# ``task.py``).
# ---------------------------------------------------------------------------


# Depolarising step / spiking protocols -> full IDrest feature set.
class IDRest(IDrest):
    name: ClassVar[str] = "IDRest"


class GenericStep(IDrest):
    name: ClassVar[str] = "GenericStep"


class C1step(IDrest):
    name: ClassVar[str] = "C1step"


class Delta(IDrest):
    name: ClassVar[str] = "Delta"


class IDdepol(IDrest):
    name: ClassVar[str] = "IDdepol"


class IRdepol(IDrest):
    name: ClassVar[str] = "IRdepol"


class SponAPs(IDrest):
    name: ClassVar[str] = "SponAPs"


class SpikeRec(IDrest):
    name: ClassVar[str] = "SpikeRec"


# Threshold-search / sparse-spiking protocols -> minimal IDthresh feature set.
class IDThreshold(IDthresh):
    name: ClassVar[str] = "IDThreshold"


class Spontaneous(IDthresh):
    name: ClassVar[str] = "Spontaneous"


class SineSpec(IDthresh):
    name: ClassVar[str] = "SineSpec"


# Hyperpolarising protocol -> IDhyperpol feature set.
class IRhyperpol(IDhyperpol):
    name: ClassVar[str] = "IRhyperpol"


# Ramp / AP-threshold protocols (bluepyefe ``Ramp`` eCode) -> APWaveform set.
class APThreshold(APWaveform):
    name: ClassVar[str] = "APThreshold"


class Ramp(APWaveform):
    name: ClassVar[str] = "Ramp"


# Further step-family protocols (bluepyefe ``Step`` eCode) -> full IDrest set.
class FirePattern(IDrest):
    name: ClassVar[str] = "FirePattern"


class StartHold(IDrest):
    name: ClassVar[str] = "StartHold"


class StartNoHold(IDrest):
    name: ClassVar[str] = "StartNoHold"


# Spontaneous-activity step variants -> minimal IDthresh set.
class SpontaneousNoHold(IDthresh):
    name: ClassVar[str] = "SpontaneousNoHold"


class SponHold30(IDthresh):
    name: ClassVar[str] = "SponHold30"


class SponNoHold30(IDthresh):
    name: ClassVar[str] = "SponNoHold30"


class SpontHold30(IDthresh):
    name: ClassVar[str] = "SpontHold30"


class SpontNoHold30(IDthresh):
    name: ClassVar[str] = "SpontNoHold30"


# Two-step (HyperDePol/DeHyperPol) and Cheops eCodes -> full IDrest set
# (their depolarising phases elicit spikes).
class HyperDePol(IDrest):
    name: ClassVar[str] = "HyperDePol"


class DeHyperPol(IDrest):
    name: ClassVar[str] = "DeHyperPol"


class PosCheops(IDrest):
    name: ClassVar[str] = "PosCheops"


class NegCheops(IDrest):
    name: ClassVar[str] = "NegCheops"


# Discriminated union over every concrete Protocol so pydantic can round-trip
# ``ProtocolAndFeatureSelection.protocols`` (a ``list[ProtocolUnion]``) by the
# ``type`` literal stamped on each subclass by :class:`OBIBaseModel`.
ProtocolUnion = Annotated[
    IDrest
    | IDthresh
    | IV
    | APWaveform
    | SAHP
    | IDhyperpol
    | IDRest
    | GenericStep
    | C1step
    | Delta
    | IDdepol
    | IRdepol
    | SponAPs
    | SpikeRec
    | IDThreshold
    | Spontaneous
    | SineSpec
    | IRhyperpol
    | APThreshold
    | Ramp
    | FirePattern
    | StartHold
    | StartNoHold
    | SpontaneousNoHold
    | SponHold30
    | SponNoHold30
    | SpontHold30
    | SpontNoHold30
    | HyperDePol
    | DeHyperPol
    | PosCheops
    | NegCheops,
    Discriminator("type"),
]


PROTOCOL_CATALOGUE: tuple[type[Protocol], ...] = (
    IDrest,
    IDthresh,
    IV,
    APWaveform,
    SAHP,
    IDhyperpol,
    IDRest,
    GenericStep,
    C1step,
    Delta,
    IDdepol,
    IRdepol,
    SponAPs,
    SpikeRec,
    IDThreshold,
    Spontaneous,
    SineSpec,
    IRhyperpol,
    APThreshold,
    Ramp,
    FirePattern,
    StartHold,
    StartNoHold,
    SpontaneousNoHold,
    SponHold30,
    SponNoHold30,
    SpontHold30,
    SpontNoHold30,
    HyperDePol,
    DeHyperPol,
    PosCheops,
    NegCheops,
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
