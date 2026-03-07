"""Module with shared types."""

import os
from enum import StrEnum, auto

StrOrPath = str | os.PathLike[str]


class SimulationBackend(StrEnum):
    bluecellulab = auto()
    neurodamus = auto()
