"""Fixtures for circuit simplification tests.

Uses the corrected fixture pattern from __imp_04Aug2026.md Part 3:
- ``fake_simplified_circuit`` creates a real tmp_path with a minimal
  circuit_config.json (so ``execute()`` doesn't skip registration).
- ``mock_pipeline`` injects fake sonata_simplify modules into sys.modules
  so execute() can run without the optional private package installed.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def fake_simplified_circuit(tmp_path: Path) -> Path:
    """Create a minimal simplified circuit in a tmp directory."""
    d = tmp_path / "simplified"
    d.mkdir(parents=True)
    (d / "circuit_config.json").write_text(
        json.dumps(
            {
                "version": "2.3",
                "manifest": {"$BASE_DIR": "./"},
                "networks": {"nodes": [], "edges": []},
            }
        )
    )
    return d


@pytest.fixture
def mock_pipeline(fake_simplified_circuit: Path):
    """Inject fake sonata_simplify modules so execute() can run without the package.

    Mirrors the ultraliser sys.modules mock in test_skeletonization: sonata-simplify
    is an optional private dependency and is not installed in every environment.
    The API-signature guard lives in test_pipeline_accepts_simulation_config.
    """
    pipeline_mod = MagicMock(name="sonata_simplify.pipeline")
    recipe_mod = MagicMock(name="sonata_simplify.recipe")
    pipeline_mod.SimplificationPipeline.return_value.run_recipe.return_value = [
        fake_simplified_circuit
    ]
    with (
        patch.dict(
            sys.modules,
            {
                "sonata_simplify": MagicMock(name="sonata_simplify"),
                "sonata_simplify.pipeline": pipeline_mod,
                "sonata_simplify.recipe": recipe_mod,
            },
        ),
        patch(
            "obi_one.scientific.tasks.circuit_simplification.task.simplification_package_versions",
            return_value={
                "obi-one": "0.0.0",
                "sonata-simplify": "0.0.0",
                "bluecellulab": "0.0.0",
            },
        ),
    ):
        yield pipeline_mod.SimplificationPipeline


@pytest.fixture
def mock_mechanism_compilation():
    """Mock the mechanism compilation step added by the task launch fix.

    Patches ``process.get_mechanisms_dirs`` and ``process.compile_mechanisms``
    so tests that exercise ``execute()`` with ``single_compartment`` don't
    require a real circuit with MOD files.
    """
    with (
        patch(
            "obi_one.scientific.tasks.circuit_simplification.task.process.get_mechanisms_dirs",
            return_value=[Path("/fake/mod")],
        ),
        patch(
            "obi_one.scientific.tasks.circuit_simplification.task.process.compile_mechanisms",
        ),
    ):
        yield
