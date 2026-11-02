"""What ``stage_circuit_nodes`` fetches out of a circuit's ``sonata_circuit`` asset.

Campaign generation reads node properties and node sets and nothing else, so the staging it asks
for has to leave the edge files alone -- on a large circuit they dwarf everything else, and a
private-project circuit is downloaded rather than symlinked. These tests pin which files are
requested, and that the requested paths are relative to the asset root whichever way the config's
manifest is written.
"""

import json
from pathlib import Path

import bluepysnap
import pytest

from obi_one.scientific.library.circuit_staging import (
    CIRCUIT_CONFIG_FILE_NAME,
    stage_circuit_nodes,
)

from tests.utils import CIRCUIT_DIR

CIRCUIT_NAME = "N_10__top_nodes_dim6"
SOURCE_CIRCUIT = CIRCUIT_DIR / CIRCUIT_NAME
ENTITY_ID = "11111111-2222-3333-4444-555555555555"

NODES_FILES = {
    "S1nonbarrel_neurons/nodes.h5",
    "POm/nodes.h5",
    "VPM/nodes.h5",
}
EDGES_FILES = {
    "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical/edges.h5",
    "VPM__S1nonbarrel_neurons__chemical/edges.h5",
    "POm__S1nonbarrel_neurons__chemical/edges.h5",
}


class FakeAsset:
    """Stands in for the ``sonata_circuit`` directory asset."""

    id = "99999999-2222-3333-4444-555555555555"


class FakeDBClient:
    """Serves files out of a local circuit directory, recording what was asked for.

    ``fetch_file`` is the only client call staging makes. Copying rather than linking keeps the
    staged config a real file, which is what makes ``$BASE_DIR`` resolve into the staging
    directory -- the property the production code relies on.
    """

    def __init__(self, source: Path) -> None:
        self._source = source
        self.requested: list[str] = []

    def fetch_file(self, *, output_path: Path, asset_path: Path, **_: object) -> Path:
        self.requested.append(str(asset_path))
        source_file = self._source / asset_path
        if not source_file.exists():
            msg = f"'{asset_path}' is not in the asset"
            raise FileNotFoundError(msg)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(source_file.read_bytes())
        return output_path


def _circuit_source(tmp_path: Path, base_dir: str | None = None) -> Path:
    """A copy of the test circuit, optionally with its manifest's ``$BASE_DIR`` rewritten."""
    source = tmp_path / "asset"
    source.mkdir()

    config = json.loads((SOURCE_CIRCUIT / CIRCUIT_CONFIG_FILE_NAME).read_text())
    if base_dir is not None:
        config["manifest"]["$BASE_DIR"] = base_dir
    (source / CIRCUIT_CONFIG_FILE_NAME).write_text(json.dumps(config))

    # Only the files staging is allowed to want; anything else it asks for should fail loudly.
    for relative in {"node_sets.json", *NODES_FILES}:
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((SOURCE_CIRCUIT / relative).read_bytes())

    return source


class TestWhichFilesAreStaged:
    def test_the_config_node_sets_and_every_nodes_file_are_fetched(self, tmp_path):
        db_client = FakeDBClient(_circuit_source(tmp_path))
        dest_dir = tmp_path / "staged"

        config_path = stage_circuit_nodes(
            db_client, entity_id=ENTITY_ID, asset=FakeAsset(), dest_dir=dest_dir
        )

        assert config_path == dest_dir / CIRCUIT_CONFIG_FILE_NAME
        assert set(db_client.requested) == {
            CIRCUIT_CONFIG_FILE_NAME,
            "node_sets.json",
            *NODES_FILES,
        }

    def test_no_edge_file_is_fetched(self, tmp_path):
        """The point of the whole exercise: edges dominate a large circuit and are never read."""
        db_client = FakeDBClient(_circuit_source(tmp_path))

        stage_circuit_nodes(
            db_client, entity_id=ENTITY_ID, asset=FakeAsset(), dest_dir=tmp_path / "staged"
        )

        assert EDGES_FILES.isdisjoint(db_client.requested)
        assert not any("edges" in path for path in db_client.requested)

    def test_the_staged_circuit_is_loadable(self, tmp_path):
        """Staged in isolation, the config still resolves against what was fetched."""
        db_client = FakeDBClient(_circuit_source(tmp_path))
        dest_dir = tmp_path / "staged"

        stage_circuit_nodes(db_client, entity_id=ENTITY_ID, asset=FakeAsset(), dest_dir=dest_dir)

        circuit = bluepysnap.Circuit(str(dest_dir / CIRCUIT_CONFIG_FILE_NAME))
        assert set(circuit.nodes.population_names) == {"S1nonbarrel_neurons", "POm", "VPM"}
        # Reading a property proves the nodes file itself landed, not just its path.
        assert len(circuit.nodes["S1nonbarrel_neurons"].ids()) == 10

    def test_a_config_without_node_sets_stages_the_rest(self, tmp_path):
        """``node_sets_file`` is optional, and absent from expanded_json when not declared."""
        source = _circuit_source(tmp_path)
        config_file = source / CIRCUIT_CONFIG_FILE_NAME
        config = json.loads(config_file.read_text())
        del config["node_sets_file"]
        config_file.write_text(json.dumps(config))
        (source / "node_sets.json").unlink()

        db_client = FakeDBClient(source)

        stage_circuit_nodes(
            db_client, entity_id=ENTITY_ID, asset=FakeAsset(), dest_dir=tmp_path / "staged"
        )

        assert set(db_client.requested) == {CIRCUIT_CONFIG_FILE_NAME, *NODES_FILES}


class TestManifestShapes:
    """The declared paths come out of ``expanded_json``, which reflects the manifest."""

    def test_a_relative_base_dir_yields_asset_relative_paths(self, tmp_path):
        db_client = FakeDBClient(_circuit_source(tmp_path, base_dir="./"))

        stage_circuit_nodes(
            db_client, entity_id=ENTITY_ID, asset=FakeAsset(), dest_dir=tmp_path / "staged"
        )

        assert set(db_client.requested) >= NODES_FILES
        assert all(not Path(path).is_absolute() for path in db_client.requested)

    def test_an_absolute_base_dir_is_made_relative_again(self, tmp_path):
        """An absolute $BASE_DIR pointing at the staging directory still resolves."""
        dest_dir = tmp_path / "staged"
        db_client = FakeDBClient(_circuit_source(tmp_path, base_dir=str(dest_dir)))

        stage_circuit_nodes(db_client, entity_id=ENTITY_ID, asset=FakeAsset(), dest_dir=dest_dir)

        assert set(db_client.requested) >= NODES_FILES
        assert all(not Path(path).is_absolute() for path in db_client.requested)

    def test_an_absolute_base_dir_outside_the_staging_directory_is_refused(self, tmp_path):
        """Such a path names no file inside the asset, so it cannot be fetched."""
        db_client = FakeDBClient(_circuit_source(tmp_path, base_dir="/somewhere/else"))

        with pytest.raises(ValueError, match="outside the staging directory"):
            stage_circuit_nodes(
                db_client, entity_id=ENTITY_ID, asset=FakeAsset(), dest_dir=tmp_path / "staged"
            )
