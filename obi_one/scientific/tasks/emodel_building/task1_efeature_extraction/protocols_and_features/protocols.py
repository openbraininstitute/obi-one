"""Ephys protocol models, one class per protocol.

The hierarchy has three levels:

* :class:`Protocol` — the base, holding the fields every protocol shares (LJP,
  amplitudes, role flags, feature selection).
* a *shape* intermediate per BluePyEfe eCode class (:class:`StepShapeProtocol`,
  :class:`SAHPShapeProtocol`, …). The stimulus shape decides which timing
  parameters exist, so each intermediate fixes ``ecode`` and declares exactly
  the timing fields its eCode reads — ``ton``/``toff`` for a plain step, all
  four for sAHP, ``ton`` alone for a ramp, none at all for SpikeRec. A protocol
  therefore has no timing field it cannot use, and the schema tells the
  frontend which inputs to render without a separate list.
* a concrete class per protocol (:class:`IDRestProtocol`, :class:`IVProtocol`,
  …), which fixes ``protocol_name`` and narrows ``features`` to its own
  feature union.

Everything is declared statically here rather than read from BluePyEfe at
runtime: the eCode-to-shape mapping is mirrored from ``bluepyefe.ecode.eCodes``
and the feature classes live in :mod:`.efeatures`. That keeps the schema (and
so the UI) buildable without BluePyEfe's unreleased ``features_per_ecode``
branch installed.

The same eCode can back protocols with very different feature sets — IDrest,
IV and APWaveform are all ``Step`` — which is why the feature set belongs to
the concrete protocol rather than to the shape.
"""

import abc
from typing import Annotated, Any, ClassVar, get_args

from pydantic import Discriminator, Field

