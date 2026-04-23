"""Base classes for NEST block handlers.

Each OBI-ONE block type (stimulus, recording, manipulation) has a mirrored NEST
handler class that translates the SONATA config entry to NEST API calls. If a
feature is not supported in NEST, the handler raises NestFeatureNotSupportedError.
"""

from abc import ABC, abstractmethod
from typing import Any

from obi_one.core.exception import OBIONEError


class NestFeatureNotSupportedError(OBIONEError):
    """Raised when a SONATA feature is not supported in NEST."""


class NestInputHandler(ABC):
    """Base handler for translating a SONATA ``inputs`` entry to NEST devices.

    Each subclass mirrors a single OBI-ONE stimulus block type. The handler
    receives the parsed SONATA input dict and creates the corresponding NEST
    generator device(s), connecting them to the appropriate node collection.
    """

    @abstractmethod
    def apply(
        self,
        input_name: str,
        input_config: dict,
        node_collections: dict[str, Any],
        node_sets: dict[str, Any],
        nest: Any,
    ) -> Any:
        """Create and connect NEST devices for this input.

        Args:
            input_name: Name of the input entry in the SONATA config.
            input_config: The SONATA input configuration dict.
            node_collections: Mapping of population name to NEST NodeCollection.
            node_sets: Parsed node_sets.json mapping set names to node IDs.
            nest: The ``nest`` module.

        Returns:
            The created NEST device NodeCollection(s).
        """


class NestReportHandler(ABC):
    """Base handler for translating a SONATA ``reports`` entry to NEST devices.

    Each subclass mirrors a single OBI-ONE recording block type.
    """

    @abstractmethod
    def apply(
        self,
        report_name: str,
        report_config: dict,
        node_collections: dict[str, Any],
        node_sets: dict[str, Any],
        nest: Any,
    ) -> Any:
        """Create and connect NEST recording devices for this report.

        Args:
            report_name: Name of the report entry in the SONATA config.
            report_config: The SONATA report configuration dict.
            node_collections: Mapping of population name to NEST NodeCollection.
            node_sets: Parsed node_sets.json mapping set names to node IDs.
            nest: The ``nest`` module.

        Returns:
            The created NEST device NodeCollection(s).
        """


class NestConnectionOverrideHandler(ABC):
    """Base handler for translating a SONATA ``connection_overrides`` entry."""

    @abstractmethod
    def apply(
        self,
        override_config: dict,
        node_collections: dict[str, Any],
        node_sets: dict[str, Any],
        nest: Any,
    ) -> None:
        """Apply a connection override to the NEST network.

        Args:
            override_config: The SONATA connection override configuration dict.
            node_collections: Mapping of population name to NEST NodeCollection.
            node_sets: Parsed node_sets.json mapping set names to node IDs.
            nest: The ``nest`` module.
        """


def resolve_node_set_to_nest_nodes(
    node_set_name: str,
    node_collections: dict[str, Any],
    node_sets: dict[str, Any],
) -> Any:
    """Resolve a SONATA node set name to a NEST NodeCollection subset.

    Args:
        node_set_name: Name from the node_sets.json or a population name.
        node_collections: Mapping of population name to NEST NodeCollection.
        node_sets: Parsed node_sets.json content.

    Returns:
        A NEST NodeCollection containing the resolved neurons.
    """
    if node_set_name in node_sets:
        ns_def = node_sets[node_set_name]

        if "node_id" in ns_def:
            node_ids = ns_def["node_id"]
            pop = ns_def.get("population", "All")

            if pop == "All" and len(node_collections) == 1:
                pop = next(iter(node_collections))

            if pop in node_collections:
                nc = node_collections[pop]
                return nc[sorted(node_ids)]

        if "population" in ns_def:
            pop = ns_def["population"]
            if isinstance(pop, list):
                pop = pop[0]
            if pop in node_collections:
                return node_collections[pop]

    if node_set_name in node_collections:
        return node_collections[node_set_name]

    if len(node_collections) == 1:
        return next(iter(node_collections.values()))

    msg = (
        f"Cannot resolve node set '{node_set_name}' to a NEST NodeCollection. "
        f"Available populations: {list(node_collections.keys())}, "
        f"available node sets: {list(node_sets.keys())}."
    )
    raise NestFeatureNotSupportedError(msg)
