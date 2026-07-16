"""Ephys protocol Pydantic models.

Each :class:`Protocol` subclass declares its valid eFEL features as typed
Pydantic fields (one per feature subclass from :mod:`.efeatures`), plus
user-editable stimulus timing (``ton``/``toff``/``tmid``/``tmid2``) and
liquid junction potential (``ljp``) on the base. Whether each feature is
actually extracted is decided by its own ``extract`` flag, surfaced through
:meth:`Protocol.selected_efeatures`.

:data:`ProtocolUnion` is the discriminated union used by
``ProtocolAndFeatureSelection.protocols``.
"""

from typing import Annotated, ClassVar

from pydantic import Discriminator, Field

from obi_one.core.base import OBIBaseModel
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.protocols_and_features.efeatures import (  # noqa: E501
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
    valid eFEL feature. Protocol-level stimulus timing (``ton``/``toff``/
    ``tmid``/``tmid2``) and liquid junction potential (``ljp``) can be
    user-specified; when left at ``0.0`` they are auto-detected from each
    ``ElectricalCellRecording``'s NWB asset at task execution time.

    Per-protocol custom eFEL settings are available via
    ``custom_efel_settings`` (the "Add setting" picker in the UI). Per-feature
    eFEL detection knobs (threshold, strict_stiminterval, interp_step,
    stim_start, stim_end) live on :class:`EFeature` and override the protocol
    level.
    """

    name: ClassVar[str]

    # ------------------------------------------------------------------
    # Stimulus timing & LJP — user-editable, 0.0 = auto-detect from NWB
    # ------------------------------------------------------------------
    ton: float = Field(
        default=0.0,
        title="Stimulus onset (ton)",
        description="Stimulus onset time (ms). Set to 0 to auto-detect from the NWB.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    toff: float = Field(
        default=0.0,
        title="Stimulus end (toff)",
        description="Stimulus end time (ms). Set to 0 to auto-detect from the NWB.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    tmid: float = Field(
        default=0.0,
        title="Mid-transition 1 (tmid)",
        description=(
            "First mid-transition point for two-step protocols (ms). Set to 0 to auto-detect."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    tmid2: float = Field(
        default=0.0,
        title="Mid-transition 2 (tmid2)",
        description=(
            "Second mid-transition point for two-step protocols (ms). Set to 0 to auto-detect."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    ljp: float = Field(
        default=0.0,
        title="Liquid junction potential (LJP)",
        description=(
            "Liquid junction potential correction (mV). Set to 0 to use the recording's LJP."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLIVOLTS,
        },
    )

    # ------------------------------------------------------------------
    # Per-protocol extraction amplitudes (threshold-based / relative mode)
    # ------------------------------------------------------------------
    extraction_amplitudes: float | list[float] = Field(
        default=0.0,
        title="Extraction amplitudes",
        description=(
            "Amplitudes (% of rheobase) to extract from this protocol. Only used"
            " when global ``threshold_based`` is enabled. Set to 0 to fall back to"
            " NWB-discovered amplitudes (which may be in absolute nA — a warning"
            " is logged)."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    # ------------------------------------------------------------------
    # Validation hold-out (per-protocol)
    # ------------------------------------------------------------------
    validation: bool = Field(
        default=False,
        title="Validation protocol",
        description=(
            "If True, this protocol's features are extracted but marked as"
            " validation-only in the output JSON so the optimiser excludes them."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    # ------------------------------------------------------------------
    # Custom eFEL settings (picker)
    # ------------------------------------------------------------------
    custom_efel_settings: dict[str, float | bool] = Field(
        default_factory=dict,
        title="Custom eFEL settings",
        description=(
            "Per-protocol eFEL settings applied to all features of this protocol."
            " Keys are eFEL setting names. Overridden by per-feature settings."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY},
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

        Returns only the ``custom_efel_settings`` dict (or empty). Per-feature
        settings override these values in the cascade (global -> protocol ->
        feature).
        """
        return dict(self.custom_efel_settings)

    def timing_override(self) -> dict:
        """Return user-set timing/LJP fields as a dict (0.0 values omitted).

        Keys are ``ton``, ``toff``, ``tmid``, ``tmid2``, ``ljp`` — only
        non-zero values are included. Used by the extraction task to
        override auto-detected NWB timing.
        """
        result: dict[str, float] = {}
        for key in ("ton", "toff", "tmid", "tmid2", "ljp"):
            value = getattr(self, key)
            if value:
                result[key] = value
        return result


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


# Threshold-search / sparse-spiking protocols -> minimal IDthresh feature set.
class IDThreshold(IDthresh):
    name: ClassVar[str] = "IDThreshold"


class Spontaneous(IDthresh):
    name: ClassVar[str] = "Spontaneous"


class SineSpec(IDthresh):
    name: ClassVar[str] = "SineSpec"


# SpikeRec's eCode sets ``toff`` at the very end of the trace, which breaks
# step-only features such as ``depol_block_bool`` (their stim-end window is
# empty). Give it the minimal IDthresh set -- whose features degrade gracefully
# -- rather than the full IDrest set.
class SpikeRec(IDthresh):
    name: ClassVar[str] = "SpikeRec"


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
