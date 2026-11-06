"""Erdos-Renyi structural connectivity model."""

from typing import ClassVar

import numpy as np
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.structural_conn_models.base import (
    PathwayConnContext,
    PathwayStructuralConnModel,
)


class ErdosRenyiConnModel(PathwayStructuralConnModel):
    """Erdos-Renyi connectivity: every ordered (source, target) pair is connected independently
    with the same fixed probability.
    """

    title: ClassVar[str] = "Erdos-Renyi"
    description: ClassVar[str] = (
        "Connects every ordered source/target neuron pair independently with a single fixed"
        " connection probability."
    )

    connection_probability: float = Field(
        ge=0.0,
        le=1.0,
        title="Connection probability",
        description="Probability that any given ordered (source, target) neuron pair is connected.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_INPUT,
        },
    )

    def draw_connections(
        self, context: PathwayConnContext, rng: np.random.Generator
    ) -> tuple[np.ndarray, np.ndarray]:
        """Connect each available source to each target with the fixed probability."""
        if self.connection_probability <= 0.0:
            return self._empty()

        probability = self.connection_probability

        def probability_for_target(_target_index: int, available_mask: np.ndarray) -> np.ndarray:
            return np.full(int(available_mask.sum()), probability)

        return self._draw_per_target(context, rng, probability_for_target)
