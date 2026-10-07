"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.tasks.emodel_building.task1_efeature_extraction.constants import (
    INHERIT_NOTE,
    SPIKE_DETECTION_THRESHOLD_DESCRIPTION,
    SPIKE_DETECTION_THRESHOLD_TITLE,
    TRACE_RESAMPLING_TIMESTEP_DESCRIPTION,
    TRACE_RESAMPLING_TIMESTEP_TITLE,
)

__all__ = [
    "INHERIT_NOTE",
    "SPIKE_DETECTION_THRESHOLD_DESCRIPTION",
    "SPIKE_DETECTION_THRESHOLD_TITLE",
    "TRACE_RESAMPLING_TIMESTEP_DESCRIPTION",
    "TRACE_RESAMPLING_TIMESTEP_TITLE",
]
