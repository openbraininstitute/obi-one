import json
import logging
import shutil
from pathlib import Path

import h5py
import libsonata
import pytest

from obi_one.scientific.library.morphology_pack import build
from obi_one.scientific.library.morphology_pack.build import (
    NoPackError,
    build_morphology_pack,
    segment_cap,
)
from obi_one.scientific.library.morphology_pack.geometry import LEVELS
from obi_one.scientific.library.morphology_pack.reader import read_pack

from tests.utils import CIRCUIT_DIR

CONTAINER_CIRCUIT = CIRCUIT_DIR / "N_10__top_nodes_dim6"
FOLDER_CIRCUIT = CIRCUIT_DIR / "nbS1-O1-E2Sst-maxNsyn-HEX0-L5"
POPULATION = "S1nonbarrel_neurons"
CONFIG = Path("circuit_config.json")
NODES = Path(POPULATION) / "nodes.h5"
LOTS = 10**12


def pack_of(circuit: Path, max_segments: int = LOTS, workers: int = 1):
    return read_pack(build_morphology_pack(circuit / CONFIG, max_segments, workers))


def kinds(pack) -> list[tuple[float, float]]:
    return [(level.entry.tolerance_um, level.entry.prune_um) for level in pack.levels]


@pytest.fixture
def copied(tmp_path) -> Path:
    """A copy of the container circuit, to change."""
    return shutil.copytree(CONTAINER_CIRCUIT, tmp_path / "circuit")


def name_absent(circuit: Path, cells) -> None:
    with h5py.File(circuit / NODES, "r+") as file:
        file[f"nodes/{POPULATION}/0/morphology"][cells] = "absent"


class TestPack:
    def test_every_level_finest_first(self):
        pack = pack_of(CONTAINER_CIRCUIT)
        assert kinds(pack) == [(0.125, 0.0), (0.25, 0.0), (1.0, 5.0)]
        segments = [len(level.segments) for level in pack.levels]
        assert segments == sorted(segments, reverse=True)
        assert segments[0] > 10_000
        assert all(set(level.cells) == set(range(10)) for level in pack.levels)

    def test_a_circuit_with_a_folder_of_morphologies(self):
        pack = pack_of(FOLDER_CIRCUIT)
        nodes = libsonata.NodeStorage(str(FOLDER_CIRCUIT / NODES)).open_population(POPULATION)
        assert len(pack.levels) == len(LEVELS)
        assert set(pack.levels[0].cells) == set(range(nodes.size))

    def test_processes_build_the_same_pack(self):
        alone = build_morphology_pack(CONTAINER_CIRCUIT / CONFIG, LOTS, 1)
        spread = build_morphology_pack(CONTAINER_CIRCUIT / CONFIG, LOTS, 2)
        same = alone == spread
        assert same

    def test_each_stage_is_logged(self, caplog):
        with caplog.at_level(logging.INFO, logger=build.L.name):
            pack_of(CONTAINER_CIRCUIT)
        stages = [
            record.getMessage()
            for record in caplog.records
            if record.getMessage().startswith("Morphology pack:")
        ]
        ends = ["read", "simplified", "placed", "packed"]
        assert len(stages) == len(ends)
        assert all(f"{end} in " in stage for end, stage in zip(ends, stages, strict=True))


class TestUnreadable:
    def test_a_name_the_container_does_not_hold_leaves_a_soma(self, copied):
        name_absent(copied, 0)
        pack = pack_of(copied)
        assert set(pack.levels[0].cells) == set(range(1, 10))
        assert pack.somas[0, 3] == 0
        assert pack.somas[1, 3] > 0


class TestNoPack:
    def test_without_a_biophysical_population(self, copied):
        config = json.loads((copied / CONFIG).read_text())
        for nodes in config["networks"]["nodes"]:
            for population in nodes["populations"].values():
                population["type"] = "virtual"
        (copied / CONFIG).write_text(json.dumps(config))
        with pytest.raises(NoPackError, match="no biophysical population"):
            pack_of(copied)

    def test_when_no_morphology_can_be_read(self, copied):
        name_absent(copied, slice(None))
        with pytest.raises(NoPackError, match="morphologies could be read"):
            pack_of(copied)

    def test_when_the_levels_together_are_too_many(self):
        together = sum(len(level.segments) for level in pack_of(CONTAINER_CIRCUIT).levels)
        assert pack_of(CONTAINER_CIRCUIT, together).levels
        with pytest.raises(NoPackError, match=f"over the {together - 1}"):
            pack_of(CONTAINER_CIRCUIT, together - 1)


class TestSegmentCap:
    def test_the_fixed_cap_where_memory_holds_more(self, monkeypatch, caplog):
        monkeypatch.setattr(
            build,
            "memory_left",
            lambda _: build.BASE_BYTES + 2 * build.MAX_SEGMENTS * build.BYTES_A_SEGMENT,
        )
        with caplog.at_level(logging.INFO, logger=build.L.name):
            assert segment_cap(workers=2) == build.MAX_SEGMENTS
        assert "by" not in caplog.records[-1].getMessage()

    def test_fewer_where_memory_holds_fewer(self, monkeypatch, caplog):
        monkeypatch.setattr(
            build, "memory_left", lambda _: build.BASE_BYTES + 1000 * build.BYTES_A_SEGMENT + 1
        )
        with caplog.at_level(logging.INFO, logger=build.L.name):
            assert segment_cap(workers=2) == 1000
        assert "memory left" in caplog.records[-1].getMessage()

    def test_none_where_memory_holds_no_more_than_the_base(self, monkeypatch):
        monkeypatch.setattr(build, "memory_left", lambda _: build.BASE_BYTES - 1)
        assert segment_cap(workers=2) == 0

    @pytest.mark.parametrize("workers", [1, 2])
    def test_two_processes_or_fewer_hold_the_base(self, monkeypatch, workers):
        monkeypatch.setattr(
            build, "memory_left", lambda _: build.BASE_BYTES + 1000 * build.BYTES_A_SEGMENT
        )
        assert segment_cap(workers=workers) == 1000

    def test_each_process_past_two_holds_more(self, monkeypatch):
        held = build.BASE_BYTES + 2 * build.BYTES_A_WORKER
        monkeypatch.setattr(build, "memory_left", lambda _: held + 1000 * build.BYTES_A_SEGMENT)
        assert segment_cap(workers=4) == 1000

    def test_one_process_a_cpu_where_none_are_given(self, monkeypatch):
        monkeypatch.setattr(build, "available_cpus", lambda: 3)
        held = build.BASE_BYTES + build.BYTES_A_WORKER
        monkeypatch.setattr(build, "memory_left", lambda _: held + 1000 * build.BYTES_A_SEGMENT)
        assert segment_cap() == 1000
