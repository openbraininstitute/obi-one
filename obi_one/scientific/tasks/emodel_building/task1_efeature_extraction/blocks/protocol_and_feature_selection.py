"""Block holding the list of protocols with per-protocol feature selections."""

from enum import StrEnum

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (  # noqa: E501
    Protocol,
)


def _available_efeatures_by_protocol() -> dict[str, list[str]]:
    """Build ``{protocol_name: [efel_name, ...]}`` from BluePyEfe's registry.

    Used by the frontend's ``select_efeatures_by_protocol`` UI element to
    populate the feature picker for each protocol.
    """
    from bluepyefe.ecode import PROTOCOL_EFEATURES  # noqa: PLC0415

    return {name: list(features) for name, features in PROTOCOL_EFEATURES.items()}


class AutoTargetPreset(StrEnum):
    """Preset names mirroring BluePyEModel's ``AUTO_TARGET_DICT`` keys."""

    FIRING_PATTERN = "firing_pattern"
    AP_WAVEFORM = "ap_waveform"
    IV = "iv"
    VALIDATION = "validation"


EFEL_DOC_BASE_URL = "https://efel.readthedocs.io/en/latest/eFeatures.html"

EFEL_FIGURES_BASE_URL = (
    "https://raw.githubusercontent.com/openbraininstitute/eFEL/master/docs/source/_static/figures"
)

EFEL_FEATURE_IMAGE_MAP: dict[str, str] = {
    "AHP_depth": "AHP.png",
    "AHP_depth_abs": "AHP.png",
    "AHP_depth_diff": "AHP.png",
    "AHP_depth_from_peak": "AHP.png",
    "AHP1_depth_from_peak": "AHP.png",
    "AHP2_depth_from_peak": "AHP.png",
    "AHP_time_from_peak": "AHP.png",
    "fast_AHP": "AHP.png",
    "fast_AHP_change": "AHP.png",
    "AHP_depth_abs_slow": "AHP.png",
    "AHP_depth_slow": "AHP.png",
    "AHP_slow_time": "AHP.png",
    "min_AHP_indices": "AHP.png",
    "min_AHP_values": "AHP.png",
    "AP_amplitude": "AP_Amplitude.png",
    "AP1_amp": "AP_Amplitude.png",
    "AP2_amp": "AP_Amplitude.png",
    "APlast_amp": "AP_Amplitude.png",
    "mean_AP_amplitude": "AP_Amplitude.png",
    "AP_amplitude_change": "AP_Amplitude.png",
    "AP_amplitude_from_voltagebase": "AP_Amplitude.png",
    "AP_height": "AP_Amplitude.png",
    "AP1_peak": "AP_Amplitude.png",
    "AP2_peak": "AP_Amplitude.png",
    "peak_voltage": "AP_Amplitude.png",
    "AP_duration_half_width": "AP_duration_half_width.png",
    "AP_duration_half_width_change": "AP_duration_half_width.png",
    "AP_width": "AP_duration_half_width.png",
    "AP_duration": "AP_duration_half_width.png",
    "AP_duration_change": "AP_duration_half_width.png",
    "spike_half_width": "AP_duration_half_width.png",
    "AP1_width": "AP_duration_half_width.png",
    "AP2_width": "AP_duration_half_width.png",
    "APlast_width": "AP_duration_half_width.png",
    "AP_rise_time": "AP_duration_half_width.png",
    "AP_fall_time": "AP_duration_half_width.png",
    "ISI_values": "inv_ISI.png",
    "all_ISI_values": "inv_ISI.png",
    "inv_ISI_values": "inv_ISI.png",
    "inv_first_ISI": "inv_ISI.png",
    "inv_second_ISI": "inv_ISI.png",
    "inv_third_ISI": "inv_ISI.png",
    "inv_fourth_ISI": "inv_ISI.png",
    "inv_fifth_ISI": "inv_ISI.png",
    "inv_last_ISI": "inv_ISI.png",
    "doublet_ISI": "inv_ISI.png",
    "ISI_semilog_slope": "inv_ISI.png",
    "ISI_log_slope": "inv_ISI.png",
    "ISI_log_slope_skip": "inv_ISI.png",
    "ISI_CV": "inv_ISI.png",
    "sag_amplitude": "sag.png",
    "sag_ratio1": "sag.png",
    "sag_ratio2": "sag.png",
    "sag_time_constant": "sag.png",
    "voltage_base": "voltage_features.png",
    "steady_state_voltage_stimend": "voltage_features.png",
    "steady_state_voltage": "voltage_features.png",
    "voltage_deflection": "voltage_features.png",
    "voltage_deflection_vb_ssse": "voltage_features.png",
    "voltage_deflection_begin": "voltage_features.png",
    "voltage_after_stim": "voltage_features.png",
    "minimum_voltage": "voltage_features.png",
    "maximum_voltage": "voltage_features.png",
    "ohmic_input_resistance": "voltage_features.png",
    "ohmic_input_resistance_vb_ssse": "voltage_features.png",
}


