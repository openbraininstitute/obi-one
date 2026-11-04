import ast
import json
import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from obi_one.scientific.library.circuit import Circuit

ROOT = Path(__file__).resolve().parents[5]
NOTEBOOKS = ROOT / "examples/obi_one/scientific/tasks/circuit_simplification"
LOCAL_NOTEBOOK = "run_simplification_local.ipynb"
BENCHMARK_NOTEBOOK = "benchmark_simplification.ipynb"


def notebook_cells(name):
    return json.loads((NOTEBOOKS / name).read_text())["cells"]


def cell_source(name, index):
    return "".join(notebook_cells(name)[index]["source"])


def run_cell(name, index, namespace):
    exec(compile(cell_source(name, index), f"{name}:cell{index}", "exec"), namespace)  # ruff: ignore[exec-builtin]


class TestSimplificationNotebooks:
    @pytest.mark.parametrize("name", [LOCAL_NOTEBOOK, BENCHMARK_NOTEBOOK])
    def test_code_cells_compile(self, name):
        for index, cell in enumerate(notebook_cells(name)):
            if cell["cell_type"] == "code":
                compile("".join(cell["source"]), f"{name}:cell{index}", "exec")

    @pytest.mark.parametrize("name", [LOCAL_NOTEBOOK, BENCHMARK_NOTEBOOK])
    def test_imports_use_current_modules(self, name, monkeypatch):
        monkeypatch.chdir(NOTEBOOKS)
        monkeypatch.setenv("PATH", os.environ["PATH"])
        namespace: dict[str, Any] = {}
        run_cell(name, 2, namespace)
        assert namespace["repo_root"] == ROOT
        assert namespace["GridScanGenerationTask"].__module__ == "obi_one.core.scan_generation"
        assert namespace["resolve_circuit"].__module__ == "obi_one.db_sdk.circuit"
        assert (
            namespace["CircuitSimplificationScanConfig"].__module__
            == "obi_one.scientific.tasks.circuit_simplification.config"
        )

    def test_local_mode_does_not_authenticate(self, monkeypatch):
        monkeypatch.setenv("PATH", os.environ["PATH"])
        namespace: dict[str, Any] = {}
        run_cell(LOCAL_NOTEBOOK, 2, namespace)
        run_cell(LOCAL_NOTEBOOK, 4, namespace)
        assert namespace["db_client"] is None
        assert namespace["REGISTER_OUTPUTS"] is False

    @pytest.mark.parametrize("algorithm", ["single_compartment", "neat_reduction"])
    def test_local_example_generates_single_config(self, algorithm, tmp_path, monkeypatch):
        monkeypatch.setenv("PATH", os.environ["PATH"])
        namespace: dict[str, Any] = {}
        run_cell(LOCAL_NOTEBOOK, 2, namespace)
        circuit_path = tmp_path / "circuit_config.json"
        circuit_path.write_text(json.dumps({"networks": {"nodes": [], "edges": []}}))
        namespace.update(
            circuit=Circuit(name="local", path=str(circuit_path)),
            REGISTER_OUTPUTS=False,
            algorithm_name=algorithm,
            output_root=tmp_path,
        )
        run_cell(LOCAL_NOTEBOOK, 19, namespace)
        run_cell(LOCAL_NOTEBOOK, 21, namespace)
        config = namespace["grid_scan"].single_configs[0]
        assert config.algorithms[algorithm].algorithm_name == algorithm
        assert (namespace["coord_root"] / "obi_one_coordinate.json").is_file()

    @pytest.mark.parametrize("name", [LOCAL_NOTEBOOK, BENCHMARK_NOTEBOOK])
    def test_notebooks_do_not_delete_existing_files(self, name):
        for cell in notebook_cells(name):
            if cell["cell_type"] != "code":
                continue
            tree = ast.parse("".join(cell["source"]))
            assert not any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"rmtree", "unlink"}
                for node in ast.walk(tree)
            )

    def test_brian2_uses_simulation_config(self, tmp_path, monkeypatch):
        run = Mock()
        monkeypatch.setattr(subprocess, "run", run)
        namespace: dict[str, Any] = {
            "Path": Path,
            "sys": sys,
            "output_root": tmp_path,
            "brian2_result": tmp_path / "export_brian2",
        }
        run_cell(LOCAL_NOTEBOOK, 32, namespace)
        args, kwargs = run.call_args
        assert "--simulation-config" in args[0]
        assert "--circuit-config" not in args[0]
        assert kwargs["check"] is True

    def test_optional_brian2_simulation_can_be_skipped(self, tmp_path, monkeypatch):
        run = Mock()
        monkeypatch.setattr(subprocess, "run", run)
        run_cell(
            LOCAL_NOTEBOOK,
            32,
            {"output_root": tmp_path, "brian2_result": None},
        )
        run.assert_not_called()

    @pytest.mark.parametrize("simulator", ["Brian2", "NEST"])
    def test_plots_with_only_one_simulator(self, simulator, tmp_path):
        matplotlib = pytest.importorskip("matplotlib")
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # ruff: ignore[import-outside-top-level]

        directory = tmp_path / f"{simulator.lower()}_simulation_results"
        directory.mkdir()
        results = {
            "tstop": 500.0,
            "populations": {
                "neurons": {
                    "n_nodes": 1,
                    "n_spikes": 1,
                    "spike_times": [100.0],
                    "spike_senders": [0],
                    "voltage_traces": {},
                }
            },
        }
        (directory / f"{simulator.lower()}_results.json").write_text(json.dumps(results))
        namespace: dict[str, Any] = {
            "json": json,
            "output_root": tmp_path,
            "brian2_results_dir": tmp_path / "brian2_simulation_results",
        }
        try:
            run_cell(LOCAL_NOTEBOOK, 37, namespace)
        finally:
            plt.close("all")
        assert set(namespace["sim_results"]) == {simulator}
        assert (tmp_path / "voltage_traces_comparison.png").is_file()
        assert (tmp_path / "spike_raster_comparison.png").is_file()
