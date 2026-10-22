from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import libsonata
import pytest

from obi_one.scientific.library.morphology_pack.build import build_morphology_pack
from obi_one.scientific.library.morphology_pack.reader import read_pack
from obi_one.scientific.library.morphology_pack.staging import stage_morphology_pack_inputs

from tests.utils import CIRCUIT_DIR

CONTAINER_CIRCUIT = CIRCUIT_DIR / "N_10__top_nodes_dim6"
FOLDER_CIRCUIT = CIRCUIT_DIR / "nbS1-O1-E2Sst-maxNsyn-HEX0-L5"
POPULATION = "S1nonbarrel_neurons"
CONFIG = Path("circuit_config.json")
NODES = Path(POPULATION) / "nodes.h5"


class LocalCircuit:
    """Stands in for the database client: a circuit's files are linked from a directory."""

    def __init__(self, source: Path):
        self.source = source
        self.asset = SimpleNamespace(id=uuid4())
        self.fetched = []

    def select_assets(self, circuit, selection):  # ruff: ignore[unused-method-argument]
        return SimpleNamespace(one=lambda: self.asset)

    def fetch_file(self, *, asset_id, output_path, asset_path, **_):
        assert asset_id is self.asset
        self.fetched.append(asset_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.symlink_to(self.source / asset_path)
        return output_path


def nodes_of(source: Path) -> list[Path]:
    """The config, node sets and every population's nodes the circuit at `source` declares."""
    config = libsonata.CircuitConfig.from_file(str(source / CONFIG))
    declared = {
        config.node_population_properties(name).elements_path for name in config.node_populations
    }
    if config.node_sets_path:
        declared.add(config.node_sets_path)
    return [CONFIG, *(Path(path).relative_to(source.resolve()) for path in declared)]


@pytest.fixture
def circuit():
    return SimpleNamespace(id=uuid4())


def test_a_container_of_morphologies(tmp_path, circuit):
    client = LocalCircuit(CONTAINER_CIRCUIT)
    config = stage_morphology_pack_inputs(client, circuit, tmp_path)
    assert config == tmp_path.resolve() / CONFIG
    assert sorted(client.fetched) == sorted(
        [*nodes_of(CONTAINER_CIRCUIT), Path("morphologies/merged-morphologies.h5")]
    )
    pack = read_pack(build_morphology_pack(config, 10**12, 1))
    assert set(pack.levels[0].cells) == set(range(10))


def test_a_folder_of_morphologies(tmp_path, circuit):
    client = LocalCircuit(FOLDER_CIRCUIT)
    stage_morphology_pack_inputs(client, circuit, tmp_path)
    nodes = libsonata.NodeStorage(str(FOLDER_CIRCUIT / NODES)).open_population(POPULATION)
    names = set(nodes.get_attribute("morphology", nodes.select_all()))
    assert sorted(client.fetched) == sorted(
        [*nodes_of(FOLDER_CIRCUIT), *(Path("morphologies/swc") / f"{name}.swc" for name in names)]
    )
