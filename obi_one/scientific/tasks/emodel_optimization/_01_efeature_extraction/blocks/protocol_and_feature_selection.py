"""Block holding the list of protocols with per-protocol feature selections."""

from dataclasses import fields as dataclass_fields

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.protocols_and_features import (  # noqa: E501
    IV,
    PROTOCOL_CATALOGUE,
    SAHP,
    APWaveform,
    EFeature,
    IDrest,
    IDthresh,
    Protocol,
    ProtocolUnion,
    available_features_by_protocol_name,
)


def _efel_settings_defaults() -> dict[str, dict]:
    """Introspect ``efel.settings.Settings`` for the frontend's "add setting" picker.

    Returns ``{setting_name: {"default": value, "type": "float"|"int"|"str"|"bool"}}``
    for every field on the eFEL ``Settings`` dataclass.
    """
    try:
        from efel.settings import Settings  # noqa: PLC0415
    except ImportError:
        return {}

    result: dict[str, dict] = {}
    for f in dataclass_fields(Settings):
        type_name: str
        if f.type is float or f.type == "float":
            type_name = "float"
        elif f.type is int or f.type == "int":
            type_name = "int"
        elif f.type is bool or f.type == "bool":
            type_name = "bool"
        else:
            type_name = "str"
        result[f.name] = {"default": f.default, "type": type_name}
    return result


def available_efeatures_by_category() -> dict[str, list[str]]:
    """Group all catalogue features by their ``category`` ClassVar.

    Returns ``{"Spike event": ["Spikecount", ...], "Spike shape": [...], ...}``
    for the frontend's "Add more features" modal.
    """
    result: dict[str, list[str]] = {}
    seen: set[str] = set()
    for p_cls in PROTOCOL_CATALOGUE:
        for field_info in p_cls.model_fields.values():
            ann = field_info.annotation
            if isinstance(ann, type) and issubclass(ann, EFeature) and ann.efel_name not in seen:
                seen.add(ann.efel_name)
                category = ann.category
                result.setdefault(category, []).append(ann.efel_name)
    return result


def _default_protocols() -> tuple[Protocol, ...]:
    """L5PC-style defaults — set ``extract=True`` on the same features the old
    ``ExtractionTargets`` mirror used. Amplitudes are no longer a user
    parameter (they're read from the NWB at task execution time), so this only
    pre-selects features.
    """
    idrest = IDrest()
    for fname in (
        "spikecount",
        "mean_frequency",
        "time_to_first_spike",
        "time_to_last_spike",
        "inv_time_to_first_spike",
        "inv_first_isi",
        "inv_second_isi",
        "inv_third_isi",
        "inv_last_isi",
        "ahp_depth",
        "ahp_time_from_peak",
        "min_ahp_values",
        "depol_block_bool",
        "voltage_base",
    ):
        getattr(idrest, fname).extract = True

    iv = IV()
    iv.voltage_base.extract = True
    iv.ohmic_input_resistance_vb_ssse.extract = True

    apwaveform = APWaveform()
    for fname in ("ap_amplitude", "ap1_amp", "ap_duration_half_width", "ahp_depth"):
        getattr(apwaveform, fname).extract = True

    sahp = SAHP()
    for fname in ("mean_frequency", "voltage_base", "depol_block_bool"):
        getattr(sahp, fname).extract = True

    return (IDthresh(), idrest, iv, apwaveform, sahp)


class ProtocolAndFeatureSelection(Block):
    """Per-protocol picker for timing, LJP, and chosen efeatures.

    Each entry in ``protocols`` is a concrete :class:`Protocol` instance
    carrying its own stimulus timing (``ton``/``toff``/``tmid``/``tmid2``),
    liquid junction potential (``ljp``), and one typed field per valid
    :class:`EFeature`. Whether each feature is actually extracted is
    controlled by its own ``extract`` flag. The catalogue of features
    available per protocol lives in ``protocols_and_features`` and is
    advertised to the frontend via the ``available_efeatures_by_protocol``
    key on the field's ``json_schema_extra``. The full list of eFEL settings
    (for the "add setting" picker) is advertised via
    ``available_efel_settings``. Features grouped by category are advertised
    via ``available_efeatures_by_category``.

    ``protocols`` is a tuple — not a list — so the obi-one scan framework
    leaves it alone instead of expanding it as a parameter-scan dimension.
    """

    autoselect: bool = Field(
        default=False,
        title="Automatically fill the features and protocols",
        description=(
            "When enabled, protocols and features are selected automatically"
            " using BluePyEModel's auto_targets presets. Manual protocol/feature"
            " selection below is ignored."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    auto_targets_presets: tuple[str, ...] = Field(
        default=("firing_pattern", "ap_waveform", "iv"),
        title="Auto-target presets",
        description=(
            "Preset names from BluePyEModel's AUTO_TARGET_DICT used when"
            " autoselect is enabled. Options: 'firing_pattern', 'ap_waveform',"
            " 'iv', 'validation'."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    protocols: tuple[ProtocolUnion, ...] = Field(
        default_factory=_default_protocols,
        title="Protocols",
        description=(
            "Protocols to extract features from. Defaults mirror the L5PC"
            " example; the frontend can repopulate this from the catalogue and"
            " the protocols returned by"
            " ``/declared/electrical-cell-recording-protocols``."
            " Ignored when autoselect is enabled."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.SELECT_EFEATURES_BY_PROTOCOL,
            "available_efeatures_by_protocol": available_features_by_protocol_name(),
            "available_efeatures_by_category": available_efeatures_by_category(),
            "available_efel_settings": _efel_settings_defaults(),
        },
    )
