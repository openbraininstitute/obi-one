"""Base classes for Brian2 block handlers.

Each OBI-ONE block type (stimulus, recording, manipulation) has a mirrored
Brian2 handler class that translates the SONATA config entry to Brian2 API
calls. If a feature is not supported in Brian2, the handler raises
Brian2FeatureNotSupportedError.
"""

from abc import ABC, abstractmethod
from typing import Any

import numpy as np

from obi_one.core.exception import OBIONEError


class Brian2FeatureNotSupportedError(OBIONEError):
    """Raised when a SONATA feature is not supported in Brian2."""


class Brian2InputHandler(ABC):
    """Base handler for translating a SONATA ``inputs`` entry to Brian2 objects.

    Subclasses create the Brian2 stimulus objects (e.g. ``PoissonInput``,
    ``SpikeGeneratorGroup`` + ``Synapses``, ``TimedArray``) that deliver the
    input to the target neurons, and append them to ``brian2_objects`` so the
    task can assemble them into its ``Network``.
    """

    @abstractmethod
    def apply(
        self,
        input_name: str,
        input_config: dict,
        neuron_group: Any,
        node_population: str,
        node_sets: dict[str, Any],
        brian2_objects: list,
        b2: Any,
    ) -> Any:
        """Create and connect Brian2 devices for this input.

        Args:
            input_name: Name of the input entry in the SONATA config.
            input_config: The SONATA input configuration dict.
            neuron_group: Brian2 ``NeuronGroup`` for the circuit's single
                point-neuron population.
            node_population: Name of the node population.
            node_sets: Parsed node_sets.json mapping set names to node IDs.
            brian2_objects: Mutable list to which created Brian2 objects
                must be appended so they get included in the Network.
            b2: The ``brian2`` module.

        Returns:
            The primary Brian2 object(s) created for this input (for logging).
        """


class Brian2ReportHandler(ABC):
    """Base handler for translating a SONATA ``reports`` entry to Brian2 objects."""

    @abstractmethod
    def apply(
        self,
        report_name: str,
        report_config: dict,
        neuron_group: Any,
        node_population: str,
        node_sets: dict[str, Any],
        brian2_objects: list,
        b2: Any,
    ) -> Any:
        """Create and connect Brian2 recording devices for this report."""


class Brian2ConnectionOverrideHandler(ABC):
    """Base handler for translating a SONATA ``connection_overrides`` entry."""

    @abstractmethod
    def apply(
        self,
        override_config: dict,
        synapses: Any,
        neuron_group: Any,
        node_sets: dict[str, Any],
        b2: Any,
    ) -> None:
        """Apply a connection override to the Brian2 network."""


def resolve_node_set_to_indices(
    node_set_name: str,
    node_population: str,
    node_sets: dict[str, Any],
    n_nodes: int,
) -> np.ndarray:
    """Resolve a SONATA node set name to an array of node indices.

    Args:
        node_set_name: Name from the node_sets.json or a population name.
        node_population: Name of the node population being resolved against.
        node_sets: Parsed node_sets.json content.
        n_nodes: Size of the node population (used when resolving "All").

    Returns:
        ``np.ndarray`` of integer node indices into the population.
    """
    if node_set_name in node_sets:
        spec = node_sets[node_set_name]
        pop_filter = spec.get("population")
        if pop_filter is not None and pop_filter not in {node_population, "All"}:
            return np.array([], dtype=int)
        if "node_id" in spec:
            return np.asarray(spec["node_id"], dtype=int)
        return np.arange(n_nodes, dtype=int)

    if node_set_name in {node_population, "All"}:
        return np.arange(n_nodes, dtype=int)

    msg = (
        f"Cannot resolve node set '{node_set_name}' to indices in population "
        f"'{node_population}'. Available node sets: {list(node_sets.keys())}."
    )
    raise Brian2FeatureNotSupportedError(msg)
