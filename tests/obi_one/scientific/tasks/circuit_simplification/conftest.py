"""Fixtures for circuit simplification tests.

Uses the corrected fixture pattern from __imp_04Aug2026.md Part 3:
- ``fake_simplified_circuit`` creates a real tmp_path with a minimal
  circuit_config.json (so ``execute()`` doesn't skip registration).
- ``mock_pipeline`` patches with ``autospec=True`` so signature drift
  in sonata_simplify fails the test (compatibility guard for free).
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def fake_simplified_circuit(tmp_path: Path) -> Path:
    """Create a minimal simplified circuit in a tmp directory."""
    d = tmp_path / "simplified"
    d.mkdir(parents=True)
    (d / "circuit_config.json").write_text(
        json.dumps({
            "version": "2.3",
            "manifest": {"$BASE_DIR": "./"},
            "networks": {"nodes": [], "edges": []},
        })
    )
    return d


@pytest.fixture
def mock_pipeline(fake_simplified_circuit: Path):
    """Mock SimplificationPipeline with autospec for API compatibility guard."""
    with patch(
        "sonata_simplify.pipeline.SimplificationPipeline", autospec=True
    ) as m:
        # run_recipe returns a list of output paths (one per target)
        m.return_value.run_recipe.return_value = [fake_simplified_circuit]
        yield m
