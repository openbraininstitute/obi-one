from pathlib import Path

import pytest
from bluepysnap import BluepySnapError

import obi_one as obi
from obi_one.scientific import library

from tests.utils import CIRCUIT_DIR


def test_morphology_containerization(tmp_path):
    # Set up morphology containerization
    circuit_list = [
        obi.Circuit(
            name="nbS1-O1-E2Sst-maxNsyn-HEX0-L5",
            path=str(CIRCUIT_DIR / "nbS1-O1-E2Sst-maxNsyn-HEX0-L5" / "circuit_config.json"),
        ),
    ]

    hoc_path = Path(library.__file__).parent
    containerization_init = obi.MorphologyContainerizationScanConfig.Initialize(
        circuit=circuit_list,
        hoc_template_old=str(hoc_path / "cell_template_neurodamus.jinja2"),
        hoc_template_new=str(hoc_path / "cell_template_neurodamus_obi.jinja2"),
    )
    morphology_containerization_scan_config = obi.MorphologyContainerizationScanConfig(
        initialize=containerization_init
    )

    # Run containerization
    grid_scan = obi.GridScanGenerationTask(
        form=morphology_containerization_scan_config,
        output_root=tmp_path / "grid_scan",
        coordinate_directory_option="VALUE",
    )
    grid_scan.execute()
    obi.run_tasks_for_generated_scan(grid_scan)

    # Check that output circuits with containerized morphologies are created and accessible
    instances = grid_scan.single_configs
    assert len(instances) == 1
    for instance in instances:
        cname = instance.initialize.circuit.name
        out_path = tmp_path / grid_scan.output_root / cname
        # Check output circuit
        circuit = obi.Circuit(name=cname, path=str(out_path / "circuit_config.json"))
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
