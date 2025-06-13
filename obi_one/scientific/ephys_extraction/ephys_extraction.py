"""Electrophys tool."""

import logging
import tempfile
from statistics import mean
from typing import Any, Literal

import entitysdk.client
from bluepyefe.extract import extract_efeatures
from efel.units import get_unit
from entitysdk.models import ElectricalCellRecording
from pydantic import BaseModel, Field

POSSIBLE_PROTOCOLS = {
    "idrest": ["idrest"],
    "idthresh": ["idthres", "idthresh"],
    "iv": ["iv"],
    "apwaveform": ["apwaveform"],
    "spontaneous": ["spontaneous"],
    "step": ["step"],
    "spontaps": ["spontaps"],
    "firepattern": ["firepattern"],
    "sponnohold30": ["sponnohold30", "spontnohold30"],
    "sponthold30": ["sponhold30", "sponthold30"],
    "starthold": ["starthold"],
    "startnohold": ["startnohold"],
    "delta": ["delta"],
    "sahp": ["sahp"],
    "idhyperpol": ["idhyeperpol"],
    "irdepol": ["irdepol"],
    "irhyperpol": ["irhyperpol"],
    "iddepol": ["iddepol"],
    "ramp": ["ramp"],
    "apthresh": ["apthresh", "ap_thresh"],
    "hyperdepol": ["hyperdepol"],
    "negcheops": ["negcheops"],
    "poscheops": ["poscheops"],
    "spikerec": ["spikerec"],
    "sinespec": ["sinespec"],
}


STIMULI_TYPES = list[
    Literal[
        "spontaneous",
        "idrest",
        "idthres",
        "apwaveform",
        "iv",
        "step",
        "spontaps",
        "firepattern",
        "sponnohold30",
        "sponhold30",
        "starthold",
        "startnohold",
        "delta",
        "sahp",
        "idhyperpol",
        "irdepol",
        "irhyperpol",
        "iddepol",
        "ramp",
        "ap_thresh",
        "hyperdepol",
        "negcheops",
        "poscheops",
        "spikerec",
        "sinespec",
    ]
]

CALCULATED_FEATURES = list[
    Literal[
        "spike_count",
        "time_to_first_spike",
        "time_to_last_spike",
        "inv_time_to_first_spike",
        "doublet_ISI",
        "inv_first_ISI",
        "ISI_log_slope",
        "ISI_CV",
        "irregularity_index",
        "adaptation_index",
        "mean_frequency",
        "strict_burst_number",
        "strict_burst_mean_freq",
        "spikes_per_burst",
        "AP_height",
        "AP_amplitude",
        "AP1_amp",
        "APlast_amp",
        "AP_duration_half_width",
        "AHP_depth",
        "AHP_time_from_peak",
        "AP_peak_upstroke",
        "AP_peak_downstroke",
        "voltage_base",
        "voltage_after_stim",
        "ohmic_input_resistance_vb_ssse",
        "steady_state_voltage_stimend",
        "sag_amplitude",
        "decay_time_constant_after_stim",
        "depol_block_bool",
    ]
]


class AmplitudeInput(BaseModel):
    """Amplitude class."""

    min_value: float
    max_value: float


class ElectrophysInput(BaseModel):
    """Inputs of the NeuroM API."""

    trace_id: str = Field(
        description=(
            "ID of the trace of interest. The trace ID is in the form of an HTTP(S)"
            " link such as 'https://bbp.epfl.ch/neurosciencegraph/data/traces...'."
        )
    )
    stimuli_types: STIMULI_TYPES | None = Field(
        default=None,
        description=(
            "Type of stimuli requested by the user. Should be one of 'spontaneous',"
            " 'idrest', 'idthres', 'apwaveform', 'iv', 'step', 'spontaps',"
            " 'firepattern', 'sponnohold30','sponhold30', 'starthold', 'startnohold',"
            " 'delta', 'sahp', 'idhyperpol', 'irdepol', 'irhyperpol','iddepol', 'ramp',"
            " 'ap_thresh', 'hyperdepol', 'negcheops', 'poscheops',"
            " 'spikerec', 'sinespec'."
        ),
    )
    calculated_feature: CALCULATED_FEATURES | None = Field(
        default=None,
        description=(
            "Feature requested by the user. Should be one of 'spike_count',"
            "'time_to_first_spike', 'time_to_last_spike',"
            "'inv_time_to_first_spike', 'doublet_ISI', 'inv_first_ISI',"
            "'ISI_log_slope', 'ISI_CV', 'irregularity_index', 'adaptation_index',"
            "'mean_frequency', 'strict_burst_number', 'strict_burst_mean_freq',"
            "'spikes_per_burst', 'AP_height', 'AP_amplitude', 'AP1_amp', 'APlast_amp',"
            "'AP_duration_half_width', 'AHP_depth', 'AHP_time_from_peak',"
            "'AP_peak_upstroke', 'AP_peak_downstroke', 'voltage_base',"
            "'voltage_after_stim', 'ohmic_input_resistance_vb_ssse',"
            "'steady_state_voltage_stimend', 'sag_amplitude',"
            "'decay_time_constant_after_stim', 'depol_block_bool'"
        ),
    )
    amplitude: AmplitudeInput | None = Field(
        default=None,
        description=(
            "Amplitude of the protocol (should be specified in nA)."
            "Can be a range of amplitudes with min and max values"
            "Can be None (if the user does not specify it)"
            " and all the amplitudes are going to be taken into account."
        ),
    )


