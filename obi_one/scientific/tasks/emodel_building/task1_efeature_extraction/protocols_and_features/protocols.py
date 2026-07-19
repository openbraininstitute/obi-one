"""Ephys protocol Pydantic model.

A single generic :class:`Protocol` class replaces the former per-protocol
subclasses. Valid eFEL features per protocol are sourced from
:func:`bluepyefe.ecode.get_valid_efeatures`, eliminating duplication between
obi-one and bluepyefe.

Each BluePyEfe eCode class uses a different subset of timing parameters
(ton, toff, tmid, tmid2). The :data:`ECODE_TIMING_PARAMS` mapping tells the
frontend which timing fields to render for each protocol via
``Protocol.visible_timing_params``.
"""

from typing import Any

from pydantic import Field, model_validator

from obi_one.core.base import OBIBaseModel
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.efeatures import (  # noqa: E501
    EFEATURE_REGISTRY,
    EFeature,
    get_feature_category,
)

# ---------------------------------------------------------------------------
# Per-eCode timing parameter visibility
#
# Maps each BluePyEfe eCode name (lowercase, matching PROTOCOL_EFEATURES keys)
# to the tuple of timing fields that are meaningful for that stimulus shape.
# The frontend uses this to show only the relevant timing inputs.
#
# Source: bluepyefe/ecode/*.py — each Recording subclass reads a different
# subset of ton/toff/tmid/tmid2 from config_data.
# ---------------------------------------------------------------------------

ECODE_TIMING_PARAMS: dict[str, tuple[str, ...]] = {
    # Step eCode (IDrest, IV, APWaveform, IDthresh, FirePattern, etc.)
    "step": ("ton", "toff"),
    "idrest": ("ton", "toff"),
    "genericstep": ("ton", "toff"),
    "iv": ("ton", "toff"),
    "apwaveform": ("ton", "toff"),
    "idthresh": ("ton", "toff"),
    "idthres": ("ton", "toff"),
    "idthreshold": ("ton", "toff"),
    "firepattern": ("ton", "toff"),
    "spontaneous": ("ton", "toff"),
    "spontaps": ("ton", "toff"),
    "sponaps": ("ton", "toff"),
    "sponnohold30": ("ton", "toff"),
    "sponhold30": ("ton", "toff"),
    "spontnohold30": ("ton", "toff"),
    "sponthold30": ("ton", "toff"),
    "spontaneousnohold": ("ton", "toff"),
    "starthold": ("ton", "toff"),
    "startnohold": ("ton", "toff"),
    "delta": ("ton", "toff"),
    "iddepol": ("ton", "toff"),
    "irdepol": ("ton", "toff"),
    # Ramp eCode — only needs ton (toff = end of ramp, auto-detected)
    "ramp": ("ton",),
    "ap_thresh": ("ton",),
    "apthresh": ("ton",),
    "apthreshold": ("ton",),
    # sAHP eCode — two-step protocol with 4 timing points
    "sahp": ("ton", "tmid", "tmid2", "toff"),
    "idhyperpol": ("ton", "tmid", "tmid2", "toff"),
    "irhyperpol": ("ton", "tmid", "tmid2", "toff"),
    # DeHyperPol / HyperDePol — two-step with 3 timing points
    "dehyperpol": ("ton", "tmid", "toff"),
    "hyperdepol": ("ton", "tmid", "toff"),
    # Cheops — triangular stimuli (t1-t4 not yet exposed; use ton/toff as outer bounds)
    "poscheops": ("ton", "toff"),
    "negcheops": ("ton", "toff"),
    # SpikeRec — no user-configurable timing
    "spikerec": (),
    # SineSpec / resonance
    "sinespec": ("ton", "toff"),
    # PinkNoise
    "pinknoise": ("ton", "toff"),
    # CapCheck
    "capcheck": ("ton", "toff"),
}


def _resolve_timing_params(protocol_name: str) -> tuple[str, ...]:
    """Resolve visible timing params for a protocol name.

    Uses the same case-insensitive substring matching as BluePyEfe's eCode
    lookup to find the matching entry in :data:`ECODE_TIMING_PARAMS`.
    Falls back to ``("ton", "toff")`` (Step-like) if no match.
    """
    name_lower = protocol_name.lower()
    for ecode_name, params in ECODE_TIMING_PARAMS.items():
        if ecode_name in name_lower:
            return params
    return ("ton", "toff")


