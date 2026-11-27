import json
import operator
import shutil
from dataclasses import FrozenInstanceError
from pathlib import Path

import h5py
import libsonata
import numpy as np
import pytest

from obi_one.scientific.library import circuit_synapses as module
from obi_one.scientific.library.circuit_synapses import (
    CellSynapses,
    cached_synapses_per_cell,
    count_synapses,
    count_synapses_by_source,
    read_synapses_per_cell,
    synapses_by_source,
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
        assert estimated(synapses[CELLS]) == 0
        assert exact(synapses[CELLS]).tolist() == [
            synapses_onto(circuit, [i]) for i in range(N_CELLS)
        ]

    def test_the_total_is_the_edges_onto_the_cells(self, synapses):
        assert exact(synapses[CELLS]).sum() == 471 + 260 + 176

    def test_the_synapses_are_kept_by_source_population(self, circuit, synapses):
        assert sorted(synapses[CELLS].exact) == sorted(["S1nonbarrel_neurons", "VPM", "POm"])
        by_source = count_synapses_by_source(synapses, {CELLS: list(range(N_CELLS))})
        assert by_source["VPM"] == vpm_edges(circuit)
        assert sum(by_source.values()) == 907

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
        assert np.array_equal(exact(merged[CELLS]), exact(synapses[CELLS]))

    def test_a_large_index_is_not_read_and_its_population_is_counted_in_total(
        self, circuit, monkeypatch
    ):
        monkeypatch.setattr(module, "MAX_INDEX_BYTES", 0)

        counted_in_total = read_synapses_per_cell(circuit)

        assert estimated(counted_in_total[CELLS]) == 907
        assert exact(counted_in_total[CELLS]) is None

    def test_edges_onto_a_virtual_population_are_left_out(self, circuit):
        config = json.loads(circuit.read_text())
        for nodes in config["networks"]["nodes"]:
            for population in nodes["populations"].values():
                population["type"] = "virtual"
        circuit.write_text(json.dumps(config))

        assert read_synapses_per_cell(circuit) == {}

    def test_electrical_synapses_are_left_out(self, circuit):
        circuit.write_text(circuit.read_text().replace('"chemical"', '"electrical"'))

        assert count_synapses(read_synapses_per_cell(circuit), {CELLS: list(range(N_CELLS))}) == 0

    def test_an_edges_file_without_indices_is_counted_in_total(self, circuit):
        with h5py.File(circuit.parent / VPM / "edges.h5", "r+") as f:
            del f[f"edges/{VPM}/indices"]

        counted = read_synapses_per_cell(circuit)

        assert estimated(counted[CELLS]) == vpm_edges(circuit)
        assert exact(counted[CELLS]).sum() + estimated(counted[CELLS]) == 907

    def test_an_index_without_its_last_cells_is_counted_in_total(self, circuit):
        """A writer of synaptome circuits leaves the last target out of the index."""
        rewrite_node_ranges(circuit, operator.itemgetter(slice(-1)))

        assert read_synapses_per_cell(circuit)[CELLS].estimated == {"VPM": vpm_edges(circuit)}

    def test_rows_of_an_index_beyond_the_population_are_ignored(self, circuit, synapses):
        """Another writer pads the index of one cell with empty rows, up to the sources."""
        rewrite_node_ranges(
            circuit, lambda ranges: np.vstack([ranges, np.repeat(ranges[-1:, 1:], 2, axis=1)])
        )

        padded = read_synapses_per_cell(circuit)

        assert estimated(padded[CELLS]) == 0
        assert np.array_equal(exact(padded[CELLS]), exact(synapses[CELLS]))

    def test_an_index_pointing_past_its_ranges_is_counted_in_total(self, circuit):
        rewrite_node_ranges(circuit, lambda ranges: ranges + 1000)

        assert read_synapses_per_cell(circuit)[CELLS].estimated == {"VPM": vpm_edges(circuit)}

    def test_a_population_missing_from_its_file_is_left_out(self, circuit, caplog):
        missing = vpm_edges(circuit)
        with h5py.File(circuit.parent / VPM / "edges.h5", "r+") as f:
            f.move(f"edges/{VPM}", "edges/renamed")

        counted = read_synapses_per_cell(circuit)

        assert exact(counted[CELLS]).sum() == 907 - missing
        assert f"{VPM} of" in caplog.text

    def test_an_edges_file_that_cannot_be_opened_fails_the_count(self, circuit):
        def refuse(_path):
            msg = "Expected 206 for a range request, got 200"
            raise OSError(msg)

        with pytest.raises(OSError, match="206"):
            read_synapses_per_cell(circuit, refuse)


def total(cells, ids):
    return sum(synapses_by_source(cells, ids).values())


def exact(cells):
    """The exact synapses of each cell, summed over the source populations, or None."""
    return sum(cells.exact.values()) if cells.exact else None


def estimated(cells):
    return sum(cells.estimated.values())


def vpm_edges(circuit):
    with h5py.File(circuit.parent / VPM / "edges.h5", "r") as f:
        return f[f"edges/{VPM}/source_node_id"].shape[0]


def rewrite_node_ranges(circuit, change):
    with h5py.File(circuit.parent / VPM / "edges.h5", "r+") as f:
        index = f[f"edges/{VPM}/indices/target_to_source"]
        ranges = change(index["node_id_to_ranges"][:])
        del index["node_id_to_ranges"]
        index["node_id_to_ranges"] = ranges


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
        cells = CellSynapses(10, estimated={"virtual": 7})

        assert count_synapses({"cells": cells}, {"cells": [0]}) == 2

    def test_ids_outside_the_population_or_repeated_are_ignored(self, synapses):
        assert count_synapses(synapses, {CELLS: [0, 0, N_CELLS, -1]}) == count_synapses(
            synapses, {CELLS: [0]}
        )


class TestEstimatedSynapses:
    """A population counted in total gives a node set its share of the cells, times a margin."""

    CELLS = CellSynapses(
        4, {"cells": np.array([1, 2, 3, 4], dtype=np.uint32)}, estimated={"virtual": 1000}
    )

    def test_all_the_cells_get_the_total(self):
        assert total(self.CELLS, [0, 1, 2, 3]) == 1010

    def test_a_subset_gets_its_share_times_the_margin(self):
        assert total(self.CELLS, [0]) == 1 + 1000 * module.SUBSET_FACTOR / 4

    def test_the_share_is_capped_at_the_total(self):
        assert total(self.CELLS, [0, 1]) == 3 + 1000

    def test_each_source_keeps_its_own_count(self):
        assert synapses_by_source(self.CELLS, [0]) == {
            "cells": 1,
            "virtual": 1000 * module.SUBSET_FACTOR / 4,
        }


class TestCellSynapsesAreReadOnly:
    """They are cached and shared by every simulation of a circuit."""

    def test_the_fields_cannot_be_replaced(self, synapses):
        with pytest.raises(FrozenInstanceError):
            synapses[CELLS].size = 0

    def test_the_counts_by_source_cannot_be_changed(self, synapses):
        with pytest.raises(TypeError):
            synapses[CELLS].exact["VPM"] = np.zeros(N_CELLS)
        with pytest.raises(TypeError):
            synapses[CELLS].estimated["VPM"] = 1

    def test_the_counts_per_cell_cannot_be_changed(self, synapses):
        with pytest.raises(ValueError, match="read-only"):
            synapses[CELLS].exact["VPM"][0] = 0
