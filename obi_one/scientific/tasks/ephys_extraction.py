"""Electrophys tool."""

from typing import ClassVar

import entitysdk.client
from fastapi import HTTPException
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.library.ephys_extraction import (
    CALCULATED_FEATURES,
    POSSIBLE_STIMULI_STR,
    STIMULI_TYPES,
    AmplitudeInput,
    ElectrophysiologyMetricsOutput,
    get_electrophysiology_metrics,
)


class ElectrophysiologyMetricsScanConfig(ScanConfig):
    """ScanConfig for extracting electrophysiological metrics from a trace."""

    single_coord_class_name: ClassVar[str] = "ElectrophysiologyMetricsSingleConfig"
    name: ClassVar[str] = "Electrophysiology Metrics"
    description: ClassVar[str] = "Calculates ephys metrics for a given trace."

    class Initialize(Block):
        trace_id: str = Field(description="ID of the trace of interest.")
        protocols: STIMULI_TYPES | None = Field(
            default=None,
            description=f"Type of stimuli requested by the user. Should be one \
                of: '{POSSIBLE_STIMULI_STR}'.",
        )
        requested_metrics: CALCULATED_FEATURES | None = Field(
            default=None,
            description="Feature requested by the user. Should be one of 'spike_count',"
            "'time_to_first_spike', 'time_to_last_spike',"
            "'inv_time_to_first_spike', 'doublet_ISI', 'inv_first_ISI',"
            "'ISI_log_slope', 'ISI_CV', 'irregularity_index', 'adaptation_index',"
            "'mean_frequency', 'strict_burst_number', 'strict_burst_mean_freq',"
            "'spikes_per_burst', 'AP_height', 'AP_amplitude', 'AP1_amp', 'APlast_amp',"
            "'AP_duration_half_width', 'AHP_depth', 'AHP_time_from_peak',"
            "'AP_peak_upstroke', 'AP_peak_downstroke', 'voltage_base',"
            "'voltage_after_stim', 'ohmic_input_resistance_vb_ssse',"
            "'steady_state_voltage_stimend', 'sag_amplitude',"
            "'decay_time_constant_after_stim', 'depol_block_bool'",
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

    initialize: Initialize


class ElectrophysiologyMetricsSingleConfig(ElectrophysiologyMetricsScanConfig, SingleConfigMixin):
    """Calculates electrophysiological metrics for a given trace."""


class ElectrophysiologyMetricsTask(Task):
    """Task to calculate electrophysiological metrics for a given trace."""

    config: ElectrophysiologyMetricsSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,
        entity_cache: bool = False,  # noqa: ARG002
    ) -> ElectrophysiologyMetricsOutput:
        try:
            ephys_metrics = get_electrophysiology_metrics(
                trace_id=self.config.initialize.trace_id,
                entity_client=db_client,
                calculated_feature=self.config.initialize.requested_metrics,
                amplitude=self.config.initialize.amplitude,
                stimuli_types=self.config.initialize.protocols,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}") from e
        else:
            return ephys_metrics
