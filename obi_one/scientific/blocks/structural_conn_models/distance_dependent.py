"""Distance-dependent structural connectivity model."""

from typing import ClassVar

import numpy as np
from pydantic import Field, PositiveFloat

from obi_one.core.exception import OBIONEError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.structural_conn_models.base import (
    PathwayConnContext,
    PathwayStructuralConnModel,
)


class DistanceDependentConnModel(PathwayStructuralConnModel):
    """Distance-dependent connectivity: the connection probability decreases exponentially with
    the Euclidean distance between the source and target neuron positions.

    The probability that a source at position ``p_s`` connects to a target at position ``p_t`` is

        P(d) = c * exp(-d / length_scale),   d = ||p_s - p_t||

    clipped to ``[0, 1]``. Distances use the x/y/z coordinates of the source and target node
    populations.
    """

    title: ClassVar[str] = "Distance-dependent (exponential)"
    description: ClassVar[str] = (
        "Connects source/target neuron pairs with a probability that decays exponentially with"
        " the Euclidean distance between their x/y/z positions."
    )

    scale_factor: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        title="Scale factor",
        description="Connection probability at zero distance (the coefficient c in"
        " P(d) = c * exp(-d / length_scale)).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_INPUT,
        },
    )
    length_scale: PositiveFloat = Field(
        title="Length scale",
        description="Characteristic decay distance (the length scale in"
        " P(d) = c * exp(-d / length_scale)); larger values give longer-range connectivity.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_INPUT,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )

    def draw_connections(
        self, context: PathwayConnContext, rng: np.random.Generator
    ) -> tuple[np.ndarray, np.ndarray]:
        """Connect pairs with an exponentially distance-decaying probability."""
        if self.scale_factor <= 0.0:
            return self._empty()
        if context.source_positions is None or context.target_positions is None:
            msg = (
                "Distance-dependent connectivity requires x/y/z positions for both the source"
                " and target populations, but at least one population exposes none."
            )
            raise OBIONEError(msg)

        source_positions = context.source_positions
        target_positions = context.target_positions

        def probability_for_target(target_index: int, available_mask: np.ndarray) -> np.ndarray:
            target_pos = target_positions[target_index]
            distances = np.linalg.norm(source_positions[available_mask] - target_pos, axis=1)
            probabilities = self.scale_factor * np.exp(-distances / self.length_scale)
            return np.clip(probabilities, 0.0, 1.0)

        return self._draw_per_target(context, rng, probability_for_target)
