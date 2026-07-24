"""Ephys protocol models, one class per protocol.

The hierarchy has three levels:

* :class:`Protocol` — the base, holding the fields every protocol shares
  (amplitudes, role flags, feature selection).
* a *shape* intermediate per BluePyEfe eCode class (:class:`StepShapeProtocol`,
  :class:`SAHPShapeProtocol`, …). The stimulus shape decides which timing
  parameters exist, so each intermediate fixes ``ecode_class`` and declares
  exactly the timing fields its eCode reads — ``stim_start``/``stim_end`` for a plain
  step, all four for sAHP, ``stim_start`` alone for a ramp, none at all for SpikeRec.
  A protocol therefore has no timing field it cannot use, and the schema tells
  the frontend which inputs to render without a separate list.
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
from typing import Annotated, Any, ClassVar

from pydantic import Discriminator, Field, PositiveFloat

from obi_one.core.base import OBIBaseModel
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.library.entity_property_types import (
    ElectricalCellRecordingMappedProperties,
    MappedPropertiesGroup,
)
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


def stim_start_field() -> Any:
    """Stimulus onset, declared by shapes whose eCode reads ``stim_start``."""
    return _timing_field(
        "Stimulus onset (stim_start)",
        "Stimulus onset time (ms). Set to 0 to auto-detect from the NWB.",
    )


def stim_end_field() -> Any:
    """Stimulus end, declared by shapes whose eCode reads ``stim_end``."""
    return _timing_field(
        "Stimulus end (stim_end)",
        "Stimulus end time (ms). Set to 0 to auto-detect from the NWB.",
    )


def stim_mid_field() -> Any:
    """First mid-transition, declared by two-step shapes."""
    return _timing_field(
        "Mid-transition 1 (stim_mid)",
        "First mid-transition point for two-step protocols (ms). Set to 0 to auto-detect.",
    )


def stim_mid_2_field() -> Any:
    """Second mid-transition, declared by the sAHP shape."""
    return _timing_field(
        "Mid-transition 2 (stim_mid_2)",
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

    Protocol-level stimulus timing (``stim_start``/``stim_end``/``stim_mid``/``stim_mid_2``) may be
    user-specified; when left at ``0.0`` it is auto-detected from each
    ``ElectricalCellRecording``'s NWB asset at task execution time.

    Per-feature eFEL detection knobs (threshold, interp_step, stim_start,
    stim_end) live on :class:`EFeature` and override the global-level settings.
    """

    # -- static description, set by the shape intermediate / concrete class ---

    protocol_name: ClassVar[str] = ""
    """Name of the BluePyEfe protocol name class implementing this stimulus shape."""

    # ------------------------------------------------------------------
    # Per-protocol extraction amplitudes (threshold-based / relative mode)
    # ------------------------------------------------------------------
    extraction_amplitudes: tuple[tuple[float, bool], ...] = Field(
        default=(),
        title="Extraction amplitudes",
        description=(
            "Step amplitudes (nA) to extract from this protocol, populated from the"
            " recordings' NWBs via the ``AmplitudesByProtocol`` property of"
            " ``/declared/mapped-electrical-cell-recording-properties``. Each amplitude is"
            " paired with a boolean marking whether it is used for validation."
        ),
        json_schema_extra={
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.INPUTS,
            SchemaKey.PROPERTY: ElectricalCellRecordingMappedProperties.AMPLITUDES_BY_PROTOCOL,
        },
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

    threshold: float | None = Field(
        default=None,
        title="Threshold",
        description=(
            "eFEL ``Threshold``: voltage above which a spike is detected (mV)."
            " Leave unset to inherit the global value; features may override it."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLIVOLTS,
        },
    )
    interp_step: PositiveFloat | None = Field(
        default=None,
        title="Interpolation step",
        description=(
            "eFEL ``interp_step``: time step the trace is resampled to before extraction"
            " (ms). Leave unset to inherit the global value; features may override it."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    def efel_settings_overrides(self) -> dict:
        """Return this protocol's own eFEL setting overrides (only what it sets).

        Unset (``None``) values are omitted so the extraction task can cascade
        feature > protocol > global.
        """
        overrides: dict[str, float | bool] = {}
        if self.threshold is not None:
            overrides["Threshold"] = self.threshold
        if self.interp_step is not None:
            overrides["interp_step"] = self.interp_step
        return overrides

    def stim_timing(self) -> dict:
        """Return user-set stimulus timing, keyed as bluepyefe eCode metadata.

        Maps the shape's ``stim_start``/``stim_end``/``stim_mid``/``stim_mid_2`` to
        bluepyefe's ``ton``/``toff``/``tmid``/``tmid2``; 0.0 values are omitted so
        bluepyefe auto-detects them from the NWB.
        """
        mapping = {
            "stim_start": "ton",
            "stim_end": "toff",
            "stim_mid": "tmid",
            "stim_mid_2": "tmid2",
        }
        timing: dict[str, float] = {}
        for attr, key in mapping.items():
            value = getattr(self, attr, 0.0)
            if value:
                timing[key] = value
        return timing

# ---------------------------------------------------------------------------
# Shape intermediates — one per BluePyEfe eCode class.
#
# Mirrors the eCode registry at bluepyefe/ecode/__init__.py; the shape decides
# which timing parameters BluePyEfe reads from config_data.
# ---------------------------------------------------------------------------


class StepShapeProtocol(Protocol, abc.ABC):
    """Single rectangular step (``Step`` eCode): onset and end only."""

    ecode_class: ClassVar[str] = "Step"

    stim_start: float = stim_start_field()
    stim_end: float = stim_end_field()


class SAHPShapeProtocol(Protocol, abc.ABC):
    """Two-step with a short depolarising pulse (``SAHP`` eCode): 4 timing points."""

    ecode_class: ClassVar[str] = "SAHP"

    stim_start: float = stim_start_field()
    stim_mid: float = stim_mid_field()
    stim_mid_2: float = stim_mid_2_field()
    stim_end: float = stim_end_field()


class RampShapeProtocol(Protocol, abc.ABC):
    """Linearly rising stimulus (``Ramp`` eCode): only the onset is configurable."""

    ecode_class: ClassVar[str] = "Ramp"

    stim_start: float = stim_start_field()


class HyperDePolShapeProtocol(Protocol, abc.ABC):
    """Hyperpolarising then depolarising step (``HyperDePol`` eCode): 3 timing points."""

    ecode_class: ClassVar[str] = "HyperDePol"

    stim_start: float = stim_start_field()
    stim_mid: float = stim_mid_field()
    stim_end: float = stim_end_field()


class DeHyperPolShapeProtocol(Protocol, abc.ABC):
    """Depolarising then hyperpolarising step (``DeHyperPol`` eCode): 3 timing points."""

    ecode_class: ClassVar[str] = "DeHyperPol"

    stim_start: float = stim_start_field()
    stim_mid: float = stim_mid_field()
    stim_end: float = stim_end_field()


class NegCheopsShapeProtocol(Protocol, abc.ABC):
    """Negative triangular ramps (``NegCheops`` eCode); inner ramp times are not exposed."""

    ecode_class: ClassVar[str] = "NegCheops"

    stim_start: float = stim_start_field()
    stim_end: float = stim_end_field()


class PosCheopsShapeProtocol(Protocol, abc.ABC):
    """Positive triangular ramps (``PosCheops`` eCode); inner ramp times are not exposed."""

    ecode_class: ClassVar[str] = "PosCheops"

    stim_start: float = stim_start_field()
    stim_end: float = stim_end_field()


class SpikeRecShapeProtocol(Protocol, abc.ABC):
    """Train of short suprathreshold pulses (``SpikeRec`` eCode): timing is not configurable."""

    ecode_class: ClassVar[str] = "SpikeRec"

    # SpikeRec exposes no configurable stimulus timing.


class SineSpecShapeProtocol(Protocol, abc.ABC):
    """Chirp / resonance stimulus (``SineSpec`` eCode)."""

    ecode_class: ClassVar[str] = "SineSpec"

    stim_start: float = stim_start_field()
    stim_end: float = stim_end_field()


class PinkNoiseShapeProtocol(Protocol, abc.ABC):
    """Pink-noise stimulus (``PinkNoise`` eCode)."""

    ecode_class: ClassVar[str] = "PinkNoise"

    stim_start: float = stim_start_field()
    stim_end: float = stim_end_field()


class CapCheckShapeProtocol(Protocol, abc.ABC):
    """Capacitance-check pulse (``CapCheck`` eCode)."""

    ecode_class: ClassVar[str] = "CapCheck"

    stim_start: float = stim_start_field()
    stim_end: float = stim_end_field()


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


ProtocolUnion = Annotated[
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
    | CapCheckProtocol, Discriminator("type")]
