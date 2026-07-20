"""Block holding the list of protocols with per-protocol feature selections."""

from enum import StrEnum

from pydantic import Field

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.images_and_doc_links import (  # noqa: E501
    EFEL_DOC_BASE_URL,
    EFEL_FEATURE_IMAGE_MAP,
    EFEL_FIGURES_BASE_URL,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (  # noqa: E501
    APWaveformProtocol,
    IDRestProtocol,
    IDThreshProtocol,
    IVProtocol,
    ProtocolUnion,
    SAHPProtocol,
    available_efeatures_by_protocol,
)


class AutoTargetPreset(StrEnum):
    """Preset names mirroring BluePyEModel's ``AUTO_TARGET_DICT`` keys."""

    FIRING_PATTERN = "firing_pattern"
    AP_WAVEFORM = "ap_waveform"
    IV = "iv"
    VALIDATION = "validation"


def _default_protocols() -> tuple[ProtocolUnion, ...]:
    """L5PC-style defaults, pre-selecting the features the L5PC example extracts.

    ``Protocol.select`` silently skips names that are not valid for a protocol,
    so these lists stay honest against the per-protocol feature sets.
    """
    idthresh = IDThreshProtocol(is_rheobase_protocol=True)
    idrest = IDRestProtocol().select(
        "Spikecount",
        "mean_frequency",
        "time_to_first_spike",
        "time_to_last_spike",
        "inv_time_to_first_spike",
        "inv_first_ISI",
        "inv_second_ISI",
        "inv_third_ISI",
        "inv_last_ISI",
        "AHP_depth",
        "AHP_time_from_peak",
        "depol_block_bool",
        "voltage_base",
    )
    iv = IVProtocol().select("voltage_base", "ohmic_input_resistance_vb_ssse")
    apwaveform = APWaveformProtocol().select(
        "AP_amplitude", "AP1_amp", "AP_duration_half_width", "AHP_depth"
    )
    sahp = SAHPProtocol().select("mean_frequency", "voltage_base", "depol_block_bool")

    return (idthresh, idrest, iv, apwaveform, sahp)


class SelectEFeaturesByProtocol(OBIBaseModel):
    """Protocol list and per-protocol feature selection.

    Not a Block — this is the object behind the ``select_efeatures_by_protocol``
    UI element, in the same way :class:`NeuronPropertyFilter` backs the neuron
    property filter element. The whole object is rendered by that one widget, so
    its fields carry no individual ``ui_element`` of their own.

    ``threshold_based`` controls whether per-protocol ``extraction_amplitudes``
    are interpreted as relative (% of rheobase) or absolute (nA, auto-discovered
    from the NWB).

    Each entry in ``protocols`` is one of the concrete :class:`Protocol`
    subclasses, carrying its own stimulus timing (``ton``/``toff``/``tmid``/
    ``tmid2``), liquid junction potential (``ljp``), and a ``features`` dict of
    valid :class:`EFeature` instances keyed by eFEL feature name. Whether each
    feature is actually extracted is controlled by its own ``extract`` flag.
    Which features are valid, and which timing fields are meaningful, are fixed
    by the protocol class itself — see :mod:`.protocols_and_features.protocols`.

    ``protocols`` is a tuple — not a list — so the obi-one scan framework
    leaves it alone instead of expanding it as a parameter-scan dimension.
    """

    threshold_based: bool = Field(
        default=False,
        title="Threshold-based amplitudes",
        description=(
            "When enabled, extraction uses relative amplitudes (% of rheobase)"
            " from per-protocol ``extraction_amplitudes``. When disabled (default),"
            " amplitudes are auto-discovered in absolute nA from the NWB."
        ),
    )

    autoselect: bool = Field(
        default=False,
        title="Automatically fill the features and protocols",
        description=(
            "When enabled, protocols and features are selected automatically"
            " using BluePyEModel's auto_targets presets. Manual protocol/feature"
            " selection below is ignored."
        ),
    )

    auto_targets_presets: str = Field(
        default="firing_pattern,ap_waveform,iv",
        title="Auto-target presets",
        description=(
            "Presets from BluePyEModel's AUTO_TARGET_DICT used when autoselect"
            " is enabled. Select one or more: 'firing_pattern', 'ap_waveform',"
            " 'iv', 'validation'."
        ),
    )

    protocols: tuple[ProtocolUnion, ...] = Field(  # ty:ignore[invalid-assignment]
        default_factory=_default_protocols,
        title="Protocols",
        description=(
            "Protocols to extract features from. Defaults mirror the L5PC"
            " example; the frontend can repopulate this from the catalogue and"
            " the protocols discovered from the recordings' NWB files."
            " Ignored when autoselect is enabled."
        ),
    )


class ProtocolAndFeatureSelection(Block):
    """Per-protocol picker for timing, LJP, amplitudes, and chosen efeatures.

    The selection itself lives in :class:`SelectEFeaturesByProtocol`, exposed as
    a single object field so the schema advertises ``type: object`` as the
    ``select_efeatures_by_protocol`` component spec requires.
    """

    selection: SelectEFeaturesByProtocol = Field(
        default_factory=SelectEFeaturesByProtocol,
        title="EFeatures by protocol",
        description=(
            "Protocols to extract features from, together with the per-protocol"
            " feature selection and the amplitude/auto-target settings that"
            " govern it."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.SELECT_EFEATURES_BY_PROTOCOL,
            "available_efeatures_by_protocol": available_efeatures_by_protocol(),
            "efel_doc_base_url": EFEL_DOC_BASE_URL,
            "efel_figures_base_url": EFEL_FIGURES_BASE_URL,
            "efel_feature_image_map": EFEL_FEATURE_IMAGE_MAP,
        },
    )
