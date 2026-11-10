"""Shared fixtures for obi_one lib tests."""

from pathlib import Path

import pytest

from obi_one.core.run_tasks import run_tasks_for_generated_scan
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific import library
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.morphology_containerization import (
    MorphologyContainerizationScanConfig,
)

from tests.utils import CIRCUIT_DIR

CONTAINERIZATION_CIRCUIT_NAME = "nbS1-O1-E2Sst-maxNsyn-HEX0-L5"


@pytest.fixture(scope="session")
def containerized_hex0_l5_circuit(tmp_path_factory: pytest.TempPathFactory) -> Circuit:
    """Run morphology containerization once; reused by containerization + Circuit load tests."""
    output_root = tmp_path_factory.mktemp("containerized_hex0_l5")
    source = Circuit(
        name=CONTAINERIZATION_CIRCUIT_NAME,
        path=str(CIRCUIT_DIR / CONTAINERIZATION_CIRCUIT_NAME / "circuit_config.json"),
    )
    hoc_path = Path(library.__file__).parent
    scan_config = MorphologyContainerizationScanConfig(
        initialize=MorphologyContainerizationScanConfig.Initialize(
            circuit=[source],
            hoc_template_old=str(hoc_path / "cell_template_neurodamus.jinja2"),
            hoc_template_new=str(hoc_path / "cell_template_neurodamus_obi.jinja2"),
        )
    )
    grid_scan = GridScanGenerationTask(
        form=scan_config,
        output_root=output_root,
        coordinate_directory_option="VALUE",
    )
    grid_scan.execute()
    run_tasks_for_generated_scan(grid_scan)

    return Circuit(
        name=source.name,
        path=str(output_root / source.name / "circuit_config.json"),
    )
