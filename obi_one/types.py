"""Module with shared types."""

import os
from enum import StrEnum, auto

StrOrPath = str | os.PathLike[str]


class SimulationBackend(StrEnum):
    bluecellulab = auto()
    neurodamus = auto()


class TaskType(StrEnum):
    """Task types supported for job submission."""

    circuit_extraction = auto()
    circuit_simulation = auto()
    morphology_skeletonization = auto()
    ion_channel_model_simulation_execution = auto()
    em_synapse_mapping = auto()