class ElectrophysFeatureToolOutput(BaseModel):
    """Output schema for the neurom tool."""

    brain_region: str
    feature_dict: dict[str, Any]


def get_electrophysiology_metrics(# noqa: PLR0914, C901
    trace_id: str,
    entity_client: entitysdk.client.Client,
    calculated_feature: CALCULATED_FEATURES | None = None,
    amplitude: AmplitudeInput | None = None,
    stimuli_types: STIMULI_TYPES | None = None,
) -> ElectrophysFeatureToolOutput:
    """Compute electrophys features for a given trace."""
    logger = logging.getLogger(__name__)

    logger.info(
        "Entering electrophys tool. Inputs: trace_id=%r, calculated_feature=%r, amplitude=%r, stimuli_types=%r",
        trace_id, calculated_feature, amplitude, stimuli_types
    )

    # Deal with cases where user did not specify stimulus type or/and feature
    if not stimuli_types:
        # Default to IDRest if protocol not specified
        logger.warning("No stimulus type specified. Defaulting to IDRest.")
        stimuli_types = ["idrest"]

    if not calculated_feature:
        # Compute ALL of the available features if not specified
        logger.warning("No feature specified. Defaulting to everything.")
        calculated_feature = list(CALCULATED_FEATURES.__args__[0].__args__)  # type: ignore

    # Turn amplitude requirement of user into a bluepyefe compatible representation
    if isinstance(amplitude, AmplitudeInput):
        # If the user specified amplitude/a range of amplitudes,
        # the target amplitude is centered on the range and the
        # tolerance is set as half the range
        desired_amplitude = mean(
            [
                amplitude.min_value,
                amplitude.max_value,
            ]
        )

        # If the range is just one number, use 10% of it as tolerance
        if amplitude.min_value == amplitude.max_value:
            desired_tolerance = amplitude.max_value * 0.1
        else:
            desired_tolerance = amplitude.max_value - desired_amplitude
    else:
        # If the amplitudes are not specified, take an arbitrarily high tolerance
        desired_amplitude = 0
        desired_tolerance = 1e12
    logger.info(
        "target amplitude set to %s nA. Tolerance is %s nA",
        desired_amplitude,
        desired_tolerance,
    )

    targets = []

    for stim_type in stimuli_types:
        for efeature in calculated_feature:
            for protocol in POSSIBLE_PROTOCOLS[stim_type]:
                target = {
                    "efeature": efeature,
                    "protocol": protocol,
                    "amplitude": desired_amplitude,
                    "tolerance": desired_tolerance,
                }
                targets.append(target)
    logger.info("Generated %d targets.", len(targets))
    logger.info("Trace ID: %s", trace_id)
    trace_metadata = entity_client.get_entity(
        entity_id=trace_id,
        entity_type=ElectricalCellRecording
    )
    # Download the .nwb file associated to the trace from the KG
    with (tempfile.NamedTemporaryFile(suffix=".nwb") as temp_file,
            tempfile.TemporaryDirectory() as temp_dir):
        for asset in trace_metadata.assets:
            logger.debug("Asset object: %s", asset)
            if asset.content_type == "application/nwb":
                trace_content = entity_client.download_content(
                    entity_id=trace_id,
                    entity_type=ElectricalCellRecording,
                    asset_id=asset.id
                )
                temp_file.write(trace_content)
                temp_file.flush()
                break
        else:
            raise ValueError(
                f"No asset with content type 'application/nwb' found for trace {trace_id}."
            )

        # LNMC traces need to be adjusted by an output voltage of 14mV due to their experimental protocol
        files_metadata = {
            "test": {
                stim_type: [
                    {
                        "filepath": temp_file.name,
                        "protocol": protocol,
                        "ljp": trace_metadata.ljp,
                    }
                    for protocol in POSSIBLE_PROTOCOLS[stim_type]
                ]
                for stim_type in stimuli_types
            }
        }
        # Extract the requested features for the requested protocols
        efeatures, protocol_definitions, _ = extract_efeatures(
            output_directory=temp_dir,
            files_metadata=files_metadata,
            targets=targets,
            absolute_amplitude=True,
        )
        output_features = {}
        logger.debug("Efeatures: %s", efeatures)
        # Format the extracted features into a readable dict for the model
        for protocol_name in protocol_definitions:
            efeatures_values = efeatures[protocol_name]
            protocol_def = protocol_definitions[protocol_name]
            output_features[protocol_name] = {
                f"{f['efeature_name']} (avg on n={f['n']} trace(s))": (
                    f"{f['val'][0]} {get_unit(f['efeature_name']) if get_unit(f['efeature_name']) != 'constant' else ''}"
                ).strip()
                for f in efeatures_values["soma"]
            }

            # Add the stimulus current of the protocol to the output
            output_features[protocol_name]["stimulus_current"] = f"{protocol_def['step']['amp']} nA"
    return ElectrophysFeatureToolOutput(
        brain_region=trace_metadata.brain_region.name, feature_dict=output_features
    )