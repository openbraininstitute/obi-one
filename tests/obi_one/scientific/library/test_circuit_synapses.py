import json
import shutil
from pathlib import Path

import h5py
import libsonata
import numpy as np
import pytest

from obi_one.scientific.library import circuit_synapses as module
from obi_one.scientific.library.circuit_synapses import (
    cached_synapses_per_cell,
    count_synapses,
    read_synapses_per_cell,
)

from tests.utils import CIRCUIT_DIR

CELLS = "S1nonbarrel_neurons"
VPM = "VPM__S1nonbarrel_neurons__chemical"
POM = "POm__S1nonbarrel_neurons__chemical"
N_CELLS = 10


@pytest.fixture
def circuit(tmp_path):
    directory = tmp_path / "circuit"
    shutil.copytree(CIRCUIT_DIR / "N_10__top_nodes_dim6", directory)
    return directory / "circuit_config.json"


@pytest.fixture
def synapses(circuit):
    return read_synapses_per_cell(circuit)


def synapses_onto(circuit, cells):
    """The edges onto the cells, counted by libsonata in every edge population of the circuit."""
    config = libsonata.CircuitConfig.from_file(str(circuit))
    return sum(
        config.edge_population(name).afferent_edges(cells).flat_size
        for name in config.edge_populations
        if config.edge_population(name).target == CELLS
    )


def merge_pom_into_vpm_file(circuit):
    """Make one edges file hold two populations, VPM and POm."""
    directory = circuit.parent
    with (
        h5py.File(directory / POM / "edges.h5", "r") as source,
        h5py.File(directory / VPM / "edges.h5", "r+") as target,
    ):
        source.copy(source[f"edges/{POM}"], target["edges"], name=POM)
    (directory / POM / "edges.h5").unlink()
    config = json.loads(circuit.read_text())
    edges = config["networks"]["edges"]
    pom = next(e for e in edges if POM in e["populations"])
    next(e for e in edges if VPM in e["populations"])["populations"][POM] = pom["populations"][POM]
    edges.remove(pom)
    circuit.write_text(json.dumps(config))


def open_recording(opened):
    def open_edges_file(path):
        opened.append(path)
        return Path(path).open("rb")

    return open_edges_file


class TestReadSynapsesPerCell:
    def test_the_synapses_of_each_cell_are_those_of_all_its_edge_populations(
        self, circuit, synapses
    ):
        assert list(synapses) == [CELLS]
        assert synapses[CELLS].tolist() == [synapses_onto(circuit, [i]) for i in range(N_CELLS)]

    def test_the_total_is_the_edges_onto_the_cells(self, synapses):
        assert synapses[CELLS].sum() == 471 + 260 + 176

    def test_each_edges_file_is_opened_once(self, circuit):
        opened = []

        read_synapses_per_cell(circuit, open_recording(opened))

        config = libsonata.CircuitConfig.from_file(str(circuit))
        assert sorted(opened) == sorted(
            config.edge_population_properties(n).elements_path for n in config.edge_populations
        )

    def test_the_populations_of_one_edges_file_are_all_counted(self, circuit, synapses):
        merge_pom_into_vpm_file(circuit)
        opened = []

        merged = read_synapses_per_cell(circuit, open_recording(opened))

        assert len(opened) == 2
        assert np.array_equal(merged[CELLS], synapses[CELLS])

    def test_a_large_index_gives_estimates_with_the_right_total(
        self, circuit, synapses, monkeypatch
    ):
        """Above the limit, each cell gets its ranges times the mean edges per range."""
        monkeypatch.setattr(module, "MAX_RANGES_READ", 0)

        estimated = read_synapses_per_cell(circuit)

        assert estimated[CELLS].sum() == pytest.approx(synapses[CELLS].sum())
        assert not np.array_equal(estimated[CELLS], synapses[CELLS])
        assert np.all((estimated[CELLS] > 0) == (synapses[CELLS] > 0))

    def test_edges_onto_a_virtual_population_are_left_out(self, circuit):
        config = json.loads(circuit.read_text())
        for nodes in config["networks"]["nodes"]:
            for population in nodes["populations"].values():
                population["type"] = "virtual"
        circuit.write_text(json.dumps(config))

        assert read_synapses_per_cell(circuit) == {}

    def test_electrical_synapses_are_left_out(self, circuit):
        circuit.write_text(circuit.read_text().replace('"chemical"', '"electrical"'))

        assert read_synapses_per_cell(circuit) == {}

    def test_an_edges_file_without_indices_cannot_be_counted(self, circuit):
        with h5py.File(circuit.parent / VPM / "edges.h5", "r+") as f:
            del f[f"edges/{VPM}/indices"]

        with pytest.raises(KeyError):
            read_synapses_per_cell(circuit)


@pytest.fixture
def empty_cache():
    module.SYNAPSES_PER_CELL_CACHE.clear()
    yield
    module.SYNAPSES_PER_CELL_CACHE.clear()


@pytest.mark.usefixtures("empty_cache")
class TestCachedSynapsesPerCell:
    def test_a_circuit_is_read_once(self):
        reads = []

        def read():
            reads.append(1)
            return {CELLS: np.ones(3)}

        first = cached_synapses_per_cell("circuit-1", read)
        second = cached_synapses_per_cell("circuit-1", read)

        assert len(reads) == 1
        assert first is second

    def test_circuits_are_kept_apart(self):
        a = cached_synapses_per_cell("a", lambda: {CELLS: np.zeros(1)})
        b = cached_synapses_per_cell("b", lambda: {CELLS: np.ones(1)})

        assert a[CELLS][0] == 0
        assert b[CELLS][0] == 1

    def test_a_failed_read_is_not_kept(self):
        def fail():
            msg = "refused"
            raise OSError(msg)

        with pytest.raises(OSError, match="refused"):
            cached_synapses_per_cell("circuit-1", fail)

        assert cached_synapses_per_cell("circuit-1", lambda: {CELLS: np.ones(1)})[CELLS][0] == 1

    def test_the_oldest_circuit_is_dropped_beyond_the_limit(self, monkeypatch):
        monkeypatch.setattr(module, "MAX_CACHED_CIRCUITS", 2)
        for key in ("a", "b", "c"):
            cached_synapses_per_cell(key, lambda: {CELLS: np.ones(1)})

        assert list(module.SYNAPSES_PER_CELL_CACHE) == ["b", "c"]


class TestCountSynapses:
    def test_all_the_cells(self, synapses):
        assert count_synapses(synapses, {CELLS: list(range(N_CELLS))}) == 907

    @pytest.mark.parametrize("seed", range(10))
    def test_any_subset_of_the_cells_has_the_edges_onto_it(self, circuit, synapses, seed):
        rng = np.random.default_rng(seed)
        cells = sorted(rng.choice(N_CELLS, int(rng.integers(1, N_CELLS)), replace=False).tolist())

        assert count_synapses(synapses, {CELLS: cells}) == synapses_onto(circuit, cells)

    def test_no_cell_has_no_synapse(self, synapses):
        assert count_synapses(synapses, {CELLS: []}) == 0
        assert count_synapses(synapses, {}) == 0

    def test_a_population_without_synapses_counts_nothing(self, synapses):
        assert count_synapses(synapses, {"VPM": [0, 1], CELLS: [0]}) == count_synapses(
            synapses, {CELLS: [0]}
        )

    def test_the_estimate_is_rounded_to_an_integer(self):
        assert count_synapses({"cells": np.array([1.4, 1.4])}, {"cells": [0, 1]}) == 3
