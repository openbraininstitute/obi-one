"""Shared titles and descriptions for settings exposed at multiple cascade levels.

``spike_detection_threshold`` and ``trace_resampling_timestep`` are eFEL detection
knobs declared on ``Settings`` (global), ``Protocol``, and ``EFeature`` with
precedence feature > protocol > global. Declaring their user-facing titles and
descriptions here keeps the three field declarations in sync.
"""

SPIKE_DETECTION_THRESHOLD_TITLE = "Spike detection threshold"
SPIKE_DETECTION_THRESHOLD_DESCRIPTION = (
    "eFEL ``Threshold``: voltage above which a spike is detected (mV)."
)

TRACE_RESAMPLING_TIMESTEP_TITLE = "Trace resampling timestep"
TRACE_RESAMPLING_TIMESTEP_DESCRIPTION = (
    "eFEL ``interp_step``: time step the trace is resampled to before extraction (ms)."
)

# Appended to the protocol- and feature-level descriptions: when the field is left
# unset it inherits the setting from the level above.
INHERIT_NOTE = "Leave unset to inherit from the level above (feature > protocol > global)."
