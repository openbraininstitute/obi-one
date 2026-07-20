"""eFEL documentation links and feature figure URLs.

The frontend's ``select_efeatures_by_protocol`` UI element uses these to link
each eFEL feature to its documentation entry and, where one exists, to an
illustrative figure from the eFEL docs. Features without an entry in
:data:`EFEL_FEATURE_IMAGE_MAP` simply have no figure.
"""

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
