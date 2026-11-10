from pathlib import Path

from obi_one.core.run_tasks import run_tasks_for_generated_scan
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.morphology_decontainerization import (
    MorphologyDecontainerizationScanConfig,
)

from tests.utils import CIRCUIT_DIR


def _circuit(name: str) -> Circuit:
    return Circuit(name=name, path=str(CIRCUIT_DIR / name / "circuit_config.json"))


def _run_decontainerization(tmp_path, circuits, output_formats, run_name: str):
    form = MorphologyDecontainerizationScanConfig(
        initialize=MorphologyDecontainerizationScanConfig.Initialize(
            circuit=circuits,
            output_format=output_formats,
        )
    )
    grid_scan = GridScanGenerationTask(
        form=form,
        output_root=tmp_path / run_name,
        coordinate_directory_option="VALUE",
    )
    grid_scan.execute()
    run_tasks_for_generated_scan(grid_scan)
    return grid_scan


def _assert_decontainerized_outputs(grid_scan) -> None:
    for instance in grid_scan.single_configs:
        cname = instance.initialize.circuit.name
        fmt = instance.initialize.output_format
        out_path = Path(instance.coordinate_output_root)
        circuit = Circuit(name=cname, path=str(out_path / "circuit_config.json"))
        nodes = circuit.sonata_circuit.nodes[circuit.default_population_name]
        morph_dir = Path(nodes.morph.get_morphology_dir(extension=fmt))
        assert morph_dir.is_dir()
        assert morph_dir.stem == fmt
        files = list(morph_dir.iterdir())
        assert all(f.suffix == f".{fmt}" for f in files)
        for nid in nodes.ids():
            _ = nodes.morph.get(nid, transform=True, extension=fmt)


def test_morphology_decontainerization(tmp_path):
    """All formats on one circuit; second circuit only h5 (still covers both + all formats)."""
    circuit_a = _circuit("N_10__top_nodes_dim6")
    circuit_b = _circuit("N_10__top_rc_nodes_dim2_rc")

    formats_scan = _run_decontainerization(tmp_path, circuit_a, ["swc", "asc", "h5"], "formats")
    assert len(formats_scan.single_configs) == 3
    _assert_decontainerized_outputs(formats_scan)

    second_circuit_scan = _run_decontainerization(tmp_path, circuit_b, ["h5"], "second")
    assert len(second_circuit_scan.single_configs) == 1
    _assert_decontainerized_outputs(second_circuit_scan)
