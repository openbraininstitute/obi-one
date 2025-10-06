from pathlib import Path

import obi_one as obi

from tests.utils import CIRCUIT_DIR


def test_morphology_decontainerization(tmp_path):
    # Set up morphology decontainerization
    circuit_list = [
        obi.Circuit(
            name="N_10__top_nodes_dim6",
            path=str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"),
        ),
        obi.Circuit(
            name="N_10__top_rc_nodes_dim2_rc",
            path=str(CIRCUIT_DIR / "N_10__top_rc_nodes_dim2_rc" / "circuit_config.json"),
        ),
    ]

    decontainerization_init = obi.MorphologyDecontainerizationScanConfig.Initialize(
        circuit=circuit_list, output_format=["swc", "asc", "h5"]
    )
    morphology_decontainerization_scan_config = obi.MorphologyDecontainerizationScanConfig(
        initialize=decontainerization_init
    )

    # Run decontainerization
    grid_scan = obi.GridScanGenerationTask(
        form=morphology_decontainerization_scan_config,
        output_root=tmp_path / "grid_scan",
        coordinate_directory_option="VALUE",
    )
    grid_scan.execute()
    obi.run_tasks_for_generated_scan(grid_scan)

    # Check that output circuits with individual morphologies have been created and are accessible
    instances = grid_scan.single_configs
    assert len(instances) == 6
    for instance in instances:
        cname = instance.initialize.circuit.name
        fmt = instance.initialize.output_format
        out_path = tmp_path / grid_scan.output_root / cname / fmt
        # Check output circuit
        circuit = obi.Circuit(name=cname, path=str(out_path / "circuit_config.json"))
        nodes = circuit.sonata_circuit.nodes[circuit.default_population_name]
        # Check morph dir
        morph_dir = Path(nodes.morph.get_morphology_dir(extension=fmt))
        assert morph_dir.is_dir()
        assert morph_dir.stem == fmt
        # Check morph format
        files = list(morph_dir.iterdir())
        assert all(f.suffix == f".{fmt}" for f in files)
        # Check morph access
        for nid in nodes.ids():
            _ = nodes.morph.get(nid, transform=True, extension=fmt)
