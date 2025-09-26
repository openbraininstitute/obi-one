"""Electrophys tool."""

import logging
import tempfile
from io import StringIO
from statistics import mean
from typing import Any, Literal

import entitysdk.client
from bluepyefe.extract import extract_efeatures
from efel.units import get_unit
from entitysdk.models import ElectricalCellRecording
from pydantic import BaseModel, Field

from obi_one.core.exception import ProtocolNotFoundError

EFEL_SETTINGS = {"strict_stiminterval": True, "Threshold": -20.0, "interp_step": 0.025}

STIMULI_TYPES = list[
    Literal[
        "spontaneous",
        "idrest",
        "idthreshold",
        "apwaveform",
        "iv",
        "step",
        "sponaps",
        "firepattern",
        "spontaneousnohold",
        "starthold",
        "startnohold",
        "delta",
        "sahp",
        "idhyperpol",
        "irdepol",
        "irhyperpol",
        "iddepol",
        "apthreshold",
        "hyperdepol",
        "negcheops",
        "poscheops",
        "spikerec",
        "sinespec",
        "genericstep",
    ]
]
POSSIBLE_STIMULI_STR = "', '".join(STIMULI_TYPES.__args__[0].__args__)

STEP_LIKE_STIMULI_TYPES = list[
    Literal[
        "idrest",
        "idthreshold",
        "apwaveform",
        "iv",
        "step",
        "firepattern",
        "delta",
        "genericstep",
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

    min_value: float | None = Field(default=None, description="Minimum amplitude (nA)")
    max_value: float | None = Field(default=None, description="Maximum amplitude (nA)")


class ElectrophysiologyMetricsOutput(BaseModel):
    """Output schema for electrophysiological metrics extracted using BluePyEfe."""

    feature_dict: dict[str, dict[str, Any]] = Field(
        description="Mapping of feature name to its metric values. "
        "Each entry contains at least an 'avg', and optionally 'unit', 'num_traces', etc."
    )

    @classmethod
    def from_efeatures(cls, raw: dict[str, Any]) -> "ElectrophysiologyMetricsOutput":
        return cls(feature_dict=raw)


def get_electrophysiology_metrics(  # noqa: PLR0912, PLR0914, PLR0915, C901
    trace_id: str,
    entity_client: entitysdk.client.Client,
    calculated_feature: CALCULATED_FEATURES | None = None,
    amplitude: AmplitudeInput | None = None,
    stimuli_types: STIMULI_TYPES | None = None,
) -> ElectrophysiologyMetricsOutput:
    """Compute electrophys features for a given trace."""
    logger = logging.getLogger(__name__)

    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.WARNING)
    logging.getLogger("bluepyefe.extract").addHandler(handler)

    logger.info(
        "Entering electrophys tool. Inputs: trace_id=%r, calculated_feature=%r, amplitude=%r, \
            stimuli_types=%r",
        trace_id,
        calculated_feature,
        amplitude,
        stimuli_types,
    )

    # Get the trace metadata from the entitycore
    trace_metadata = entity_client.get_entity(
        entity_id=trace_id, entity_type=ElectricalCellRecording
    )

    # Get the available stimulus types from the trace metadata
    available_stimuli = {stimulus.name.lower() for stimulus in trace_metadata.stimuli}

    # If the user did not specify any stimulus types, try to use all step-like stimuli present in
    # the trace.
    if not stimuli_types:
        stimuli_types = [
            s for s in available_stimuli if s in STEP_LIKE_STIMULI_TYPES.__args__[0].__args__
        ]

        if not stimuli_types:
            logger.warning(
                "No stimulus type specified, and no valid stimuli found in the trace metadata. "
                "Falling back to default STEP_LIKE_STIMULI_TYPES."
            )
            stimuli_types = list(STEP_LIKE_STIMULI_TYPES.__args__[0].__args__)
        else:
            msg = f"No stimulus type specified. Using all valid stimuli found in the trace: \
                    {stimuli_types}"
            logger.warning(msg)
    else:
        # Validate the user-specified stimuli types against the available ones in the trace metadata
        valid_stimuli = [s for s in stimuli_types if s in available_stimuli]
        invalid_stimuli = set(stimuli_types) - set(valid_stimuli)

        if not valid_stimuli:
            msg = (
                f"None of the requested protocols {stimuli_types} are present in the trace. "
                f"Available: {sorted(available_stimuli)}"
            )
            raise ProtocolNotFoundError(msg)

        if invalid_stimuli:
            msg = (
                f"The following stimulus types are not present in the trace and will be ignored: "
                f"{sorted(invalid_stimuli)}"
            )
            logger.warning(msg)

        stimuli_types = valid_stimuli

    if not calculated_feature:
        # Compute ALL of the available features if not specified
        logger.warning("No feature specified. Defaulting to everything.")
        calculated_feature = list(CALCULATED_FEATURES.__args__[0].__args__)

    # Turn amplitude requirement of user into a bluepyefe compatible representation
    if (
        isinstance(amplitude, AmplitudeInput)
        and amplitude.min_value is not None
        and amplitude.max_value is not None
    ):
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
        desired_tolerance = amplitude.max_value - desired_amplitude
        if amplitude.min_value == amplitude.max_value:
            desired_tolerance = amplitude.max_value * 0.1

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
            target = {
                "efeature": efeature,
                "protocol": stim_type,
                "amplitude": desired_amplitude,
                "tolerance": desired_tolerance,
            }
            targets.append(target)
    logger.info("Generated %d targets.", len(targets))
    logger.info("Trace ID: %s", trace_id)
    trace_metadata = entity_client.get_entity(
        entity_id=trace_id, entity_type=ElectricalCellRecording
    )
    # Download the .nwb file associated to the trace from the KG
    with (
        tempfile.NamedTemporaryFile(suffix=".nwb") as temp_file,
        tempfile.TemporaryDirectory() as temp_dir,
    ):
        for asset in trace_metadata.assets:
            logger.debug("Asset object: %s", asset)
            if asset.content_type == "application/nwb":
                trace_content = entity_client.download_content(
                    entity_id=trace_id, entity_type=ElectricalCellRecording, asset_id=asset.id
                )
                temp_file.write(trace_content)
                temp_file.flush()
                break
        else:
            msg = f"No asset with content type 'application/nwb' found for trace {trace_id}."
            raise ValueError(msg)

        # LNMC traces need to be adjusted by an output voltage of 14mV due to their experimental
        # protocol
        files_metadata = {
            "test": {
                stim_type: [
                    {
                        "filepath": temp_file.name,
                        "protocol": stim_type,
                        "ljp": trace_metadata.ljp,
                    }
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
            efel_settings=EFEL_SETTINGS,
        )

        missing_protocols = parse_bpe_logs(log_stream)

        # If all requested protocols are missing from the data
        if set(stimuli_types).issubset(set(missing_protocols)):
            msg = (
                f"None of the requested protocols {stimuli_types} are present in the trace. "
                f"Available: {sorted(available_stimuli)}"
            )
            raise ProtocolNotFoundError(msg)

        output_features = {}
        logger.debug("Efeatures: %s", efeatures)
        # Format the extracted features into a readable dict for the model
        for protocol_name in protocol_definitions:
            efeatures_values = efeatures[protocol_name]
            protocol_def = protocol_definitions[protocol_name]
            output_features[protocol_name] = {
                f["efeature_name"]: {
                    "avg": f["val"][0],
                    "num_traces": f["n"],
                    "unit": get_unit(f["efeature_name"])
                    if get_unit(f["efeature_name"]) != "constant"
                    else None,
                }
                for f in efeatures_values["soma"]
            }

            # Add the stimulus current of the protocol to the output
            output_features[protocol_name]["stimulus_current"] = f"{protocol_def['step']['amp']} nA"
    logging.getLogger("bluepyefe.extract").removeHandler(handler)
    return ElectrophysiologyMetricsOutput.from_efeatures(output_features)


def parse_bpe_logs(log_stream: StringIO) -> list[str]:
    """Parse the BluePyEfe log stream to extract missing protocols.

    Args:
        log_stream (StringIO): The BPE log stream containing log messages.

    Returns:
        missing_protocols (list): Protocols not found in any cell recordings.
    """
    log_contents = log_stream.getvalue()
    missing_protocols = []

    for line in log_contents.splitlines():
        if "not found in any cell recordings" in line:
            # Extract protocol name from log line
            proto = line.split("'")[1]
            missing_protocols.append(proto)

    return missing_protocols
