"""Shared test doubles for simulation/neuron node set resolution tests.

These model the subset of the ``bluepysnap`` API that the node set resolution
helpers rely on:

- ``Simulation.node_sets`` -- the *merged* circuit + simulation node sets, keyed
  by name; ``name in node_sets`` and ``node_sets[name]`` must work.
- ``NodeSet.get_ids(population, raise_missing_property=...)`` -- resolve to IDs
  for a single population, raising ``BluepySnapError`` when the node set does not
  apply to that population.
- ``Simulation.circuit.nodes.population_names`` and
  ``Simulation.circuit.nodes[pop].to_libsonata`` -- the per-population stores
  passed to ``get_ids``.
"""

from __future__ import annotations

from dataclasses import dataclass

from bluepysnap import BluepySnapError

_MISSING = object()


class _FakeNodeSet:
    """A single node set resolving to explicit IDs per population."""

    def __init__(self, name: str, ids_by_population: dict[str, list[int]]):
        self._name = name
        self._ids_by_population = ids_by_population

    def get_ids(self, population, *, raise_missing_property: bool = True):
        # ``population`` is the per-population store; our fake store carries its name.
        pop_name = population.name
        ids = self._ids_by_population.get(pop_name, _MISSING)
        if ids is _MISSING:
            # Node set does not apply to this population. The real bluepysnap raises
            # BluepySnapError here when raise_missing_property is True; mirror that.
            if raise_missing_property:
                msg = f"Node set '{self._name}' does not resolve in population '{pop_name}'"
                raise BluepySnapError(msg)
            return []
        return list(ids)


class _FakeNodeSets:
    """Merged node sets view: name -> {population -> [node_id, ...]}."""

    def __init__(self, per_node_set: dict[str, dict[str, list[int]]]):
        self._per_node_set = per_node_set

    def __contains__(self, name: str) -> bool:
        return name in self._per_node_set

    def __iter__(self):
        return iter(self._per_node_set)

    def __getitem__(self, name: str) -> _FakeNodeSet:
        return _FakeNodeSet(name, self._per_node_set[name])


@dataclass
class _FakePopulationStore:
    name: str


class _FakeNodePopulation:
    def __init__(self, name: str):
        self.to_libsonata = _FakePopulationStore(name)


class _FakeNodes:
    def __init__(self, population_names: list[str]):
        self._pops = {name: _FakeNodePopulation(name) for name in population_names}

    @property
    def population_names(self):
        return list(self._pops)

    def __getitem__(self, name: str):
        return self._pops[name]


class _FakeCircuit:
    def __init__(self, population_names: list[str]):
        self.nodes = _FakeNodes(population_names)


class FakeSimulation:
    """Minimal stand-in for a ``snap.Simulation`` for node set resolution tests.

    Args:
        per_node_set: node set name -> {population name -> [node_id, ...]}. The set
            of populations is derived from the union of populations referenced by the
            node sets, plus any ``extra_populations`` (to exercise populations in
            which a node set does not resolve).
    """

    def __init__(
        self,
        per_node_set: dict[str, dict[str, list[int]]],
        *,
        extra_populations: list[str] | None = None,
    ):
        populations = set(extra_populations or [])
        for by_pop in per_node_set.values():
            populations.update(by_pop)
        self.circuit = _FakeCircuit(sorted(populations))
        self.node_sets = _FakeNodeSets(per_node_set)
