"""Block holding the list of protocols with per-protocol feature selections."""

from dataclasses import fields as dataclass_fields

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.protocols_and_features import (  # noqa: E501
    IV,
    SAHP,
    APWaveform,
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
    """Group ALL eFEL features by their category.

    Returns ``{"Spike event features": ["peak_indices", ...], ...}`` for the
    frontend's "Add more features" modal. Includes all 182 eFEL features
    (not just the curated subset with dedicated classes).

    Categories are derived from the eFEL documentation structure:
    - Spike event features (69): timing, ISI, burst, frequency features
    - Spike shape features (76): amplitude, AHP, AP shape, rise/fall features
    - Subthreshold features (27): voltage base, sag, impedance, time constants
    - Extracellular features (10): peak_to_valley, halfwidth, etc.
    """
    return _EFEL_FEATURE_CATEGORIES.copy()


# Full eFEL feature catalogue grouped by category.
# Parsed from eFEL docs/source/eFeatures.rst (eFEL v5.x / tag 1.0.43).
# Doc URL per feature: https://efel.readthedocs.io/en/latest/eFeatures.html#<feature_name>
_EFEL_FEATURE_CATEGORIES: dict[str, list[str]] = {
    "Spike event features": [
        "peak_indices",
        "peak_time",
        "time_to_first_spike",
        "time_to_last_spike",
        "time_to_second_spike",
        "inv_time_to_first_spike",
        "ISI_values",
        "all_ISI_values",
        "inv_ISI_values",
        "inv_first_ISI",
        "inv_second_ISI",
        "inv_third_ISI",
        "inv_fourth_ISI",
        "inv_fifth_ISI",
        "inv_last_ISI",
        "doublet_ISI",
        "ISI_semilog_slope",
        "ISI_log_slope",
        "ISI_log_slope_skip",
        "ISI_CV",
        "irregularity_index",
        "adaptation_index",
        "adaptation_index_2",
        "spike_count",
        "spike_count_stimint",
        "number_initial_spikes",
        "mean_frequency",
        "burst_begin_indices",
        "burst_end_indices",
        "strict_burst_mean_freq",
        "burst_ISI_indices",
        "burst_mean_freq",
        "strict_burst_number",
        "burst_number",
        "single_burst_ratio",
        "spikes_per_burst",
        "spikes_per_burst_diff",
        "spikes_in_burst1_burst2_diff",
        "spikes_in_burst1_burstlast_diff",
        "strict_interburst_voltage",
        "interburst_voltage",
        "interburst_min_indices",
        "interburst_min_values",
        "interburst_duration",
        "interburst_15percent_indices",
        "interburst_20percent_indices",
        "interburst_25percent_indices",
        "interburst_30percent_indices",
        "interburst_40percent_indices",
        "interburst_60percent_indices",
        "interburst_15percent_values",
        "interburst_20percent_values",
        "interburst_25percent_values",
        "interburst_30percent_values",
        "interburst_40percent_values",
        "interburst_60percent_values",
        "time_to_interburst_min",
        "time_to_postburst_slow_ahp",
        "postburst_min_indices",
        "postburst_min_values",
        "postburst_slow_ahp_indices",
        "postburst_slow_ahp_values",
        "postburst_fast_ahp_indices",
        "postburst_fast_ahp_values",
        "postburst_adp_peak_indices",
        "postburst_adp_peak_values",
        "time_to_postburst_fast_ahp",
        "time_to_postburst_adp_peak",
        "check_ais_initiation",
    ],
    "Spike shape features": [
        "peak_voltage",
        "AP_height",
        "AP_amplitude",
        "AP1_amp",
        "AP2_amp",
        "APlast_amp",
        "mean_AP_amplitude",
        "AP_amplitude_change",
        "AP_amplitude_from_voltagebase",
        "AP1_peak",
        "AP2_peak",
        "AP2_AP1_diff",
        "AP2_AP1_peak_diff",
        "amp_drop_first_second",
        "amp_drop_first_last",
        "amp_drop_second_last",
        "max_amp_difference",
        "AP_amplitude_diff",
        "min_AHP_indices",
        "min_AHP_values",
        "AHP_depth",
        "AHP_depth_abs",
        "AHP_depth_diff",
        "AHP_depth_from_peak",
        "AHP1_depth_from_peak",
        "AHP2_depth_from_peak",
        "AHP_time_from_peak",
        "fast_AHP",
        "fast_AHP_change",
        "AHP_depth_abs_slow",
        "AHP_depth_slow",
        "AHP_slow_time",
        "ADP_peak_indices",
        "ADP_peak_values",
        "ADP_peak_amplitude",
        "depolarized_base",
        "min_voltage_between_spikes",
        "min_between_peaks_indices",
        "min_between_peaks_values",
        "AP_rise_indices",
        "AP_fall_indices",
        "AP_duration_half_width",
        "AP_duration_half_width_change",
        "AP_width",
        "AP_duration",
        "AP_duration_change",
        "AP_width_between_threshold",
        "spike_half_width",
        "AP1_width",
        "AP2_width",
        "APlast_width",
        "spike_width2",
        "AP_begin_width",
        "AP1_begin_width",
        "AP2_begin_width",
        "AP2_AP1_begin_width_diff",
        "AP_begin_indices",
        "AP_end_indices",
        "AP_begin_voltage",
        "AP1_begin_voltage",
        "AP2_begin_voltage",
        "AP_begin_time",
        "AP_peak_upstroke",
        "AP_peak_downstroke",
        "AP_rise_time",
        "AP_fall_time",
        "AP_rise_rate",
        "AP_fall_rate",
        "AP_rise_rate_change",
        "AP_fall_rate_change",
        "AP_phaseslope",
        "phaseslope_max",
        "initburst_sahp",
        "initburst_sahp_ssse",
        "initburst_sahp_vb",
        "bpap_attenuation",
    ],
    "Subthreshold features": [
        "steady_state_voltage_stimend",
        "steady_state_current_stimend",
        "steady_state_hyper",
        "steady_state_voltage",
        "voltage_base",
        "current_base",
        "time_constant",
        "decay_time_constant_after_stim",
        "multiple_decay_time_constant_after_stim",
        "sag_time_constant",
        "sag_amplitude",
        "sag_ratio1",
        "sag_ratio2",
        "ohmic_input_resistance",
        "ohmic_input_resistance_vb_ssse",
        "voltage_deflection_vb_ssse",
        "voltage_deflection",
        "voltage_deflection_begin",
        "voltage_after_stim",
        "minimum_voltage",
        "maximum_voltage",
        "maximum_voltage_from_voltagebase",
        "depol_block_bool",
        "impedance",
        "activation_time_constant",
        "deactivation_time_constant",
        "inactivation_time_constant",
    ],
    "Extracellular features": [
        "peak_to_valley",
        "halfwidth",
        "repolarization_slope",
        "recovery_slope",
        "neg_peak_relative",
        "pos_peak_relative",
        "neg_peak_diff",
        "pos_peak_diff",
        "neg_image",
        "pos_image",
    ],
}

EFEL_DOC_BASE_URL = "https://efel.readthedocs.io/en/latest/eFeatures.html"

# GitHub raw URL base for feature illustration images (PNG).
# Only a subset of features have dedicated images in the eFEL repo.
# Source: https://github.com/openbraininstitute/eFEL/tree/master/docs/source/_static/figures
EFEL_FIGURES_BASE_URL = (
    "https://raw.githubusercontent.com/openbraininstitute/eFEL/master/docs/source/_static/figures"
)

# Mapping of feature names (or feature groups) → image filename in the eFEL repo.
# The frontend can use this to show an inline illustration when the user hovers
# or clicks the info icon on a feature. Features not in this dict have no image
# — the frontend should fall back to the doc hyperlink only.
EFEL_FEATURE_IMAGE_MAP: dict[str, str] = {
    # AHP-related features → AHP.png
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
    # AP amplitude features → AP_Amplitude.png
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
    # AP duration/width features → AP_duration_half_width.png
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
    # ISI features → inv_ISI.png
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
    # Sag features → sag.png
    "sag_amplitude": "sag.png",
    "sag_ratio1": "sag.png",
    "sag_ratio2": "sag.png",
    "sag_time_constant": "sag.png",
    # Voltage base / subthreshold features → voltage_features.png
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
    """Return the eFEL documentation URL for a specific feature.

    Links to the anchor on the eFEL eFeatures page, e.g.:
    https://efel.readthedocs.io/en/latest/eFeatures.html#mean_frequency
    """
    return f"{EFEL_DOC_BASE_URL}#{feature_name}"


def efel_feature_image_url(feature_name: str) -> str | None:
    """Return the raw GitHub image URL for a feature, or None if no image exists.

    Example:
    >>> efel_feature_image_url("AP_amplitude")
    'https://raw.githubusercontent.com/.../AP_Amplitude.png'
    >>> efel_feature_image_url("mean_frequency")
    None
    """
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

    protocols: tuple[ProtocolUnion, ...] = Field(  # ty:ignore[invalid-assignment]
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
            "efel_doc_base_url": EFEL_DOC_BASE_URL,
            "efel_figures_base_url": EFEL_FIGURES_BASE_URL,
            "efel_feature_image_map": EFEL_FEATURE_IMAGE_MAP,
        },
    )
