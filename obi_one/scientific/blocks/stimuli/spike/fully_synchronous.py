"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.blocks.stimuli.spike.fully_synchronous import (
    ClassVar,
    defaultdict,
    FullySynchronousSpikeStimulus,
    SpikeStimulus,
)

__all__ = [
    "ClassVar",
    "defaultdict",
    "FullySynchronousSpikeStimulus",
    "SpikeStimulus",
]