class Protocol(OBIBaseModel):
    """Generic ephys protocol with feature selection driven by bluepyefe.

    The valid eFEL features for this protocol are sourced from
    :func:`bluepyefe.ecode.get_valid_efeatures` via :meth:`from_protocol_name`.
    Each feature is an :class:`EFeature` instance stored in the ``features``
    dict, keyed by eFEL feature name. Whether each feature is actually
    extracted is controlled by its ``extract`` flag.

    Protocol-level stimulus timing (``ton``/``toff``/``tmid``/``tmid2``) and
    liquid junction potential (``ljp``) can be user-specified; when left at
    ``0.0`` they are auto-detected from each ``ElectricalCellRecording``'s NWB
    asset at task execution time.

    Per-protocol custom eFEL settings are available via
    ``custom_efel_settings``. Per-feature eFEL detection knobs (threshold,
    strict_stiminterval, interp_step, stim_start, stim_end) live on
    :class:`EFeature` and override the protocol level.
    """

    name: str = Field(
        ...,
        title="Protocol name",
        description=(
            "Protocol name (e.g. 'IDrest', 'IV', 'APWaveform'). Must match a"
            " bluepyefe eCode name — see bluepyefe.ecode.eCodes."
        ),
    )

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

    # ------------------------------------------------------------------
    # Features — keyed by eFEL feature name
    # ------------------------------------------------------------------
    features: dict[str, EFeature] = Field(
        default_factory=dict,
        title="Features",
        description=(
            "eFEL features valid for this protocol, keyed by eFEL feature name."
            " Use Protocol.from_protocol_name() to populate with the correct"
            " features for a given protocol name."
        ),
    )

    # ------------------------------------------------------------------
    # Visible timing params — tells the frontend which timing fields to show
    # ------------------------------------------------------------------
    visible_timing_params: tuple[str, ...] = Field(
        default=("ton", "toff"),
        title="Visible timing parameters",
        description=(
            "Timing fields that are meaningful for this protocol's eCode shape."
            " The frontend should only render these timing inputs. Other timing"
            " fields still exist on the model (defaulting to 0.0 = auto-detect)"
            " but are irrelevant for this protocol type."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _strip_feature_type(cls, data: object) -> object:
        """Strip ``type`` from feature dicts so base EFeature validates.

        EFeature subclasses set ``type`` to their class name (e.g.
        ``"Spikecount"``) via :class:`OBIBaseModel`. When deserializing a
        ``dict[str, EFeature]``, Pydantic validates each value as the base
        ``EFeature`` class which expects ``type: Literal["EFeature"]``.
        Removing ``type`` from the raw dict lets validation succeed while
        ``efel_name`` preserves the feature identity.
        """
        if isinstance(data, dict) and "features" in data:
            for val in data["features"].values():
                if isinstance(val, dict) and "type" in val:
                    del val["type"]
        return data

    @classmethod
    def from_protocol_name(cls, name: str, **kwargs: Any) -> "Protocol":
        """Create a Protocol with all valid features instantiated (extract=False).

        Uses :func:`bluepyefe.ecode.get_valid_efeatures` to determine which
        eFEL features are valid for the given protocol name, then instantiates
        each as a generic :class:`EFeature` with the correct ``efel_name`` and
        ``category``.

        Also sets ``visible_timing_params`` based on :data:`ECODE_TIMING_PARAMS`
        so the frontend knows which timing fields to render.
        """
        from bluepyefe.ecode import get_valid_efeatures  # noqa: PLC0415

        valid = get_valid_efeatures(name)
        features: dict[str, EFeature] = {}
        for efel_name in valid:
            if efel_name in EFEATURE_REGISTRY:
                features[efel_name] = EFeature(
                    efel_name=efel_name,
                    category=get_feature_category(efel_name),
                )

        # Determine visible timing params from eCode mapping
        visible = _resolve_timing_params(name)

        return cls(
            name=name,
            features=features,
            visible_timing_params=visible,
            **kwargs,
        )  # ty:ignore[arg-type]

    def selected_efeatures(self) -> list[EFeature]:
        """Return every :class:`EFeature` whose ``extract`` flag is set."""
        return [f for f in self.features.values() if f.extract]

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
