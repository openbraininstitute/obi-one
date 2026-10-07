"""Shared test doubles for simulation/neuron node set resolution tests.

These model the subset of the ``libsonata`` API that the node set resolution
helpers rely on:

- ``SimulationConfig`` -- exposes ``network`` (circuit config path), ``node_set``
  and ``node_sets_file``. In the helpers only ``node_set`` is read directly; the
  merged node sets and circuit come from the resolver, so the fake wires those in.
- ``CircuitConfig`` -- ``node_populations`` and ``node_population(name)``.
- ``NodeSets`` -- ``names`` and ``materialize(name, node_population)`` returning a
  ``Selection``; raises ``SonataError`` when the node set does not apply to a
  population.
- ``Selection`` -- ``flat_size`` and ``flatten()``.

The fake ``SimulationConfig`` is accepted directly by
``resolve_simulation_node_set_ids`` / ``count_cells_in_simulation_node_set``
because those read ``simulation_config.node_set`` and otherwise go through the
patched ``_merged_simulation_node_sets`` (see the test helpers that patch it).
"""

from __future__ import annotations

from dataclasses import dataclass

from libsonata import SonataError

_MISSING = object()


@dataclass
class _FakeSelection:
    _ids: list[int]

    @property
    def flat_size(self) -> int:
        return len(self._ids)

    def flatten(self) -> list[int]:
        return list(self._ids)


@dataclass
class _FakeNodePopulation:
    name: str


class FakeCircuitConfig:
    """Models ``libsonata.CircuitConfig`` for node population enumeration."""

    def __init__(self, population_names: list[str]):
        self._pops = {name: _FakeNodePopulation(name) for name in population_names}

    @property
    def node_populations(self) -> set[str]:
        return set(self._pops)

    def node_population(self, name: str) -> _FakeNodePopulation:
        return self._pops[name]


class FakeNodeSets:
    """Models ``libsonata.NodeSets``: name -> {population -> [node_id, ...]}.

    ``raising_populations`` lets a test force ``materialize`` to raise
    ``SonataError`` for a population regardless of membership, to exercise the
    defensive skip in the resolver.
    """

    def __init__(
        self,
        per_node_set: dict[str, dict[str, list[int]]],
        raising_populations: frozenset[str] = frozenset(),
    ):
        self._per_node_set = per_node_set
        self._raising_populations = raising_populations

    @property
    def names(self) -> set[str]:
        return set(self._per_node_set)

    def materialize(self, name: str, node_population: _FakeNodePopulation) -> _FakeSelection:
        pop_name = node_population.name
        if pop_name in self._raising_populations:
            msg = f"Node set '{name}' failed to resolve in population '{pop_name}'"
            raise SonataError(msg)
        ids = self._per_node_set.get(name, {}).get(pop_name, _MISSING)
        if ids is _MISSING:
            # Node set does not apply to this population (e.g. missing attribute);
            # libsonata raises SonataError in this case.
            msg = f"Node set '{name}' does not resolve in population '{pop_name}'"
            raise SonataError(msg)
        return _FakeSelection(list(ids))


@dataclass
class FakeSimulationConfig:
    """Models the attributes of ``libsonata.SimulationConfig`` read by the helpers."""

    node_set: str | None = None
    network: str = "circuit_config.json"
    node_sets_file: str = "node_sets.json"


def make_fake_resolution(
    per_node_set: dict[str, dict[str, list[int]]],
    *,
    node_set: str | None = None,
    extra_populations: list[str] | None = None,
    raising_populations: list[str] | None = None,
) -> tuple[FakeSimulationConfig, FakeNodeSets, FakeCircuitConfig]:
    """Build a fake (SimulationConfig, NodeSets, CircuitConfig) triple.

    The populations are the union of those referenced by the node sets plus any
    ``extra_populations`` / ``raising_populations`` (to exercise populations in
    which a node set does not resolve or raises).
    """
    populations = set(extra_populations or [])
    populations.update(raising_populations or [])
    for by_pop in per_node_set.values():
        populations.update(by_pop)
    circuit_config = FakeCircuitConfig(sorted(populations))
    node_sets = FakeNodeSets(per_node_set, frozenset(raising_populations or []))
    simulation_config = FakeSimulationConfig(node_set=node_set)
    return simulation_config, node_sets, circuit_config
