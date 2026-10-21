import os
import shutil
import threading
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import h5py
import libsonata
import pytest
from entitysdk.exception import EntitySDKError
from fastapi import HTTPException

from app.config import settings
from app.services import circuit_morphology_pack as service
from app.services.circuit_morphology_pack import (
    BUILDING,
    DEFAULT_MAX_SEGMENTS,
    Refusal,
    build_circuit_morphology_pack,
)
from obi_one.scientific.library.morphology_pack.geometry import LEVELS
from obi_one.scientific.library.morphology_pack.reader import read_pack

from tests.utils import CIRCUIT_DIR

CONTAINER_CIRCUIT = CIRCUIT_DIR / "N_10__top_nodes_dim6"
FOLDER_CIRCUIT = CIRCUIT_DIR / "nbS1-O1-E2Sst-maxNsyn-HEX0-L5"
POPULATION = "S1nonbarrel_neurons"
NODES = Path(POPULATION) / "nodes.h5"
CONTAINER = Path("morphologies/merged-morphologies.h5")


class LocalCircuit:
    """Stands in for the database client: a circuit's files come from a directory on disk."""

    def __init__(
        self,
        source: Path,
        number_neurons: int = 10,
        replaced: dict | None = None,
        asset_id: UUID | None = None,
    ):
        self.source = source
        self.number_neurons = number_neurons
        self.replaced = replaced or {}
        self.asset_id = asset_id or uuid4()
        self.listed = 0
        self.fetched = []

    def get_entity(self, *, entity_id, entity_type):  # ruff: ignore[unused-method-argument]
        return SimpleNamespace(id=entity_id, number_neurons=self.number_neurons)

    def select_assets(self, circuit, selection):  # ruff: ignore[unused-method-argument]
        return SimpleNamespace(one=lambda: SimpleNamespace(id=self.asset_id))

    def list_directory(self, **_):
        self.listed += 1
        files = {
            path.relative_to(self.source): SimpleNamespace(size=path.stat().st_size)
            for path in self.source.rglob("*")
            if path.is_file()
        }
        return SimpleNamespace(files=files)

    def download_file(self, *, output_path, asset_path, **_):
        shutil.copy(self.source / asset_path, output_path)

    def fetch_file(self, *, output_path, asset_path, **_):
        self.fetched.append(asset_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.symlink_to(self.replaced.get(asset_path, self.source / asset_path))


def build(client, directory, max_segments=DEFAULT_MAX_SEGMENTS, *, all_levels=False):
    return read_pack(
        build_circuit_morphology_pack(
            client, uuid4(), directory, max_segments, all_levels=all_levels
        )
    )


def kinds(pack) -> list[tuple[float, float]]:
    return [(level.entry.tolerance_um, level.entry.prune_um) for level in pack.levels]


def refusal(error) -> tuple[int, str]:
    return error.value.status_code, error.value.detail["reason"]


def nodes_naming_absent(folder: Path, cells) -> Path:
    """A copy of the container circuit's nodes whose `cells` name a morphology it lacks."""
    nodes = folder / "nodes.h5"
    shutil.copy(CONTAINER_CIRCUIT / NODES, nodes)
    with h5py.File(nodes, "r+") as file:
        file[f"nodes/{POPULATION}/0/morphology"][cells] = "absent"
    return nodes


@pytest.fixture
def directory(tmp_path):
    return tmp_path.resolve()


@pytest.fixture
def one_process(monkeypatch):
    monkeypatch.setattr(settings, "CIRCUIT_MORPHOLOGY_PACK_WORKERS", 1)


pytestmark = pytest.mark.usefixtures("one_process")


class TestPack:
    def test_a_circuit_with_a_container_of_morphologies(self, directory):
        client = LocalCircuit(CONTAINER_CIRCUIT)
        pack = build(client, directory)
        level = pack.levels[0]
        assert (level.entry.tolerance_um, level.entry.prune_um) == (0.125, 0.0)
        assert set(level.cells) == set(range(10))
        assert len(level.segments) == level.entry.segments > 10_000
        assert sorted(client.fetched) == sorted([NODES, CONTAINER])

    def test_a_circuit_with_a_folder_of_morphologies(self, directory):
        client = LocalCircuit(FOLDER_CIRCUIT)
        pack = build(client, directory)
        nodes = libsonata.NodeStorage(str(FOLDER_CIRCUIT / NODES)).open_population(POPULATION)
        names = set(nodes.get_attribute("morphology", nodes.select_all()))
        assert sorted(client.fetched) == sorted(
            [NODES, *(Path("morphologies/swc") / f"{name}.swc" for name in names)]
        )
        assert set(pack.levels[0].cells) == set(range(nodes.size))

    def test_what_was_staged_is_let_go_of_once_read(self, directory):
        build(LocalCircuit(CONTAINER_CIRCUIT), directory)
        assert not directory.exists()


class TestUnreadable:
    def test_a_file_that_is_not_a_morphology_leaves_a_soma(self, directory, tmp_path_factory):
        nodes = libsonata.NodeStorage(str(FOLDER_CIRCUIT / NODES)).open_population(POPULATION)
        name = nodes.get_attribute("morphology", libsonata.Selection([0]))[0]
        bad = tmp_path_factory.mktemp("bad") / "bad.swc"
        bad.write_text("not a morphology")
        client = LocalCircuit(
            FOLDER_CIRCUIT, replaced={Path("morphologies/swc") / f"{name}.swc": bad}
        )
        pack = build(client, directory)
        assert 0 not in set(pack.levels[0].cells)
        assert pack.somas[0, 3] == 0
        assert pack.somas[1, 3] > 0

    def test_a_name_the_container_does_not_hold_leaves_a_soma(self, directory, tmp_path_factory):
        nodes = nodes_naming_absent(tmp_path_factory.mktemp("nodes"), 0)
        pack = build(LocalCircuit(CONTAINER_CIRCUIT, replaced={NODES: nodes}), directory)
        assert set(pack.levels[0].cells) == set(range(1, 10))
        assert pack.somas[0, 3] == 0

    def test_refused_when_none_can_be_read(self, directory, tmp_path_factory):
        nodes = nodes_naming_absent(tmp_path_factory.mktemp("nodes"), slice(None))
        with pytest.raises(HTTPException) as error:
            build(LocalCircuit(CONTAINER_CIRCUIT, replaced={NODES: nodes}), directory)
        assert refusal(error) == (HTTPStatus.UNPROCESSABLE_ENTITY, Refusal.NO_MORPHOLOGIES)


class TestLevel:
    def test_the_finest_level_within_the_segments_asked_for(self, directory, tmp_path_factory):
        finest = build(LocalCircuit(CONTAINER_CIRCUIT), directory).levels[0]
        other = tmp_path_factory.mktemp("middle").resolve()
        middle = build(LocalCircuit(CONTAINER_CIRCUIT), other, len(finest.segments) - 1).levels[0]
        other = tmp_path_factory.mktemp("far").resolve()
        far = build(LocalCircuit(CONTAINER_CIRCUIT), other, len(middle.segments) - 1).levels[0]
        assert (middle.entry.tolerance_um, middle.entry.prune_um) == (0.25, 0.0)
        assert (far.entry.tolerance_um, far.entry.prune_um) == (1.0, 5.0)
        assert len(far.segments) < len(middle.segments) < len(finest.segments)

    def test_refused_when_no_level_fits(self, directory):
        with pytest.raises(HTTPException) as error:
            build(LocalCircuit(CONTAINER_CIRCUIT), directory, 10)
        assert refusal(error) == (HTTPStatus.UNPROCESSABLE_ENTITY, Refusal.TOO_MANY_SEGMENTS)

    def test_the_service_holds_no_more_than_its_own_limit(
        self, directory, tmp_path_factory, monkeypatch
    ):
        finest = build(LocalCircuit(CONTAINER_CIRCUIT), directory).levels[0]
        monkeypatch.setattr(
            settings, "CIRCUIT_MORPHOLOGY_PACK_MAX_SEGMENTS", len(finest.segments) - 1
        )
        other = tmp_path_factory.mktemp("capped").resolve()
        assert kinds(build(LocalCircuit(CONTAINER_CIRCUIT), other)) == [(0.25, 0.0)]


class TestAllLevels:
    def test_every_level_finest_first(self, directory, tmp_path_factory):
        pack = build(LocalCircuit(CONTAINER_CIRCUIT), directory, all_levels=True)
        assert kinds(pack) == [(0.125, 0.0), (0.25, 0.0), (1.0, 5.0)]
        segments = [len(level.segments) for level in pack.levels]
        assert segments == sorted(segments, reverse=True)
        assert all(set(level.cells) == set(range(10)) for level in pack.levels)
        other = tmp_path_factory.mktemp("finest").resolve()
        finest = build(LocalCircuit(CONTAINER_CIRCUIT), other).levels[0]
        assert segments[0] == len(finest.segments)

    def test_processes_build_the_same_pack(self, directory, tmp_path_factory, monkeypatch):
        alone = build_circuit_morphology_pack(
            LocalCircuit(CONTAINER_CIRCUIT),
            uuid4(),
            directory,
            DEFAULT_MAX_SEGMENTS,
            all_levels=True,
        )
        monkeypatch.setattr(settings, "CIRCUIT_MORPHOLOGY_PACK_WORKERS", 2)
        other = tmp_path_factory.mktemp("processes").resolve()
        spread = build_circuit_morphology_pack(
            LocalCircuit(CONTAINER_CIRCUIT), uuid4(), other, DEFAULT_MAX_SEGMENTS, all_levels=True
        )
        same = alone == spread
        assert same

    def test_the_segments_asked_for_are_not_used(self, directory):
        pack = build(LocalCircuit(CONTAINER_CIRCUIT), directory, 10, all_levels=True)
        assert len(pack.levels) == len(LEVELS)

    def test_refused_when_the_levels_together_are_too_many(
        self, directory, tmp_path_factory, monkeypatch
    ):
        pack = build(LocalCircuit(CONTAINER_CIRCUIT), directory, all_levels=True)
        together = sum(len(level.segments) for level in pack.levels)
        monkeypatch.setattr(settings, "CIRCUIT_MORPHOLOGY_PACK_MAX_SEGMENTS", together - 1)
        other = tmp_path_factory.mktemp("too-many").resolve()
        with pytest.raises(HTTPException) as error:
            build(LocalCircuit(CONTAINER_CIRCUIT), other, all_levels=True)
        assert refusal(error) == (HTTPStatus.UNPROCESSABLE_ENTITY, Refusal.TOO_MANY_SEGMENTS)
        assert not BUILDING.locked()


class TestLimits:
    def test_too_many_neurons_is_refused_before_anything_is_read(self, directory):
        client = LocalCircuit(
            CONTAINER_CIRCUIT, number_neurons=settings.CIRCUIT_MORPHOLOGY_PACK_MAX_NEURONS + 1
        )
        with pytest.raises(HTTPException) as error:
            build(client, directory)
        assert refusal(error) == (HTTPStatus.UNPROCESSABLE_ENTITY, Refusal.TOO_MANY_NEURONS)
        assert client.listed == 0
        assert client.fetched == []
        assert not any(directory.iterdir())

    def test_files_too_large_are_not_fetched(self, directory, monkeypatch):
        nodes_size = (CONTAINER_CIRCUIT / NODES).stat().st_size
        monkeypatch.setattr(settings, "CIRCUIT_MORPHOLOGY_PACK_MAX_STAGED_BYTES", nodes_size + 1)
        client = LocalCircuit(CONTAINER_CIRCUIT)
        with pytest.raises(HTTPException) as error:
            build(client, directory)
        assert refusal(error) == (HTTPStatus.UNPROCESSABLE_ENTITY, Refusal.FILES_TOO_LARGE)
        assert client.fetched == [NODES]

    def test_too_many_points_is_refused(self, directory, monkeypatch):
        monkeypatch.setattr(settings, "CIRCUIT_MORPHOLOGY_PACK_MAX_POINTS", 1000)
        with pytest.raises(HTTPException) as error:
            build(LocalCircuit(CONTAINER_CIRCUIT), directory)
        assert refusal(error) == (HTTPStatus.UNPROCESSABLE_ENTITY, Refusal.TOO_MANY_POINTS)

    def test_a_file_the_circuit_does_not_have(self, directory, monkeypatch):
        client = LocalCircuit(CONTAINER_CIRCUIT)
        monkeypatch.setattr(client, "list_directory", lambda **_: SimpleNamespace(files={}))
        with pytest.raises(HTTPException) as error:
            build(client, directory)
        assert error.value.status_code == HTTPStatus.BAD_REQUEST
        assert str(NODES) in str(error.value.detail)


class TestOneAtATime:
    def test_a_request_gives_up_while_another_pack_is_built(self, directory, monkeypatch):
        monkeypatch.setattr(service, "PATIENCE_SECONDS", 0)
        client = LocalCircuit(CONTAINER_CIRCUIT)
        with BUILDING, pytest.raises(HTTPException) as error:
            build(client, directory)
        assert refusal(error) == (HTTPStatus.SERVICE_UNAVAILABLE, Refusal.BUSY)
        assert client.listed == 0

    def test_the_way_is_free_again_after_a_build(self, directory):
        build(LocalCircuit(CONTAINER_CIRCUIT), directory)
        assert not BUILDING.locked()

    def test_the_way_is_free_again_after_a_refusal(self, directory):
        with pytest.raises(HTTPException):
            build(LocalCircuit(CONTAINER_CIRCUIT), directory, 10)
        assert not BUILDING.locked()


@pytest.fixture
def kept_dir(tmp_path_factory, monkeypatch):
    path = tmp_path_factory.mktemp("kept").resolve()
    monkeypatch.setattr(settings, "CIRCUIT_MORPHOLOGY_PACK_CACHE_DIR", path)
    return path


def pack_of(client, circuit_id, tmp_path_factory, *, all_levels=True) -> bytes:
    return build_circuit_morphology_pack(
        client,
        circuit_id,
        tmp_path_factory.mktemp("staged").resolve(),
        DEFAULT_MAX_SEGMENTS,
        all_levels=all_levels,
    )


def asset(asset_id=None):
    return SimpleNamespace(id=asset_id or uuid4())


class TestKept:
    def test_a_kept_pack_is_not_built_again(self, kept_dir, tmp_path_factory):
        circuit_id, asset_id = uuid4(), uuid4()
        built = pack_of(
            LocalCircuit(CONTAINER_CIRCUIT, asset_id=asset_id), circuit_id, tmp_path_factory
        )
        again = LocalCircuit(CONTAINER_CIRCUIT, asset_id=asset_id)
        assert pack_of(again, circuit_id, tmp_path_factory) == built
        assert again.listed == 0
        assert again.fetched == []
        assert list(kept_dir.iterdir()) == [service.kept_path(asset(asset_id))]

    def test_a_pack_of_one_level_is_not_kept(self, kept_dir, tmp_path_factory):
        pack_of(LocalCircuit(CONTAINER_CIRCUIT), uuid4(), tmp_path_factory, all_levels=False)
        assert not any(kept_dir.iterdir())

    def test_nothing_is_kept_unless_a_directory_is_given(self):
        assert service.kept_path(asset()) is None

    @pytest.mark.usefixtures("kept_dir")
    def test_each_asset_is_kept_apart(self):
        assert service.kept_path(asset()) != service.kept_path(asset())

    def test_the_packs_used_longest_ago_go(self, kept_dir, monkeypatch):
        monkeypatch.setattr(settings, "CIRCUIT_MORPHOLOGY_PACK_CACHE_MAX_BYTES", 20)
        first, second, third = (service.kept_path(asset()) for _ in range(3))
        service.keep(first, b"x" * 10)
        service.keep(second, b"x" * 10)
        os.utime(first, ns=(0, 0))
        os.utime(second, ns=(1, 1))
        assert service.kept(first) is not None
        service.keep(third, b"x" * 10)
        assert sorted(kept_dir.iterdir()) == sorted([first, third])

    def test_only_packs_are_let_go_of(self, kept_dir, monkeypatch):
        monkeypatch.setattr(settings, "CIRCUIT_MORPHOLOGY_PACK_CACHE_MAX_BYTES", 10)
        other = kept_dir / "other"
        other.write_bytes(b"x" * 10)
        os.utime(other, ns=(0, 0))
        first, second = (service.kept_path(asset()) for _ in range(2))
        service.keep(first, b"x" * 10)
        service.keep(second, b"x" * 10)
        assert sorted(kept_dir.iterdir()) == sorted([other, second])

    def test_a_pack_over_the_bytes_allowed_is_not_kept(
        self, kept_dir, tmp_path_factory, monkeypatch
    ):
        monkeypatch.setattr(settings, "CIRCUIT_MORPHOLOGY_PACK_CACHE_MAX_BYTES", 1000)
        pack_of(LocalCircuit(CONTAINER_CIRCUIT), uuid4(), tmp_path_factory)
        assert not any(kept_dir.iterdir())

    def test_a_pack_that_cannot_be_kept_is_still_given(self, kept_dir, tmp_path_factory):
        kept_dir.chmod(0o500)
        try:
            pack = read_pack(pack_of(LocalCircuit(CONTAINER_CIRCUIT), uuid4(), tmp_path_factory))
        finally:
            kept_dir.chmod(0o700)
        assert len(pack.levels) == len(LEVELS)
        assert not any(kept_dir.iterdir())
        assert not BUILDING.locked()

    def test_a_kept_pack_is_given_only_to_who_may_see_the_circuit(
        self, kept_dir, tmp_path_factory, monkeypatch
    ):
        asset_id = uuid4()
        service.kept_path(asset(asset_id)).write_bytes(b"kept")
        stranger = LocalCircuit(CONTAINER_CIRCUIT, asset_id=asset_id)

        def forbidden(**_):
            raise EntitySDKError

        monkeypatch.setattr(stranger, "get_entity", forbidden)
        with pytest.raises(HTTPException) as error:
            pack_of(stranger, uuid4(), tmp_path_factory)
        assert error.value.status_code == HTTPStatus.BAD_REQUEST
        assert any(kept_dir.iterdir())

    @pytest.mark.usefixtures("kept_dir")
    def test_a_request_that_waited_is_given_the_pack_built_meanwhile(
        self, tmp_path_factory, monkeypatch
    ):
        monkeypatch.setattr(service, "PATIENCE_SECONDS", 10)
        circuit_id, asset_id = uuid4(), uuid4()
        looked = threading.Event()
        kept = service.kept

        def watched(where):
            found = kept(where)
            looked.set()
            return found

        monkeypatch.setattr(service, "kept", watched)
        waiting = LocalCircuit(CONTAINER_CIRCUIT, asset_id=asset_id)
        given = []
        with BUILDING:
            thread = threading.Thread(
                target=lambda: given.append(pack_of(waiting, circuit_id, tmp_path_factory))
            )
            thread.start()
            assert looked.wait(10)
            service.kept_path(asset(asset_id)).write_bytes(b"built meanwhile")
        thread.join(10)
        assert not thread.is_alive()
        assert given == [b"built meanwhile"]
        assert waiting.listed == 0
