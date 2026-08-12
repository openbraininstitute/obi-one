"""Block holding the list of protocols with per-protocol feature selections."""

from pydantic import Field

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.efeatures import (  # ruff: ignore[line-too-long]
    EFeature,
    EFeatureUnion,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (  # ruff: ignore[line-too-long]
    APWaveformProtocol,
    IDRestProtocol,
    IDThreshProtocol,
    IVProtocol,
    Protocol,
    ProtocolUnion,
    SAHPProtocol,
)


def _default_protocols() -> tuple[ProtocolUnion, ...]:
    """L5PC-style default protocol set; each extracts its full valid feature set.

    The frontend repopulates this from the protocols and amplitudes returned by
    ``/declared/mapped-electrical-cell-recording-properties`` for the chosen
    recordings.
    """
    return (
        IDThreshProtocol(),
        IDRestProtocol(),
        IVProtocol(),
        APWaveformProtocol(),
        SAHPProtocol(),
    )


# Future: relative (% of rheobase) amplitude extraction. Reintroduce this strategy
# (and a threshold-based amplitude mode) on ``SelectEFeaturesByProtocol`` later.
_RELATIVE_AMPLITUDE_STRATEGY_TODO = """
class RelativeAmplitudeExtractionStrategy(BaseModel):
    # Per-protocol role flags (Rin, RMP, Rheobase)
    rin_protocol: bool = Field(
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
            " Only used when ``rin_protocol`` is True. Default: -20%."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    rmp_protocol: bool = Field(
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
            " Only used when ``rmp_protocol`` is True. Default: 0%."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    rheobase_protocol: bool = Field(
        default=False,
        title="Use for rheobase",
        description=(
            "If True, this protocol is used to estimate rheobase (lowest amplitude"
            " inducing at least 1 spike). Typically IDthresh or IDThreshold."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
"""


class SelectEFeaturesByProtocol(OBIBaseModel):
    """Protocol list and per-protocol feature selection.

    Not a Block — this is the object behind the ``select_efeatures_by_protocol``
    UI element. The whole object is rendered by that one widget, so its fields
    carry no individual ``ui_element`` of their own.

    Each entry in ``protocols`` is one of the concrete :class:`Protocol`
    subclasses, carrying the stimulus timing its eCode shape defines, the
    ``(amplitude, is_validation)`` extraction amplitudes, and a ``features`` tuple
    of the eFEL features to extract. ``protocols`` is a tuple — not a list — so the
    obi-one scan framework leaves it alone instead of expanding it as a scan
    dimension.
    """

    # declares the universal EFeatureUnion once for the whole schema. The UI dereferences the
    # OpenAPI document before validating, so every occurrence of the 146-branch union is copied:
    # one costs ~1.2 MB of generated validator code, 26 cost ~30 MB and exceed the browser's
    # stack. Keep each protocol's own ``features`` annotation narrow.
    extra_features_by_protocol: dict[str, tuple[EFeatureUnion, ...]] = Field(
        default_factory=dict,
        title="Extra features by protocol",
        description=(
            "eFEL features added beyond a protocol's own default set, keyed by the"
            " protocol's type name (e.g. ``IDRestProtocol``). Any feature in the eFEL"
            " catalogue is accepted for any protocol. Duplicates of a protocol's"
            " defaults are ignored."
        ),
    )

    protocols: tuple[ProtocolUnion, ...] = Field(
        default_factory=_default_protocols,
        title="Protocols",
        description=(
            "Protocols to extract features from. Defaults mirror the L5PC example;"
            " the frontend can repopulate this from the protocols and amplitudes"
            " discovered for the chosen recordings."
        ),
    )

    def features_for(self, protocol: Protocol) -> tuple[EFeature, ...]:
        """Return ``protocol``'s own features followed by its extras.

        An extra that duplicates one of the protocol's own features is dropped, so the
        default's setting overrides win.
        """
        extras = self.extra_features_by_protocol.get(type(protocol).__name__, ())
        already_selected = {type(feature).__name__ for feature in protocol.features}
        return (
            *protocol.features,
            *(feature for feature in extras if type(feature).__name__ not in already_selected),
        )


class ProtocolAndFeatureSelection(Block):
    """Choose the protocols, amplitudes, and eFEL features for your recordings.

    Select which electrical features (efeatures) to extract for each protocol. The available
    protocols and amplitudes depend on the recordings you choose.
    """

    selection: SelectEFeaturesByProtocol = Field(
        default_factory=SelectEFeaturesByProtocol,
        title="EFeatures by protocol",
        description=(
            "Protocols to extract features from, together with the per-protocol"
            " feature selection and the amplitude settings that govern it."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.SELECT_EFEATURES_BY_PROTOCOL,
            SchemaKey.PROPERTY_ENDPOINTS: "declared/mapped-electrical-cell-recording-properties",
        },
    )