from obi_one.core.base import OBIBaseModel
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features import (  # noqa: E501
    efeatures,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.efeatures import (  # noqa: E501
    EFeature,
)


def _timing_field(title: str, description: str) -> Any:
    """Build a stimulus-timing field (ms); 0.0 means auto-detect from the NWB."""
    return Field(
        default=0.0,
        title=title,
        description=description,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )


def ton_field() -> Any:
    """Stimulus onset, declared by shapes whose eCode reads ``ton``."""
    return _timing_field(
        "Stimulus onset (ton)",
        "Stimulus onset time (ms). Set to 0 to auto-detect from the NWB.",
    )


def toff_field() -> Any:
    """Stimulus end, declared by shapes whose eCode reads ``toff``."""
    return _timing_field(
        "Stimulus end (toff)",
        "Stimulus end time (ms). Set to 0 to auto-detect from the NWB.",
    )


def tmid_field() -> Any:
    """First mid-transition, declared by two-step shapes."""
    return _timing_field(
        "Mid-transition 1 (tmid)",
        "First mid-transition point for two-step protocols (ms). Set to 0 to auto-detect.",
    )


def tmid2_field() -> Any:
    """Second mid-transition, declared by the sAHP shape."""
    return _timing_field(
        "Mid-transition 2 (tmid2)",
        "Second mid-transition point for two-step protocols (ms). Set to 0 to auto-detect.",
    )


def _features_field(feature_classes: tuple[type[EFeature], ...]) -> Any:
    """Build a protocol's ``features`` field, defaulting to all of its features.

    Each concrete protocol narrows the annotation to its own feature union, so
    the tuple the UI fills in can only contain features that protocol can
    extract.
    """
    return Field(
        default_factory=lambda: tuple(cls() for cls in feature_classes),
        title="Features",
        description=(
            "eFEL features valid for this protocol. Each carries its own"
            " ``extract`` flag, weight, tolerance and eFEL setting overrides."
        ),
    )


class Protocol(OBIBaseModel, abc.ABC):
    """Base class for every ephys protocol.

    Subclasses supply the static description of the protocol through class
    variables; instances carry only what the user can edit.

    Protocol-level stimulus timing (``ton``/``toff``/``tmid``/``tmid2``) and
    liquid junction potential (``ljp``) may be user-specified; when left at
    ``0.0`` they are auto-detected from each ``ElectricalCellRecording``'s NWB
    asset at task execution time.

    Per-feature eFEL detection knobs (threshold, strict_stiminterval,
    interp_step, stim_start, stim_end) live on :class:`EFeature` and override
    the global-level settings.
    """

    # -- static description, set by the shape intermediate / concrete class ---

    protocol_name: ClassVar[str] = "Step"
    """Name of the BluePyEfe protocol name class implementing this stimulus shape."""

    # ------------------------------------------------------------------
    # LJP — a property of the recording, so it applies to every shape. The
    # stimulus timing fields are declared by the shape intermediates, since
    # which ones exist depends on the protocol
    # shape (eCode) and thus the protocol class.
    # ------------------------------------------------------------------
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
    # Per-protocol role flags (Rin, RMP, Rheobase)
    # ------------------------------------------------------------------
    is_rin_protocol: bool = Field(
        default=False,
        title="Use as R_in protocol",
        description=(
            "If True, this protocol is used to compute input resistance."
            " Automatically adds ``ohmic_input_resistance_vb_ssse`` to features."
            " Only relevant when ``threshold_based`` is enabled."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    rin_amplitude: float = Field(
        default=-20.0,
        title="R_in amplitude (%)",
        description=(
            "Amplitude (% of rheobase) for the R_in measurement."
            " Only used when ``is_rin_protocol`` is True. Default: -20%."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    is_rmp_protocol: bool = Field(
        default=False,
        title="Use as RMP protocol",
        description=(
            "If True, this protocol is used to compute resting membrane potential."
            " Automatically adds ``voltage_base`` to features."
            " Only relevant when ``threshold_based`` is enabled."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    rmp_amplitude: float = Field(
        default=0.0,
        title="RMP amplitude (%)",
        description=(
            "Amplitude (% of rheobase) for the RMP measurement."
            " Only used when ``is_rmp_protocol`` is True. Default: 0%."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    is_rheobase_protocol: bool = Field(
        default=False,
        title="Use for rheobase",
        description=(
            "If True, this protocol is used to estimate rheobase (lowest amplitude"
            " inducing at least 1 spike). Typically IDthresh or IDThreshold."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    # ------------------------------------------------------------------
    # Features — keyed by eFEL feature name
    # ------------------------------------------------------------------
    features: tuple[EFeature, ...] = Field(
        default=(),
        title="Features",
        description=(
            "eFEL features valid for this protocol. Concrete protocols narrow this"
            " to their own feature union, so it can only hold features the protocol"
            " can actually extract."
        ),
    )

    @classmethod
    def feature_classes(cls) -> tuple[type[EFeature], ...]:
        """Return the feature classes this protocol's ``features`` union allows.

        Read off the annotation rather than kept in a parallel list, so the
        union stays the single statement of what a protocol can extract.
        """
        args = get_args(cls.model_fields["features"].annotation)
        if not args:
            return ()
        item = args[0]
        inner = get_args(item)  # unwrap Annotated[union, Discriminator]
        if not inner:
            return (item,) if isinstance(item, type) else ()
        return get_args(inner[0])

    def select(self, *efel_names: str) -> "Protocol":
        """Mark the named features for extraction, ignoring any not valid here."""
        wanted = set(efel_names)
        for feature in self.features:
            if feature.efel_name in wanted:
                feature.extract = True
        return self

    def feature(self, efel_name: str) -> EFeature | None:
        """Return this protocol's feature with ``efel_name``, or None."""
        return next((f for f in self.features if f.efel_name == efel_name), None)

    def selected_efeatures(self) -> list[EFeature]:
        """Return every :class:`EFeature` whose ``extract`` flag is set."""
        return [f for f in self.features if f.extract]

    def timing_override(self) -> dict:
        """Return user-set timing/LJP fields as a dict (0.0 values omitted).

        Only the timing fields this protocol's shape actually declares are
        considered, plus ``ljp``. Used by the extraction task to override
        auto-detected NWB timing.
        """
        result: dict[str, float] = {}
        for key in ("ton", "toff", "tmid", "tmid2", "ljp"):
            value = getattr(self, key, 0.0)
            if value:
                result[key] = value
        return result


# ---------------------------------------------------------------------------
# Shape intermediates — one per BluePyEfe eCode class.
#
# Mirrors the eCode registry at bluepyefe/ecode/__init__.py; the shape decides
# which timing parameters BluePyEfe reads from config_data.
# ---------------------------------------------------------------------------


class StepShapeProtocol(Protocol, abc.ABC):
    """Single rectangular step (``Step`` eCode): onset and end only."""

    ecode: ClassVar[str] = "Step"

    ton: float = ton_field()
    toff: float = toff_field()


class SAHPShapeProtocol(Protocol, abc.ABC):
    """Two-step with a short depolarising pulse (``SAHP`` eCode): 4 timing points."""

    ecode: ClassVar[str] = "SAHP"

    ton: float = ton_field()
    tmid: float = tmid_field()
    tmid2: float = tmid2_field()
    toff: float = toff_field()


class RampShapeProtocol(Protocol, abc.ABC):
    """Linearly rising stimulus (``Ramp`` eCode): only the onset is configurable."""

    ecode: ClassVar[str] = "Ramp"

    ton: float = ton_field()


class HyperDePolShapeProtocol(Protocol, abc.ABC):
    """Hyperpolarising then depolarising step (``HyperDePol`` eCode): 3 timing points."""

    ecode: ClassVar[str] = "HyperDePol"

    ton: float = ton_field()
    tmid: float = tmid_field()
    toff: float = toff_field()


class DeHyperPolShapeProtocol(Protocol, abc.ABC):
    """Depolarising then hyperpolarising step (``DeHyperPol`` eCode): 3 timing points."""

    ecode: ClassVar[str] = "DeHyperPol"

    ton: float = ton_field()
    tmid: float = tmid_field()
    toff: float = toff_field()


class NegCheopsShapeProtocol(Protocol, abc.ABC):
    """Negative triangular ramps (``NegCheops`` eCode); inner ramp times are not exposed."""

    ecode: ClassVar[str] = "NegCheops"

    ton: float = ton_field()
    toff: float = toff_field()


class PosCheopsShapeProtocol(Protocol, abc.ABC):
    """Positive triangular ramps (``PosCheops`` eCode); inner ramp times are not exposed."""

    ecode: ClassVar[str] = "PosCheops"

    ton: float = ton_field()
    toff: float = toff_field()


class SpikeRecShapeProtocol(Protocol, abc.ABC):
    """Train of short suprathreshold pulses (``SpikeRec`` eCode): timing is not configurable."""

    ecode: ClassVar[str] = "SpikeRec"

    # SpikeRec exposes no configurable stimulus timing.


class SineSpecShapeProtocol(Protocol, abc.ABC):
    """Chirp / resonance stimulus (``SineSpec`` eCode)."""

    ecode: ClassVar[str] = "SineSpec"

    ton: float = ton_field()
    toff: float = toff_field()


class PinkNoiseShapeProtocol(Protocol, abc.ABC):
    """Pink-noise stimulus (``PinkNoise`` eCode)."""

    ecode: ClassVar[str] = "PinkNoise"

    ton: float = ton_field()
    toff: float = toff_field()


class CapCheckShapeProtocol(Protocol, abc.ABC):
    """Capacitance-check pulse (``CapCheck`` eCode)."""

    ecode: ClassVar[str] = "CapCheck"

    ton: float = ton_field()
    toff: float = toff_field()


# ---------------------------------------------------------------------------
# Concrete protocols — Step shape
# ---------------------------------------------------------------------------


class IDRestProtocol(StepShapeProtocol):
    """IDrest — long depolarising step used for the firing-pattern features."""

    protocol_name: ClassVar[str] = "IDrest"
    features: tuple[efeatures.IDRestFeatureUnion, ...] = _features_field(efeatures.IDREST_FEATURES)


class IDThreshProtocol(StepShapeProtocol):
    """IDthresh — near-rheobase step, normally the rheobase-search protocol."""

    protocol_name: ClassVar[str] = "IDthresh"
    features: tuple[efeatures.IDThreshFeatureUnion, ...] = _features_field(
        efeatures.IDTHRESH_FEATURES
    )


class IVProtocol(StepShapeProtocol):
    """IV — subthreshold step used for input resistance and sag."""

    protocol_name: ClassVar[str] = "IV"
    features: tuple[efeatures.IVFeatureUnion, ...] = _features_field(efeatures.IV_FEATURES)


class APWaveformProtocol(StepShapeProtocol):
    """APWaveform — short suprathreshold step used for spike-shape features."""

    protocol_name: ClassVar[str] = "APWaveform"
    features: tuple[efeatures.APWaveformFeatureUnion, ...] = _features_field(
        efeatures.APWAVEFORM_FEATURES
    )


class FirePatternProtocol(StepShapeProtocol):
    """FirePattern — long depolarising step for sustained firing."""

    protocol_name: ClassVar[str] = "FirePattern"
    features: tuple[efeatures.IDRestFeatureUnion, ...] = _features_field(efeatures.IDREST_FEATURES)


class SpontaneousProtocol(StepShapeProtocol):
    """Spontaneous — no injected current; spiking features on the resting trace."""

    protocol_name: ClassVar[str] = "Spontaneous"
    features: tuple[efeatures.IDRestFeatureUnion, ...] = _features_field(efeatures.IDREST_FEATURES)


class SpontAPsProtocol(StepShapeProtocol):
    """SpontAPs — spontaneous action potentials."""

    protocol_name: ClassVar[str] = "SpontAPs"
    features: tuple[efeatures.IDRestFeatureUnion, ...] = _features_field(efeatures.IDREST_FEATURES)


class DeltaProtocol(StepShapeProtocol):
    """Delta — short step used as a generic depolarising probe."""

    protocol_name: ClassVar[str] = "Delta"
    features: tuple[efeatures.IDRestFeatureUnion, ...] = _features_field(efeatures.IDREST_FEATURES)


class StartHoldProtocol(StepShapeProtocol):
    """StartHold — holding-current step at the start of a recording."""

    protocol_name: ClassVar[str] = "StartHold"
    features: tuple[efeatures.IDRestFeatureUnion, ...] = _features_field(efeatures.IDREST_FEATURES)


class StartNoHoldProtocol(StepShapeProtocol):
    """StartNoHold — start-of-recording step without holding current."""

    protocol_name: ClassVar[str] = "StartNoHold"
    features: tuple[efeatures.IDRestFeatureUnion, ...] = _features_field(efeatures.IDREST_FEATURES)


class GenericStepProtocol(StepShapeProtocol):
    """Step — generic rectangular step for recordings with no more specific name."""

    protocol_name: ClassVar[str] = "Step"
    features: tuple[efeatures.IDRestFeatureUnion, ...] = _features_field(efeatures.IDREST_FEATURES)


# ---------------------------------------------------------------------------
# Concrete protocols — SAHP shape
# ---------------------------------------------------------------------------


class SAHPProtocol(SAHPShapeProtocol):
    """sAHP — two-step protocol probing the slow afterhyperpolarisation."""

    protocol_name: ClassVar[str] = "sAHP"
    features: tuple[efeatures.SAHPFeatureUnion, ...] = _features_field(efeatures.SAHP_FEATURES)


class IDHyperpolProtocol(SAHPShapeProtocol):
    """IDhyperpol — hyperpolarising variant of the sAHP shape."""

    protocol_name: ClassVar[str] = "IDhyperpol"
    features: tuple[efeatures.SAHPFeatureUnion, ...] = _features_field(efeatures.SAHP_FEATURES)


class IRHyperpolProtocol(SAHPShapeProtocol):
    """IRhyperpol — input-resistance hyperpolarising protocol."""

    protocol_name: ClassVar[str] = "IRhyperpol"
    features: tuple[efeatures.SAHPFeatureUnion, ...] = _features_field(efeatures.SAHP_FEATURES)


class IDDepolProtocol(SAHPShapeProtocol):
    """IDdepol — depolarising variant of the sAHP shape; elicits spiking."""

    protocol_name: ClassVar[str] = "IDdepol"
    features: tuple[efeatures.IDRestFeatureUnion, ...] = _features_field(efeatures.IDREST_FEATURES)


class IRDepolProtocol(SAHPShapeProtocol):
    """IRdepol — input-resistance depolarising protocol; elicits spiking."""

    protocol_name: ClassVar[str] = "IRdepol"
    features: tuple[efeatures.IDRestFeatureUnion, ...] = _features_field(efeatures.IDREST_FEATURES)


# ---------------------------------------------------------------------------
# Concrete protocols — Ramp shape
# ---------------------------------------------------------------------------


class RampProtocol(RampShapeProtocol):
    """Ramp — linearly rising current used to find the AP threshold."""

    protocol_name: ClassVar[str] = "Ramp"
    features: tuple[efeatures.APWaveformFeatureUnion, ...] = _features_field(
        efeatures.APWAVEFORM_FEATURES
    )


class APThresholdProtocol(RampShapeProtocol):
    """APThreshold — ramp to the first spike."""

    protocol_name: ClassVar[str] = "APThreshold"
    features: tuple[efeatures.APWaveformFeatureUnion, ...] = _features_field(
        efeatures.APWAVEFORM_FEATURES
    )


# ---------------------------------------------------------------------------
# Concrete protocols — one per remaining shape
# ---------------------------------------------------------------------------


class HyperDePolProtocol(HyperDePolShapeProtocol):
    """HyperDePol — hyperpolarising step followed by a depolarising one."""

    protocol_name: ClassVar[str] = "HyperDePol"
    features: tuple[efeatures.IDRestFeatureUnion, ...] = _features_field(efeatures.IDREST_FEATURES)


class DeHyperPolProtocol(DeHyperPolShapeProtocol):
    """DeHyperPol — depolarising step followed by a hyperpolarising one."""

    protocol_name: ClassVar[str] = "DeHyperPol"
    features: tuple[efeatures.IDRestFeatureUnion, ...] = _features_field(efeatures.IDREST_FEATURES)


class NegCheopsProtocol(NegCheopsShapeProtocol):
    """negCheops — negative triangular ramp series."""

    protocol_name: ClassVar[str] = "negCheops"
    features: tuple[efeatures.IDRestFeatureUnion, ...] = _features_field(efeatures.IDREST_FEATURES)


class PosCheopsProtocol(PosCheopsShapeProtocol):
    """posCheops — positive triangular ramp series."""

    protocol_name: ClassVar[str] = "posCheops"
    features: tuple[efeatures.IDRestFeatureUnion, ...] = _features_field(efeatures.IDREST_FEATURES)


class SpikeRecProtocol(SpikeRecShapeProtocol):
    """SpikeRec — train of short suprathreshold pulses."""

    protocol_name: ClassVar[str] = "SpikeRec"
    features: tuple[efeatures.SpikeRecFeatureUnion, ...] = _features_field(
        efeatures.SPIKEREC_FEATURES
    )


class SineSpecProtocol(SineSpecShapeProtocol):
    """sineSpec — chirp stimulus used to probe subthreshold resonance."""

    protocol_name: ClassVar[str] = "sineSpec"
    features: tuple[efeatures.IDThreshFeatureUnion, ...] = _features_field(
        efeatures.IDTHRESH_FEATURES
    )


class PinkNoiseProtocol(PinkNoiseShapeProtocol):
    """pinkNoise — suprathreshold pink-noise current injection."""

    protocol_name: ClassVar[str] = "pinkNoise"
    features: tuple[efeatures.IDRestFeatureUnion, ...] = _features_field(efeatures.IDREST_FEATURES)


class CapCheckProtocol(CapCheckShapeProtocol):
    """capCheck — short pulse used to check the capacitance compensation."""

    protocol_name: ClassVar[str] = "capCheck"
    features: tuple[efeatures.SubthresholdFeatureUnion, ...] = _features_field(
        efeatures.SUBTHRESHOLD_FEATURES
    )


_PROTOCOLS = (
    IDRestProtocol
    | IDThreshProtocol
    | IVProtocol
    | APWaveformProtocol
    | FirePatternProtocol
    | SpontaneousProtocol
    | SpontAPsProtocol
    | DeltaProtocol
    | StartHoldProtocol
    | StartNoHoldProtocol
    | GenericStepProtocol
    | SAHPProtocol
    | IDHyperpolProtocol
    | IRHyperpolProtocol
    | IDDepolProtocol
    | IRDepolProtocol
    | RampProtocol
    | APThresholdProtocol
    | HyperDePolProtocol
    | DeHyperPolProtocol
    | NegCheopsProtocol
    | PosCheopsProtocol
    | SpikeRecProtocol
    | SineSpecProtocol
    | PinkNoiseProtocol
    | CapCheckProtocol
)

ProtocolUnion = Annotated[_PROTOCOLS, Discriminator("type")]

# Ordered longest-name-first so that e.g. "IDthresh" wins over "IDrest" would-be
# prefixes and "IRhyperpol" is not shadowed by a shorter alias.
PROTOCOL_CLASSES: tuple[type[Protocol], ...] = tuple(
    sorted(
        (
            IDRestProtocol,
            IDThreshProtocol,
            IVProtocol,
            APWaveformProtocol,
            FirePatternProtocol,
            SpontaneousProtocol,
            SpontAPsProtocol,
            DeltaProtocol,
            StartHoldProtocol,
            StartNoHoldProtocol,
            GenericStepProtocol,
            SAHPProtocol,
            IDHyperpolProtocol,
            IRHyperpolProtocol,
            IDDepolProtocol,
            IRDepolProtocol,
            RampProtocol,
            APThresholdProtocol,
            HyperDePolProtocol,
            DeHyperPolProtocol,
            NegCheopsProtocol,
            PosCheopsProtocol,
            SpikeRecProtocol,
            SineSpecProtocol,
            PinkNoiseProtocol,
            CapCheckProtocol,
        ),
        key=lambda cls: len(cls.protocol_name),
        reverse=True,
    )
)

# Alternative spellings seen in recording metadata, mapped to their protocol.
PROTOCOL_ALIASES: dict[str, type[Protocol]] = {
    "idthres": IDThreshProtocol,
    "idthreshold": IDThreshProtocol,
    "ap_thresh": APThresholdProtocol,
    "apthresh": APThresholdProtocol,
    "sponaps": SpontAPsProtocol,
    "sponnohold30": SpontaneousProtocol,
    "sponhold30": SpontaneousProtocol,
    "spontnohold30": SpontaneousProtocol,
    "sponthold30": SpontaneousProtocol,
    "spontaneousnohold": SpontaneousProtocol,
    "genericstep": GenericStepProtocol,
}


def protocol_class_for_name(protocol_name: str) -> type[Protocol] | None:
    """Return the protocol class matching ``protocol_name``, or None.

    Mirrors BluePyEfe's own lookup (``cell.Cell.read_recordings``): a registry
    key that is a case-insensitive substring of the protocol name wins, so
    ``"IDrest_250"`` resolves to :class:`IDRestProtocol`. Longer names are
    tried first so more specific protocols beat shorter ones.
    """
    lowered = protocol_name.lower()
    for alias, cls in sorted(PROTOCOL_ALIASES.items(), key=lambda kv: -len(kv[0])):
        if alias in lowered:
            return cls
    for cls in PROTOCOL_CLASSES:
        if cls.protocol_name.lower() in lowered:
            return cls
    return None


def protocol_from_name(protocol_name: str, **kwargs: Any) -> Protocol:
    """Build the protocol matching ``protocol_name``, with its valid features.

    Raises:
        KeyError: if no protocol matches, mirroring BluePyEfe's behaviour.
    """
    cls = protocol_class_for_name(protocol_name)
    if cls is None:
        msg = (
            f"There is no protocol matching the stimulus name {protocol_name!r}."
            " See PROTOCOL_CLASSES for the available protocols."
        )
        raise KeyError(msg)
    return cls(**kwargs)
