import shutil
from pathlib import Path

import h5py
import pytest
from bluepysnap import BluepySnapError

from obi_one.core.run_tasks import run_tasks_for_generated_scan
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific import library
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.morphology_containerization.config import (
    MorphologyContainerizationScanConfig,
)

from tests.obi_one.conftest import CONTAINERIZATION_CIRCUIT_NAME
from tests.utils import CIRCUIT_DIR


def test_morphology_containerization(containerized_hex0_l5_circuit: Circuit):
    """Assert containerized morph wiring on the shared session fixture circuit."""
    circuit = containerized_hex0_l5_circuit
    nodes = circuit.sonata_circuit.nodes[circuit.default_population_name]
    # Check .h5 morph dir --> Error, since .h5 container file
    with pytest.raises(
        BluepySnapError,
        match=r"'.*' is a morphology container, so a directory does not exist",
    ):
        _ = Path(nodes.morph.get_morphology_dir(extension="h5"))
    # Check .swc morph dir --> Error, since no .swc folder defined
    with pytest.raises(BluepySnapError, match="'morphologies_dir' is not defined in config"):
        _ = Path(nodes.morph.get_morphology_dir(extension="swc"))
    # Check .asc morph dir --> Error, since no .asc folder defined
    with pytest.raises(
        BluepySnapError, match="'neurolucida-asc' is not defined in 'alternate_morphologies'"
    ):
        _ = Path(nodes.morph.get_morphology_dir(extension="asc"))
    # Check .h5 container file
    h5_file = Path(nodes.morph._get_morphology_base("h5"))
    assert h5_file.is_file()
    assert h5_file.parts[-1] == "merged-morphologies.h5"
    # Check morph access
    for nid in nodes.ids():
        _ = nodes.morph.get(nid, transform=True, extension="h5")


def _make_nested_morphology_circuit(target_dir: Path, subfolders: list[str]) -> Path:
    """Copy the test circuit and move its morphologies into the given subfolders.

    The morphology names in the nodes file are updated to the relative paths, so that each
    morphology is referenced as `<subfolder>/<name>`.
    """
    shutil.copytree(CIRCUIT_DIR / CONTAINERIZATION_CIRCUIT_NAME, target_dir)
    morph_dir = target_dir / "morphologies" / "swc"
    nodes_file = target_dir / "S1nonbarrel_neurons" / "nodes.h5"
    with h5py.File(nodes_file, "r+") as f:
        group = f["nodes/S1nonbarrel_neurons/0"]
        names = [n.decode() for n in group["morphology"][:]]
        unique_names = sorted(set(names))
        assert len(unique_names) == len(subfolders)
        name_map = {n: f"{sub}/{n}" for n, sub in zip(unique_names, subfolders, strict=True)}
        for old, new in name_map.items():
            (morph_dir / new).parent.mkdir(parents=True, exist_ok=True)
            (morph_dir / f"{old}.swc").rename(morph_dir / f"{new}.swc")
        del group["morphology"]
        group.create_dataset(
            "morphology",
            data=[name_map[n] for n in names],
            dtype=h5py.string_dtype(),
        )
    return target_dir / "circuit_config.json"


def test_morphology_containerization_nested_folders(tmp_path: Path):
    """Morphologies in (multi-level) subfolders are merged into matching container groups."""
    subfolders = ["sub_a", "sub_a/sub_b"]
    circuit_name = "nested_morphologies"
    config_path = _make_nested_morphology_circuit(tmp_path / "input" / circuit_name, subfolders)

    hoc_path = Path(library.__file__).parent
    scan_config = MorphologyContainerizationScanConfig(
        initialize=MorphologyContainerizationScanConfig.Initialize(
            circuit=[Circuit(name=circuit_name, path=str(config_path))],
            hoc_template_old=str(hoc_path / "cell_template_neurodamus.jinja2"),
            hoc_template_new=str(hoc_path / "cell_template_neurodamus_obi.jinja2"),
        )
    )
    output_root = tmp_path / "output"
    grid_scan = GridScanGenerationTask(
        form=scan_config,
        output_root=output_root,
        coordinate_directory_option="VALUE",
    )
    grid_scan.execute()
    run_tasks_for_generated_scan(grid_scan)

    circuit = Circuit(
        name=circuit_name, path=str(output_root / circuit_name / "circuit_config.json")
    )
    nodes = circuit.sonata_circuit.nodes[circuit.default_population_name]

    # Original (nested) morphology folder removed
    assert not (output_root / circuit_name / "morphologies" / "swc").exists()

    # Subfolders preserved as groups within the container
    h5_file = Path(nodes.morph._get_morphology_base("h5"))
    assert h5_file.is_file()
    morph_names = set(nodes.get(properties="morphology"))
    with h5py.File(h5_file, "r") as f:
        for sub in subfolders:
            assert isinstance(f[sub], h5py.Group)
        for name in morph_names:
            assert Path(name).parent.as_posix() in subfolders
            assert name in f

    # Morphologies accessible through the container
    for nid in nodes.ids():
        _ = nodes.morph.get(nid, transform=True, extension="h5")
