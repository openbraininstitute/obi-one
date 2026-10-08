import tarfile
from pathlib import Path

import obi_one as obi
from obi_one.db_sdk.registration.circuit.assets import (
    COMPRESSED_CIRCUIT_FILENAME,
    COMPRESSED_CIRCUIT_FORMAT,
    COMPRESSED_CIRCUIT_NAME,
)

from tests.utils import CIRCUIT_DIR


def test_folder_compression(tmp_path):
    # Set up circuit folder compression
    folder_list = [
        obi.NamedPath(
            name="N_10__top_nodes_dim6",
            path=str(CIRCUIT_DIR / "N_10__top_nodes_dim6"),
        ),
        obi.NamedPath(
            name="N_10__top_rc_nodes_dim2_rc",
            path=str(CIRCUIT_DIR / "N_10__top_rc_nodes_dim2_rc"),
        ),
    ]
    compression_init = obi.FolderCompressionScanConfig.Initialize(
        folder_path=folder_list, file_format=["gz", "bz2", "xz"], file_name="circuit"
    )
    folder_compressions_form = obi.FolderCompressionScanConfig(initialize=compression_init)

    # Run circuit folder compression
    grid_scan = obi.GridScanGenerationTask(
        form=folder_compressions_form,
        output_root=tmp_path / "grid_scan",
        coordinate_directory_option="VALUE",
    )
    grid_scan.execute()
    obi.run_tasks_for_generated_scan(grid_scan)

    # Check that expected files have been created
    instances = grid_scan.single_configs
    assert len(instances) == 6
    for instance in instances:
        fmt = instance.initialize.file_format
        out_path = tmp_path / grid_scan.output_root / instance.initialize.folder_path.name / fmt
        assert (out_path / f"{instance.initialize.file_name}.tar.{fmt}").exists()


def test_output_filename_and_path():
    """The archive filename/path is derived as "<name>.tar.<format>"."""
    initialize = obi.FolderCompressionScanConfig.Initialize(
        folder_path=obi.NamedPath(name="circuit_folder", path="/some/folder"),
        file_format="gz",
        file_name="circuit",
    )
    single_config = obi.FolderCompressionSingleConfig(initialize=initialize)
    single_config.coordinate_output_root = Path("/out")

    assert initialize.output_filename == "circuit.tar.gz"
    assert single_config.output_path == Path("/out/circuit.tar.gz")


def test_compressed_circuit_filename_matches_compression_output():
    """The asset content-check name must match what the compression config produces."""
    initialize = obi.FolderCompressionScanConfig.Initialize(
        folder_path=obi.NamedPath(name="circuit_folder", path="/some/folder"),
        file_format=COMPRESSED_CIRCUIT_FORMAT,
        file_name=COMPRESSED_CIRCUIT_NAME,
    )

    assert initialize.output_filename == COMPRESSED_CIRCUIT_FILENAME


def test_compression_dereferences_symlinks(tmp_path):
    """Symlinks in the source folder are archived as real files, not as links.

    Circuits staged by the launch-system are symlinks into the mounted asset store, so the
    archive must contain the dereferenced file contents to be usable once extracted elsewhere.
    """
    # External target the symlink points to (outside the compressed folder).
    external = tmp_path / "external_target.txt"
    external.write_text("real content")

    source = tmp_path / "circuit"
    source.mkdir()
    (source / "plain.txt").write_text("plain content")
    (source / "linked.txt").symlink_to(external)

    compression_init = obi.FolderCompressionScanConfig.Initialize(
        folder_path=obi.NamedPath(name="circuit", path=str(source)),
        file_format="gz",
        file_name="circuit",
    )
    form = obi.FolderCompressionScanConfig(initialize=compression_init)
    grid_scan = obi.GridScanGenerationTask(
        form=form,
        output_root=tmp_path / "grid_scan",
        coordinate_directory_option="NONE",
    )
    grid_scan.execute()
    obi.run_tasks_for_generated_scan(grid_scan)

    archive = grid_scan.single_configs[0].output_path
    with tarfile.open(archive, "r:gz") as tar:
        linked_member = tar.getmember("circuit/linked.txt")
        # The link must be stored as a regular file (dereferenced), not a symlink.
        assert linked_member.isfile()
        assert not linked_member.issym()
        assert tar.extractfile(linked_member).read() == b"real content"
