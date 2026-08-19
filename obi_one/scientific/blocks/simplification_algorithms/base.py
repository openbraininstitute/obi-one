from typing import ClassVar

from obi_one.core.block import Block


class SimplificationAlgorithm(Block):
    """Base class for a selectable circuit-simplification algorithm."""

    algorithm_name: ClassVar[str]
