"""Tests for what ``launch_circuit_asset_generation`` stages and builds."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LAUNCH_MAIN = _REPO_ROOT / "launch_scripts/launch_circuit_asset_generation/main.py"


@pytest.fixture
def launch_main(monkeypatch):
    monkeypatch.setenv("PERSISTENT_TOKEN_ID", "local-test-token")
    monkeypatch.setenv("DEPLOYMENT", "staging")
    monkeypatch.delenv("LOCAL_STORE_PREFIX", raising=False)
    spec = importlib.util.spec_from_file_location("launch_circuit_asset_generation", _LAUNCH_MAIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(launch_main, circuit, *, force=False):
    """Run the script for `circuit`, every step standing in; the steps."""
    db_client = MagicMock()
    db_client.get_entity.return_value = circuit
    steps = MagicMock()
    with (
        patch.object(launch_main, "Client", return_value=db_client),
        patch.object(launch_main, "stage_circuit", steps.stage_circuit),
        patch.object(launch_main, "OBICircuit", steps.OBICircuit),
        patch.object(launch_main, "generate_additional_circuit_assets", steps.generate_additional),
        patch.object(
            launch_main, "stage_morphology_pack_inputs", steps.stage_morphology_pack_inputs
        ),
        patch.object(launch_main, "generate_morphology_pack_asset", steps.generate_pack),
        patch.object(
            sys,
            "argv",
            [
                "main.py",
                f"--circuit_id={uuid4()}",
                f"--virtual_lab_id={uuid4()}",
                f"--project_id={uuid4()}",
                f"--force={str(force).lower()}",
            ],
        ),
    ):
        assert launch_main.main() == 0
    return steps


def circuit_with(*labels):
    circuit = MagicMock()
    circuit.scale = "small"
    circuit.assets = [MagicMock(label=label) for label in labels]
    return circuit


PACK_MISSING = ("compressed_sonata_circuit", "circuit_connectivity_matrices")


def test_only_the_packs_files_when_it_is_all_that_is_missing(launch_main):
    steps = run(launch_main, circuit_with(*PACK_MISSING))
    steps.stage_morphology_pack_inputs.assert_called_once()
    steps.generate_pack.assert_called_once()
    assert (
        steps.generate_pack.call_args.kwargs["circuit_path"]
        == steps.stage_morphology_pack_inputs.return_value
    )
    steps.stage_circuit.assert_not_called()
    steps.generate_additional.assert_not_called()


@pytest.mark.parametrize(
    ("labels", "force"),
    [(("compressed_sonata_circuit",), False), (PACK_MISSING, True)],
)
def test_the_whole_circuit_otherwise(launch_main, labels, force):
    steps = run(launch_main, circuit_with(*labels), force=force)
    steps.stage_circuit.assert_called_once()
    steps.generate_additional.assert_called_once()
    assert steps.generate_additional.call_args.kwargs["force"] is force
    steps.stage_morphology_pack_inputs.assert_not_called()
    steps.generate_pack.assert_not_called()