def efel_feature_doc_url(feature_name: str) -> str:
    """Return the eFEL documentation URL for a specific feature."""
    return f"{EFEL_DOC_BASE_URL}#{feature_name}"


def efel_feature_image_url(feature_name: str) -> str | None:
    """Return the raw GitHub image URL for a feature, or None if no image exists."""
    filename = EFEL_FEATURE_IMAGE_MAP.get(feature_name)
    if filename is None:
        return None
    return f"{EFEL_FIGURES_BASE_URL}/{filename}"


def _default_protocols() -> tuple[Protocol, ...]:
    """L5PC-style defaults — set ``extract=True`` on the same features the old
    ``ExtractionTargets`` mirror used. Amplitudes are no longer a user
    parameter (they're read from the NWB at task execution time), so this only
    pre-selects features.
    """
    idrest = Protocol.from_protocol_name("IDrest")
    for fname in (
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
        "min_AHP_values",
        "depol_block_bool",
        "voltage_base",
    ):
        if fname in idrest.features:
            idrest.features[fname].extract = True

    iv = Protocol.from_protocol_name("IV")
    if "voltage_base" in iv.features:
        iv.features["voltage_base"].extract = True
    if "ohmic_input_resistance_vb_ssse" in iv.features:
        iv.features["ohmic_input_resistance_vb_ssse"].extract = True

    apwaveform = Protocol.from_protocol_name("APWaveform")
    for fname in ("AP_amplitude", "AP1_amp", "AP_duration_half_width", "AHP_depth"):
        if fname in apwaveform.features:
            apwaveform.features[fname].extract = True

    sahp = Protocol.from_protocol_name("sAHP")
    for fname in ("mean_frequency", "voltage_base", "depol_block_bool"):
        if fname in sahp.features:
            sahp.features[fname].extract = True

    idthresh = Protocol.from_protocol_name("IDthresh")
    idthresh.is_rheobase_protocol = True

    return (idthresh, idrest, iv, apwaveform, sahp)


class ProtocolAndFeatureSelection(Block):
    """Per-protocol picker for timing, LJP, amplitudes, and chosen efeatures.

    ``threshold_based`` controls whether per-protocol ``extraction_amplitudes``
    are interpreted as relative (% of rheobase) or absolute (nA, auto-discovered
    from the NWB).

    Each entry in ``protocols`` is a :class:`Protocol` instance carrying its
    own stimulus timing (``ton``/``toff``/``tmid``/``tmid2``), liquid junction
    potential (``ljp``), and a ``features`` dict of valid :class:`EFeature`
    instances keyed by eFEL feature name. Whether each feature is actually
    extracted is controlled by its own ``extract`` flag. The valid features
    per protocol are sourced from bluepyefe's
    :func:`bluepyefe.ecode.get_valid_efeatures`.

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
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

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

    auto_targets_presets: str = Field(
        default="firing_pattern,ap_waveform,iv",
        title="Auto-target presets",
        description=(
            "Presets from BluePyEModel's AUTO_TARGET_DICT used when autoselect"
            " is enabled. Select one or more: 'firing_pattern', 'ap_waveform',"
            " 'iv', 'validation'."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    protocols: tuple[Protocol, ...] = Field(  # ty:ignore[invalid-assignment]
        default_factory=_default_protocols,
        title="Protocols",
        description=(
            "Protocols to extract features from. Defaults mirror the L5PC"
            " example; the frontend can repopulate this from the catalogue and"
            " the protocols discovered from the recordings' NWB files."
            " Ignored when autoselect is enabled."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.SELECT_EFEATURES_BY_PROTOCOL,
            "available_efeatures_by_protocol": _available_efeatures_by_protocol(),
            "efel_doc_base_url": EFEL_DOC_BASE_URL,
            "efel_figures_base_url": EFEL_FIGURES_BASE_URL,
            "efel_feature_image_map": EFEL_FEATURE_IMAGE_MAP,
        },
    )
