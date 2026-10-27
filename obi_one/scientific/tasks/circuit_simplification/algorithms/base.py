from typing import Any, ClassVar

from obi_one.core.block import Block


class SimplificationAlgorithm(Block):
    """Base class for a selectable circuit-simplification algorithm."""

    algorithm_name: ClassVar[str]

    def pipeline_kwargs(self) -> dict[str, Any]:  # ruff: ignore[no-self-use]
        """Algorithm-specific keyword arguments for ``SimplificationPipeline``."""
        return {}
