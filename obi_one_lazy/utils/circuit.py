"""Circuit-related utility functions used by simulation staging/execution."""

import libsonata
import numpy as np


def merged_simulation_node_sets(
    simulation_config: libsonata.SimulationConfig,
) -> tuple[libsonata.NodeSets, libsonata.CircuitConfig]:
    """Return the merged (circuit + simulation) node sets and the circuit config.

    A SONATA simulation config references a circuit (``network``) and may declare its
    own ``node_sets_file``. The simulation node sets are overlaid on top of the
    circuit's (the simulation definitions take precedence), matching SONATA's
    resolution semantics.
    """
    circuit_config = libsonata.CircuitConfig.from_file(simulation_config.network)

    circuit_node_sets_path = circuit_config.node_sets_path
    node_sets = (
        libsonata.NodeSets.from_file(circuit_node_sets_path)
        if circuit_node_sets_path
        else libsonata.NodeSets.from_string("{}")
    )

    if simulation_config.node_sets_file:
        node_sets.update(libsonata.NodeSets.from_file(simulation_config.node_sets_file))

    return node_sets, circuit_config


def resolve_simulation_node_set_ids(
    simulation_config: libsonata.SimulationConfig, node_set_name: str
) -> dict[str, np.ndarray]:
    """Resolve a simulation's node set to concrete node IDs per population.

    The node set named in a SONATA simulation config may be defined either in the
    circuit's node sets or in the simulation's own ``node_sets_file`` (the latter
    takes precedence). Both are merged and resolved via libsonata, which handles every
    node set definition shape -- symbolic (e.g. ``{"synapse_class": "EXC"}``,
    ``{"mtype": "L1_DAC"}``), compound references (e.g. ``["All"]``) and explicit
    ``{"population": ..., "node_id": [...]}`` lists -- rather than assuming the raw
    node sets file entry already contains a ``"node_id"`` list.

    Args:
        simulation_config: The SONATA simulation config (``libsonata.SimulationConfig``).
        node_set_name: Name of the node set referenced by the simulation config.

    Returns:
        Mapping of population name -> array of node IDs selected by the node set.
        Populations in which the node set resolves to no cells are omitted.

    Raises:
        KeyError: If ``node_set_name`` is defined in neither the circuit nor the
            simulation node sets.
    """
    node_sets, circuit_config = merged_simulation_node_sets(simulation_config)

    if node_set_name not in node_sets.names:
        msg = f"Node set '{node_set_name}' not found in node sets file"
        raise KeyError(msg)

    ids_per_population: dict[str, np.ndarray] = {}
    for pop_name in circuit_config.node_populations:
        node_population = circuit_config.node_population(pop_name)
        try:
            selection = node_sets.materialize(node_set_name, node_population)
        except libsonata.SonataError:
            # Node set does not apply to this population (e.g. missing attribute).
            continue
        if selection.flat_size > 0:
            ids_per_population[pop_name] = selection.flatten()

    return ids_per_population


def count_cells_in_simulation_node_set(
    simulation_config: libsonata.SimulationConfig, node_set_name: str
) -> int:
    """Count the cells selected by a simulation's node set across all populations.

    Resolves the node set via :func:`resolve_simulation_node_set_ids` (merged
    circuit + simulation node sets, any definition shape). Propagates ``KeyError``
    if the node set is defined in neither.
    """
    return sum(
        len(ids)
        for ids in resolve_simulation_node_set_ids(simulation_config, node_set_name).values()
    )
