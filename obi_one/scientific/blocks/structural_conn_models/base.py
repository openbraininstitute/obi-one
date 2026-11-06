"""Structural connectivity models.

A ``PathwayStructuralConnModel`` block encapsulates the mathematical model that decides which
(source, target) neuron pairs become connected for a single pathway. Concrete subclasses each
implement :meth:`draw_connections`, so the connectivity-generation task can be parameterized with
different models (Erdos-Renyi, distance-dependent, ...) without changing the task itself.

The models operate purely on node IDs and 3D positions; they do not read or write SONATA files
themselves. The calling task resolves the source/target neuron sets to node IDs and positions and
passes them in via a :class:`PathwayConnContext`.
"""

import abc
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement


@dataclass(frozen=True)
class PathwayConnContext:
    """Inputs a structural connectivity model needs to draw connections for one pathway.

    A pathway connects exactly one source node population to one target node population (a neuron
    set spanning several populations is split into one context per ordered population pair by the
    caller).

    Attributes:
        source_ids: Node IDs of the source (presynaptic) population, shape ``(n_source,)``.
        target_ids: Node IDs of the target (postsynaptic) population, shape ``(n_target,)``.
        source_positions: ``(n_source, 3)`` x/y/z coordinates aligned with ``source_ids``.
            ``None`` when the source population exposes no x/y/z properties.
        target_positions: ``(n_target, 3)`` x/y/z coordinates aligned with ``target_ids``.
            ``None`` when the target population exposes no x/y/z properties.
        same_population: Whether source and target are the same node population, which is the
            only case in which a source and a target ID can denote the same neuron.
    """

    source_ids: np.ndarray
    target_ids: np.ndarray
    source_positions: np.ndarray | None
    target_positions: np.ndarray | None
    same_population: bool


class PathwayStructuralConnModel(Block, abc.ABC):
    """Abstract base class for structural (which-neuron-connects-to-which) connectivity models.

    A concrete model draws the set of connected (source, target) node-ID pairs for one pathway.
    It produces connectivity only; no per-edge physiological parameters are generated here.
    """

    allow_self_connections: bool = Field(
        default=False,
        title="Allow self-connections",
        description="Whether a neuron may connect to itself when it is part of both the source"
        " and the target neuron set of the same population.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    @abc.abstractmethod
    def draw_connections(
        self, context: PathwayConnContext, rng: np.random.Generator
    ) -> tuple[np.ndarray, np.ndarray]:
        """Draw the connected (source_node_id, target_node_id) pairs for one pathway.

        Args:
            context: Source/target node IDs and positions plus the same-population flag for this
                pathway.
            rng: Random generator to draw from, so results are reproducible for a given seed.

        Returns:
            A tuple ``(pre_node_ids, post_node_ids)`` of equal-length ``int64`` arrays listing
            the connected pairs. Empty arrays when no connection is drawn.
        """

    @staticmethod
    def _empty() -> tuple[np.ndarray, np.ndarray]:
        """An empty (pre, post) result."""
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)

    def _draw_per_target(
        self,
        context: PathwayConnContext,
        rng: np.random.Generator,
        probability_for_target: Callable[[int, np.ndarray], np.ndarray | float],
    ) -> tuple[np.ndarray, np.ndarray]:
        """Draw connections target-by-target given a per-target source-probability function.

        Shared by the concrete models: for each target neuron, ``probability_for_target`` returns
        the connection probability of every available source (an array aligned with the available
        sources, or a scalar applied to all of them). Each source is then connected independently
        with its probability. Iterating per target keeps the memory cost proportional to the
        number of connections drawn rather than to the full source x target product.

        A self-connection is excluded unless ``self.allow_self_connections`` is set (and only when
        source and target are the same population, the only case it can arise).

        Args:
            context: The pathway context.
            rng: Random generator.
            probability_for_target: Callable ``(target_index, available_mask) -> probabilities``
                where ``available_mask`` selects the sources eligible for that target (it drops a
                self-connection when disallowed). The returned probabilities are aligned with the
                available (masked) sources.
        """
        source_ids = context.source_ids
        target_ids = context.target_ids
        if source_ids.size == 0 or target_ids.size == 0:
            return self._empty()

        pre_chunks: list[np.ndarray] = []
        post_chunks: list[np.ndarray] = []
        for target_index, target in enumerate(target_ids):
            available_mask = np.ones(source_ids.size, dtype=bool)
            if context.same_population and not self.allow_self_connections:
                available_mask &= source_ids != target
            if not available_mask.any():
                continue

            probabilities = np.asarray(
                probability_for_target(target_index, available_mask), dtype=float
            )
            available_sources = source_ids[available_mask]
            draws = rng.random(available_sources.size)
            connected = available_sources[draws < probabilities]
            if connected.size == 0:
                continue
            pre_chunks.append(connected.astype(np.int64, copy=False))
            post_chunks.append(np.full(connected.size, target, dtype=np.int64))

        if not pre_chunks:
            return self._empty()
        return np.concatenate(pre_chunks), np.concatenate(post_chunks)
