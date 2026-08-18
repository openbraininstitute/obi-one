"""Task execution tests for circuit simplification.

Tests use mocked SimplificationPipeline (autospec=True) to avoid
heavy NEURON dependencies and verify the task's orchestration logic.
"""

import inspect
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from entitysdk.types import DerivationType
from sonata_simplify.pipeline import SimplificationPipeline

from app.mappings import TASK_DEFINITIONS
from app.services.resource_estimation.circuit_simplification import (
    FILTER_ALGORITHMS,
    FILTER_WORK_UNITS_PER_CORE,
    POINT_NEURON_WORK_UNITS_PER_CORE,
    _get_required_cpu_memory_combo,
)
from app.services.task import estimate_task_resources
from app.types import TaskType
from obi_one.core.info import Info
from obi_one.scientific.blocks.simplification_algorithms import (
    ALGORITHM_BLOCK_CLASSES,
    SingleCompartmentAlgorithm,
)
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.tasks.circuit_simplification.task import (
    ALGORITHM_EXPORT_MAP,
    CircuitSimplificationScanConfig,
    CircuitSimplificationSingleConfig,
    CircuitSimplificationTask,
)
from obi_one.types import SimulationBackend


class TestInputEntities:
    """Tests for resolving input circuit entities."""

    def test_input_entities_from_circuit_id(self):
        """A CircuitFromID input should resolve to one entity."""
        circuit_ref = CircuitFromID(id_str="test-circuit-id")
        config = CircuitSimplificationScanConfig.model_construct(
            initialize=CircuitSimplificationScanConfig.Initialize.model_construct(
                circuit=circuit_ref,
            )
        )
        entity = MagicMock()

        with patch.object(CircuitFromID, "entity", return_value=entity) as entity_mock:
            result = config.input_entities(db_client=MagicMock())

        assert result == [entity]
        entity_mock.assert_called_once()

    def test_input_entities_from_circuit_id_list(self):
        """A list of CircuitFromID inputs should resolve every entity."""
        circuit_refs = [
            CircuitFromID(id_str="first-circuit-id"),
            CircuitFromID(id_str="second-circuit-id"),
        ]
        config = CircuitSimplificationScanConfig.model_construct(
            initialize=CircuitSimplificationScanConfig.Initialize.model_construct(
                circuit=circuit_refs,
            )
        )
        entities = [MagicMock(), MagicMock()]

        with patch.object(CircuitFromID, "entity", side_effect=entities) as entity_mock:
            result = config.input_entities(db_client=MagicMock())

        assert result == entities
        assert entity_mock.call_count == 2


class TestSimplificationBlock:
    """Tests for the circuit simplification algorithm block dictionary."""

    def test_algorithms_field_exists(self):
        """The scan config should expose an algorithms block dictionary."""
        fields = CircuitSimplificationScanConfig.model_fields
        assert "algorithms" in fields

    def test_algorithms_defaults_to_single_compartment(self):
        """The default algorithm selection should contain single_compartment."""
        config = CircuitSimplificationScanConfig.empty_config()
        assert list(config.algorithms) == ["single_compartment"]
        assert isinstance(config.algorithms["single_compartment"], SingleCompartmentAlgorithm)

    def test_algorithms_field_is_a_block_dictionary(self):
        """The algorithms field should use the block_dictionary UI element."""
        field = CircuitSimplificationScanConfig.model_fields["algorithms"]
        assert field.json_schema_extra["ui_element"] == "block_dictionary"


class TestTaskDefinitionsEntry:
    """Test that circuit_simplification is in TASK_DEFINITIONS (P0)."""

    def test_task_type_in_definitions(self):
        """circuit_simplification should be in TASK_DEFINITIONS."""
        assert TaskType.circuit_simplification in TASK_DEFINITIONS

    def test_task_definition_has_resources(self):
        """The TASK_DEFINITIONS entry should have resources."""
        td = TASK_DEFINITIONS[TaskType.circuit_simplification]
        assert td.resources is not None
        assert td.resources.cores >= 1


class TestResourceEstimatorDispatch:
    """Test that circuit_simplification has a resource estimator dispatch arm (C8)."""

    def test_dispatch_arm_exists(self):
        """estimate_task_resources should dispatch circuit_simplification."""
        source = inspect.getsource(estimate_task_resources)
        assert "circuit_simplification" in source


class TestCpuMemoryCombo:
    """Tests for F6: _get_required_cpu_memory_combo must satisfy both cores AND memory."""

    def test_returns_preset_with_enough_cores(self):
        """Should return a preset with at least the requested core count."""

        ncpu, mem = _get_required_cpu_memory_combo(min_cores=8, mem_gb_required=16.0)
        assert ncpu >= 8
        assert mem >= 16

    def test_does_not_underallocate_cores(self):
        """Should not return 1 CPU when 8 are required, even if memory is small."""

        # Small memory need but large compute need
        ncpu, _mem = _get_required_cpu_memory_combo(min_cores=8, mem_gb_required=2.0)
        assert ncpu >= 8, f"Expected >=8 cores, got {ncpu}"

    def test_returns_smallest_satisfying_preset(self):
        """Should return the smallest preset that satisfies both constraints."""

        ncpu, mem = _get_required_cpu_memory_combo(min_cores=2, mem_gb_required=4.0)
        assert ncpu == 2
        assert mem == 4

    def test_raises_when_no_preset_satisfies(self):
        """Should raise when no preset can satisfy the requirements."""

        with pytest.raises(ValueError, match="No CPU/memory combination"):
            _get_required_cpu_memory_combo(min_cores=32, mem_gb_required=200.0)


class TestAlgorithmAwareSizing:
    """Tests for F6: estimator should account for algorithm type."""

    def test_filter_algorithm_constant_exists(self):
        """FILTER_ALGORITHMS should contain single_compartment."""

        assert "single_compartment" in FILTER_ALGORITHMS

    def test_point_neuron_constants_exist(self):
        """Point-neuron calibration constants should exist and be larger than filter ones."""

        assert POINT_NEURON_WORK_UNITS_PER_CORE > FILTER_WORK_UNITS_PER_CORE


class TestApiCompatibility:
    """Verify sonata_simplify API compatibility (autospec guard)."""

    def test_pipeline_accepts_simulation_config(self):
        """SimplificationPipeline should accept simulation_config kwarg."""
        sig = inspect.signature(SimplificationPipeline.__init__)
        assert "simulation_config" in sig.parameters
        assert "simplification_mode" in sig.parameters

    def test_build_simulation_config_exists(self):
        """CircuitSimplificationTask should have _build_simulation_config."""
        assert hasattr(CircuitSimplificationTask, "_build_simulation_config")

    def test_algorithm_export_map_single_compartment_no_export(self):
        """single_compartment should map to no exporter (SONATA/NEURON only)."""
        base, exporter = ALGORITHM_EXPORT_MAP["single_compartment"]
        assert base == "single_compartment"
        assert exporter is None

    def test_algorithm_export_map_nest_algorithms(self):
        """Point-neuron algorithms with _nest suffix should map to NEST exporters."""
        for name, (base, exporter) in ALGORITHM_EXPORT_MAP.items():
            if name.endswith("_nest"):
                assert exporter is not None
                assert exporter.startswith("nest:"), f"{name} → {exporter}"
                assert base in name

    def test_algorithm_export_map_brian2_only_adex(self):
        """Brian2 export should only be available for AdEx."""
        brian2_entries = {k for k, v in ALGORITHM_EXPORT_MAP.items() if v[1] and "brian2" in v[1]}
        assert brian2_entries == {"adex_brian2"}


class TestTargetNeuronSetField:
    """Tests for the target_neuron_set field in Initialize."""

    def test_target_neuron_set_field_exists(self):
        """Initialize block should have a target_neuron_set field."""
        fields = CircuitSimplificationScanConfig.Initialize.model_fields
        assert "target_neuron_set" in fields

    def test_target_neuron_set_defaults_to_none(self):
        """target_neuron_set should default to None (AllBiophysicalNeurons at execution)."""
        init = CircuitSimplificationScanConfig.Initialize(
            circuit=CircuitFromID(id_str="test-circuit-id"),
        )
        assert init.target_neuron_set is None

    def test_default_neuron_set_reference(self):
        """default_neuron_set_reference should return AllBiophysicalNeurons."""
        config = CircuitSimplificationScanConfig(
            info={"campaign_name": "test", "campaign_description": "test"},
            initialize=CircuitSimplificationScanConfig.Initialize(
                circuit=CircuitFromID(id_str="test-circuit-id"),
            ),
            algorithms={"single_compartment": ALGORITHM_BLOCK_CLASSES["single_compartment"]()},
        )
        ref = config.default_neuron_set_reference
        assert ref is not None
        assert ref.block_name == config.default_target_neuron_set_name

    def test_default_target_neuron_set_name(self):
        """default_target_neuron_set_name should be 'Default: All Biophysical Neurons'."""
        assert (
            CircuitSimplificationScanConfig.default_target_neuron_set_name
            == "Default: All Biophysical Neurons"
        )

    def test_build_simulation_config_includes_node_set(self, tmp_path):
        """_build_simulation_config should include node_set and node_sets_file when provided."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        sim_config_path = CircuitSimplificationTask._build_simulation_config(
            "some/circuit_config.json",
            output_dir,
            target_neuron_set_name="MyNodeSet",
            node_sets_file="node_sets.json",
        )
        with Path(sim_config_path).open(encoding="utf-8") as f:
            sim_config = json.load(f)
        assert sim_config["node_set"] == "MyNodeSet"
        assert sim_config["node_sets_file"] == "node_sets.json"

    def test_build_simulation_config_without_node_set(self, tmp_path):
        """_build_simulation_config should not include node_set when None."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        sim_config_path = CircuitSimplificationTask._build_simulation_config(
            "some/circuit_config.json",
            output_dir,
        )
        with Path(sim_config_path).open(encoding="utf-8") as f:
            sim_config = json.load(f)
        assert "node_set" not in sim_config
        assert "node_sets_file" not in sim_config


class TestTaskExecution:
    """F7: Tests that exercise CircuitSimplificationTask.execute() using mock fixtures."""

    @staticmethod
    def _make_config(tmp_path: Path, algorithm: str = "single_compartment"):
        """Build a CircuitSimplificationSingleConfig with one algorithm block."""
        algorithm_block = ALGORITHM_BLOCK_CLASSES[algorithm]()
        config = CircuitSimplificationSingleConfig.model_construct(
            info={"campaign_name": "test", "campaign_description": "test"},
            initialize=CircuitSimplificationScanConfig.Initialize(
                circuit=CircuitFromID(id_str="test-circuit-id"),
            ),
            algorithms={algorithm: algorithm_block},
        )
        config.scan_output_root = tmp_path / "scan_output"
        config.coordinate_output_root = tmp_path / "coord_output"
        config.coordinate_output_root.mkdir(parents=True, exist_ok=True)
        return config

    def test_execute_calls_pipeline_run(
        self,
        fake_simplified_circuit: Path,
        mock_pipeline,
        mock_mechanism_compilation,  # ruff: ignore[unused-method-argument]
        tmp_path: Path,
    ):
        """execute() should construct and run SimplificationPipeline for each algorithm."""

        # Build a single config
        config = self._make_config(tmp_path)

        task = CircuitSimplificationTask(config=config)

        # Mock resolve_circuit to return a fake circuit + entity
        mock_circuit = MagicMock()
        mock_circuit.path = str(fake_simplified_circuit / "circuit_config.json")
        mock_circuit.sonata_circuit = MagicMock()
        mock_entity = MagicMock()
        mock_entity.name = "TestCircuit"
        mock_entity.build_category = "test"
        mock_entity.brain_region = None
        mock_entity.subject = None
        mock_entity.target_simulator = "NEURON"
        mock_entity.experiment_date = None
        mock_entity.license = None
        mock_entity.root_circuit_id = None
        mock_entity.id = "parent-id"

        with (
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.db_sdk.resolve_circuit",
                return_value=(mock_circuit, mock_entity),
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._get_execution_activity",
                return_value=None,
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._update_execution_activity",
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._register_output",
                return_value=MagicMock(id="new-circuit-id"),
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._smoke_check_loadability",
            ),
        ):
            # The task looks for the simplified circuit_config.json in
            # output_dir/algorithm_name/output/circuit_config.json
            # (the sim config sets output_dir to output_dir / "output")
            algo_dir = config.coordinate_output_root / "single_compartment" / "output"
            algo_dir.mkdir(parents=True, exist_ok=True)
            (algo_dir / "circuit_config.json").write_text("{}")

            task.execute(db_client=MagicMock())

        # Pipeline should have been constructed and run_recipe called
        mock_pipeline.assert_called_once()
        mock_pipeline.return_value.run_recipe.assert_called_once()
        sim_config_path = Path(mock_pipeline.call_args.kwargs["simulation_config"])
        sim_config = json.loads(sim_config_path.read_text(encoding="utf-8"))
        assert "node_set" not in sim_config
        assert "node_sets_file" not in sim_config

    def test_execute_registers_only_exported_circuit(
        self,
        mock_pipeline,  # ruff: ignore[unused-method-argument]
        tmp_path: Path,
    ):
        """An exporter algorithm registers only its simulator-specific output."""
        config = self._make_config(tmp_path, algorithm="adex_brian2")
        task = CircuitSimplificationTask(config=config)

        mock_circuit = MagicMock()
        mock_circuit.path = str(tmp_path / "input" / "circuit_config.json")
        mock_entity = MagicMock()
        sonata_output = config.coordinate_output_root / "adex_brian2" / "output"
        sonata_output.mkdir(parents=True, exist_ok=True)
        (sonata_output / "circuit_config.json").write_text("{}")
        export_output = sonata_output / "output_brian2_adex"
        export_output.mkdir()
        export_config = export_output / "circuit_config.json"
        export_config.write_text("{}")
        registered_export = MagicMock(id="brian2-id")
        execution_activity = MagicMock()

        with (
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.db_sdk.resolve_circuit",
                return_value=(mock_circuit, mock_entity),
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._get_execution_activity",
                return_value=execution_activity,
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._update_execution_activity",
            ) as update_activity,
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._register_output",
                return_value=registered_export,
            ) as register_output,
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._resolve_target_neuron_set",
                return_value=None,
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._smoke_check_loadability",
            ),
        ):
            result = task.execute(db_client=MagicMock())

        assert result == "brian2-id"
        register_output.assert_called_once_with(
            db_client=register_output.call_args.kwargs["db_client"],
            circuit_path=export_config,
            algorithm_name="adex_brian2",
            export_suffix="_brian2_adex",
        )
        update_activity.assert_called_once()
        assert update_activity.call_args.kwargs["generated"] == ["brian2-id"]

    def test_execute_fails_when_required_export_output_is_missing(
        self,
        mock_pipeline,  # ruff: ignore[unused-method-argument]
        tmp_path: Path,
        caplog,
    ):
        """An exporter algorithm must not fall back to its intermediate output."""
        config = self._make_config(tmp_path, algorithm="adex_brian2")
        task = CircuitSimplificationTask(config=config)
        mock_circuit = MagicMock()
        mock_circuit.path = str(tmp_path / "input" / "circuit_config.json")
        mock_entity = MagicMock()
        sonata_output = config.coordinate_output_root / "adex_brian2" / "output"
        sonata_output.mkdir(parents=True, exist_ok=True)
        (sonata_output / "circuit_config.json").write_text("{}")

        with (
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.db_sdk.resolve_circuit",
                return_value=(mock_circuit, mock_entity),
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._get_execution_activity",
                return_value=None,
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._register_output",
            ) as register_output,
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._resolve_target_neuron_set",
                return_value=None,
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._smoke_check_loadability",
            ),
            pytest.raises(RuntimeError, match="Expected brian2:adex export"),
        ):
            task.execute(db_client=MagicMock())

        register_output.assert_not_called()
        assert "Expected brian2:adex export" in caplog.text

    def test_execute_skips_missing_output(
        self,
        mock_pipeline,  # ruff: ignore[unused-method-argument]
        mock_mechanism_compilation,  # ruff: ignore[unused-method-argument]
        tmp_path: Path,
    ):
        """execute() should skip algorithms whose output circuit_config.json is missing."""

        config = self._make_config(tmp_path)

        task = CircuitSimplificationTask(config=config)

        mock_circuit = MagicMock()
        mock_circuit.path = str(tmp_path / "circuit_config.json")
        mock_circuit.sonata_circuit = MagicMock()
        mock_entity = MagicMock()

        with (
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.db_sdk.resolve_circuit",
                return_value=(mock_circuit, mock_entity),
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._get_execution_activity",
                return_value=None,
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._resolve_target_neuron_set",
                return_value=None,
            ),
        ):
            # Don't create the output circuit_config.json — pipeline ran but
            # produced no output (simulated failure)
            result = task.execute(db_client=MagicMock())

        # Should return None since no output was found
        assert result is None

    def test_execute_passes_algorithm_to_pipeline(
        self,
        fake_simplified_circuit: Path,
        mock_pipeline,
        tmp_path: Path,
    ):
        """execute() should pass the base algorithm as simplification_mode to the pipeline."""

        config = self._make_config(tmp_path, algorithm="lif_nest")

        task = CircuitSimplificationTask(config=config)

        mock_circuit = MagicMock()
        mock_circuit.path = str(fake_simplified_circuit / "circuit_config.json")
        mock_circuit.sonata_circuit = MagicMock()
        mock_entity = MagicMock()

        with (
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.db_sdk.resolve_circuit",
                return_value=(mock_circuit, mock_entity),
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._get_execution_activity",
                return_value=None,
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._resolve_target_neuron_set",
                return_value="Default: All Biophysical Neurons",
            ),
        ):
            task.execute(db_client=None)

        # Check that the BASE algorithm was passed as simplification_mode
        # (compound name "lif_nest" → base "lif")
        call_kwargs = mock_pipeline.call_args
        assert call_kwargs.kwargs.get("simplification_mode") == "lif"

        # The implicit all-biophysical selection must not be passed to point-
        # neuron modes because sonata_simplify rejects node_set/node_ids there.
        sim_config_path = Path(call_kwargs.kwargs["simulation_config"])
        sim_config = json.loads(sim_config_path.read_text(encoding="utf-8"))
        assert "node_set" not in sim_config
        assert "node_sets_file" not in sim_config

    def test_execute_omits_target_set_for_single_compartment(
        self,
        fake_simplified_circuit: Path,
        mock_pipeline,
        mock_mechanism_compilation,  # ruff: ignore[unused-method-argument]
        tmp_path: Path,
    ):
        """All algorithms currently omit target node-set selection."""
        config = self._make_config(tmp_path, algorithm="single_compartment")
        task = CircuitSimplificationTask(config=config)

        mock_circuit = MagicMock()
        mock_circuit.path = str(fake_simplified_circuit / "circuit_config.json")
        mock_circuit.sonata_circuit = MagicMock()
        mock_entity = MagicMock()

        with (
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.db_sdk.resolve_circuit",
                return_value=(mock_circuit, mock_entity),
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._get_execution_activity",
                return_value=None,
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._resolve_target_neuron_set",
                return_value="Default: All Biophysical Neurons",
            ),
        ):
            task.execute(db_client=None)

        sim_config = json.loads(
            Path(mock_pipeline.call_args.kwargs["simulation_config"]).read_text(encoding="utf-8")
        )
        assert "node_set" not in sim_config
        assert "node_sets_file" not in sim_config

    def test_execute_runs_multiple_algorithm_blocks(
        self,
        fake_simplified_circuit: Path,
        mock_pipeline,
        mock_mechanism_compilation,  # ruff: ignore[unused-method-argument]
        tmp_path: Path,
    ):
        """execute() should run each algorithm block in the selected dictionary."""

        config = self._make_config(tmp_path, algorithm="single_compartment")
        for algorithm in ALGORITHM_BLOCK_CLASSES:
            if algorithm != "single_compartment":
                config.algorithms[algorithm] = ALGORITHM_BLOCK_CLASSES[algorithm]()
        task = CircuitSimplificationTask(config=config)

        mock_circuit = MagicMock()
        mock_circuit.path = str(fake_simplified_circuit / "circuit_config.json")
        mock_circuit.sonata_circuit = MagicMock()
        mock_entity = MagicMock()

        for algorithm in ALGORITHM_BLOCK_CLASSES:
            output = config.coordinate_output_root / algorithm / "output"
            output.mkdir(parents=True, exist_ok=True)
            (output / "circuit_config.json").write_text("{}")
            _, exporter_name = ALGORITHM_EXPORT_MAP[algorithm]
            if exporter_name:
                export_suffix = exporter_name.replace(":", "_")
                export_config = output / f"output_{export_suffix}" / "circuit_config.json"
                export_config.parent.mkdir(parents=True, exist_ok=True)
                export_config.write_text("{}")

        with (
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.db_sdk.resolve_circuit",
                return_value=(mock_circuit, mock_entity),
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._get_execution_activity",
                return_value=None,
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._resolve_target_neuron_set",
                return_value=None,
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._smoke_check_loadability",
            ),
        ):
            task.execute(db_client=None)

        assert mock_pipeline.call_count == len(ALGORITHM_BLOCK_CLASSES)
        for call in mock_pipeline.call_args_list:
            sim_config = json.loads(
                Path(call.kwargs["simulation_config"]).read_text(encoding="utf-8")
            )
            assert "node_set" not in sim_config
            assert "node_sets_file" not in sim_config

    def test_execute_cleans_up_temp_dir(
        self,
        mock_pipeline,  # ruff: ignore[unused-method-argument]
        mock_mechanism_compilation,  # ruff: ignore[unused-method-argument]
        tmp_path: Path,
    ):
        """execute() should clean up the temp directory after completion."""

        config = self._make_config(tmp_path)

        task = CircuitSimplificationTask(config=config)

        mock_circuit = MagicMock()
        mock_circuit.path = str(tmp_path / "circuit_config.json")
        mock_circuit.sonata_circuit = MagicMock()
        mock_entity = MagicMock()

        # Track the temp directory created by tempfile.TemporaryDirectory
        created_dirs: list[Path] = []

        original_temp_dir = tempfile.TemporaryDirectory

        class TrackingTempDir:
            """Wraps tempfile.TemporaryDirectory to capture the directory path."""

            def __init__(self, *args, **kwargs):
                self._inner = original_temp_dir(*args, **kwargs)

            def __enter__(self):
                path = self._inner.__enter__()
                created_dirs.append(Path(path))
                return path

            def __exit__(self, *args):
                return self._inner.__exit__(*args)

        with (
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.tempfile.TemporaryDirectory",
                TrackingTempDir,
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.db_sdk.resolve_circuit",
                return_value=(mock_circuit, mock_entity),
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._get_execution_activity",
                return_value=None,
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._resolve_target_neuron_set",
                return_value=None,
            ),
        ):
            task.execute(db_client=None)

        # Temp dir should be cleaned up (the context manager exited)
        assert len(created_dirs) == 1, "Expected exactly one temp directory to be created"
        assert not created_dirs[0].exists(), f"Temp dir {created_dirs[0]} should be cleaned up"


class TestTaskInternals:
    """Tests for task internals not exercised by the orchestration mocks."""

    @staticmethod
    def _make_task(tmp_path: Path) -> CircuitSimplificationTask:
        config = TestTaskExecution._make_config(tmp_path)
        return CircuitSimplificationTask(config=config)

    def test_resolve_target_neuron_set_writes_generated_file(self, tmp_path: Path):
        """A default neuron-set reference should be materialized and written."""
        task = self._make_task(tmp_path)
        task._circuit = MagicMock()
        block = MagicMock()
        block.has_block_name.return_value = False
        block.block_name = "TestNodeSet"
        target_neuron_set_ref = MagicMock(block=block, block_name="TestNodeSet")

        with (
            patch.object(
                CircuitSimplificationScanConfig,
                "default_neuron_set_reference",
                new_callable=PropertyMock,
                return_value=target_neuron_set_ref,
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.write_circuit_node_set_file"
            ) as write_node_sets,
        ):
            result = task._resolve_target_neuron_set(tmp_path)

        assert result == "TestNodeSet"
        block.set_block_name.assert_called_once_with("TestNodeSet")
        block.add_node_set_definition_to_sonata_circuit.assert_called_once_with(
            task._circuit,
            task._circuit.sonata_circuit,
            force_resolve_ids=True,
        )
        write_node_sets.assert_called_once_with(
            task._circuit.sonata_circuit,
            str(tmp_path),
            file_name="node_sets.json",
            overwrite_if_exists=True,
        )

    def test_resolve_target_neuron_set_returns_none_without_reference(self, tmp_path: Path):
        """A missing configured and default reference should be handled."""
        task = self._make_task(tmp_path)

        with patch.object(
            CircuitSimplificationScanConfig,
            "default_neuron_set_reference",
            new_callable=PropertyMock,
            return_value=None,
        ):
            assert task._resolve_target_neuron_set(tmp_path) is None

    def test_read_target_simulator_from_config(self, tmp_path: Path):
        """Known target-simulator values should be returned from the config."""
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps({"target_simulator": "Brian2"}))

        result = CircuitSimplificationTask._read_target_simulator(config_path)

        assert result.name == "Brian2"

    def test_read_target_simulator_defaults_when_missing(self, tmp_path: Path):
        """A missing target simulator should default to NEURON."""
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text("{}")

        result = CircuitSimplificationTask._read_target_simulator(config_path)

        assert result.name == "NEURON"

    def test_read_target_simulator_defaults_when_invalid(self, tmp_path: Path):
        """An invalid target simulator should warn and default to NEURON."""
        config_path = tmp_path / "circuit_config.json"
        config_path.write_text(json.dumps({"target_simulator": "Unknown"}))

        result = CircuitSimplificationTask._read_target_simulator(config_path)

        assert result.name == "NEURON"

    def test_register_output_passes_metadata_to_registration(self, tmp_path: Path):
        """Output registration should pass the exporter simulator and provenance."""
        task = self._make_task(tmp_path)
        task.config.info = Info(
            campaign_name="test",
            campaign_description="test description",
        )
        parent = MagicMock()
        parent.name = "ParentCircuit"
        parent.build_category = "test"
        parent.brain_region = None
        parent.subject = None
        parent.experiment_date = None
        parent.license = None
        parent.root_circuit_id = None
        parent.id = "parent-id"
        task._circuit_entity = parent

        circuit_path = tmp_path / "circuit_config.json"
        circuit_path.write_text(json.dumps({"target_simulator": "Brian2"}))
        registered = MagicMock(id="registered-id")

        with patch(
            "obi_one.scientific.tasks.circuit_simplification.task.circuit_registration.register_circuit",
            return_value=registered,
        ) as register_circuit:
            result = task._register_output(
                db_client=MagicMock(),
                circuit_path=circuit_path,
                algorithm_name="adex_brian2",
                export_suffix="_brian2_adex",
            )

        assert result is registered
        kwargs = register_circuit.call_args.kwargs
        assert kwargs["name"] == "ParentCircuit__test__adex_brian2_brian2_adex"
        assert kwargs["target_simulator"].name == "Brian2"
        assert kwargs["parent"] is parent
        assert kwargs["derivation_type"] == DerivationType.circuit_simplification


class TestMechanismBackendSelection:
    """Tests for the shutil.which-based simulation backend selection."""

    def test_uses_neurodamus_when_compile_mods_available(
        self,
        fake_simplified_circuit: Path,
        mock_pipeline,  # ruff: ignore[unused-method-argument]
        tmp_path: Path,
    ):
        """execute() should use neurodamus backend when neurodamus-compile-mods is on PATH."""
        config = TestTaskExecution._make_config(tmp_path)
        task = CircuitSimplificationTask(config=config)

        mock_circuit = MagicMock()
        mock_circuit.path = str(fake_simplified_circuit / "circuit_config.json")
        mock_circuit.sonata_circuit = MagicMock()
        mock_entity = MagicMock()

        algo_dir = config.coordinate_output_root / "single_compartment" / "output"
        algo_dir.mkdir(parents=True, exist_ok=True)
        (algo_dir / "circuit_config.json").write_text("{}")

        with (
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.db_sdk.resolve_circuit",
                return_value=(mock_circuit, mock_entity),
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._get_execution_activity",
                return_value=None,
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._resolve_target_neuron_set",
                return_value=None,
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._smoke_check_loadability",
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._register_output",
                return_value=MagicMock(id="new-circuit-id"),
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.process.get_mechanisms_dirs",
                return_value=[Path("/fake/mod")],
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.process.compile_mechanisms",
            ) as mock_compile,
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.shutil.which",
                return_value="/usr/bin/neurodamus-compile-mods",
            ),
        ):
            task.execute(db_client=MagicMock())

        mock_compile.assert_called_once()
        assert mock_compile.call_args.kwargs["simulation_backend"] == SimulationBackend.neurodamus

    def test_uses_bluecellulab_when_compile_mods_missing(
        self,
        fake_simplified_circuit: Path,
        mock_pipeline,  # ruff: ignore[unused-method-argument]
        tmp_path: Path,
    ):
        """execute() should fall back to bluecellulab when neurodamus-compile-mods is absent."""
        config = TestTaskExecution._make_config(tmp_path)
        task = CircuitSimplificationTask(config=config)

        mock_circuit = MagicMock()
        mock_circuit.path = str(fake_simplified_circuit / "circuit_config.json")
        mock_circuit.sonata_circuit = MagicMock()
        mock_entity = MagicMock()

        algo_dir = config.coordinate_output_root / "single_compartment" / "output"
        algo_dir.mkdir(parents=True, exist_ok=True)
        (algo_dir / "circuit_config.json").write_text("{}")

        with (
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.db_sdk.resolve_circuit",
                return_value=(mock_circuit, mock_entity),
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._get_execution_activity",
                return_value=None,
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._resolve_target_neuron_set",
                return_value=None,
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._smoke_check_loadability",
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._register_output",
                return_value=MagicMock(id="new-circuit-id"),
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.process.get_mechanisms_dirs",
                return_value=[Path("/fake/mod")],
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.process.compile_mechanisms",
            ) as mock_compile,
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.shutil.which",
                return_value=None,
            ),
        ):
            task.execute(db_client=MagicMock())

        mock_compile.assert_called_once()
        assert mock_compile.call_args.kwargs["simulation_backend"] == SimulationBackend.bluecellulab


class TestSmokeCheckLoadability:
    """F11: Tests for the loadability smoke check."""

    def test_smoke_check_raises_on_load_failure(self, tmp_path: Path):
        """_smoke_check_loadability should raise RuntimeError when BluePySnap fails."""
        # Create a malformed circuit_config.json
        bad_config = tmp_path / "circuit_config.json"
        bad_config.write_text('{"version": "2.3", "networks": {"nodes": [], "edges": []}}')

        with (
            patch("bluepysnap.Circuit", side_effect=Exception("malformed circuit")),
            pytest.raises(RuntimeError, match="Smoke check FAILED"),
        ):
            CircuitSimplificationTask._smoke_check_loadability(bad_config, "test_algo")

    def test_smoke_check_passes_on_valid_circuit(self, tmp_path: Path):
        """_smoke_check_loadability should not raise when BluePySnap loads successfully."""
        valid_config = tmp_path / "circuit_config.json"
        valid_config.write_text('{"version": "2.3", "networks": {"nodes": [], "edges": []}}')

        with patch("bluepysnap.Circuit"):
            # Should not raise
            CircuitSimplificationTask._smoke_check_loadability(valid_config, "test_algo")

    def test_execute_fails_on_unloadable_circuit(
        self,
        fake_simplified_circuit: Path,
        mock_pipeline,  # ruff: ignore[unused-method-argument]
        mock_mechanism_compilation,  # ruff: ignore[unused-method-argument]
        tmp_path: Path,
    ):
        """execute() should raise when smoke check fails, not register the circuit."""
        config = TestTaskExecution._make_config(tmp_path)

        task = CircuitSimplificationTask(config=config)

        mock_circuit = MagicMock()
        mock_circuit.path = str(fake_simplified_circuit / "circuit_config.json")
        mock_circuit.sonata_circuit = MagicMock()
        mock_entity = MagicMock()

        # Create the output circuit_config.json so the existence check passes.
        # The task looks in algo_dir/output/circuit_config.json (the sim config
        # sets output_dir to output_dir / "output").
        algo_dir = config.coordinate_output_root / "single_compartment" / "output"
        algo_dir.mkdir(parents=True, exist_ok=True)
        (algo_dir / "circuit_config.json").write_text("{}")

        with (
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.db_sdk.resolve_circuit",
                return_value=(mock_circuit, mock_entity),
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._get_execution_activity",
                return_value=None,
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._resolve_target_neuron_set",
                return_value=None,
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._register_output",
                return_value=MagicMock(id="new-circuit-id"),
            ),
            patch(
                "obi_one.scientific.tasks.circuit_simplification.task.CircuitSimplificationTask._smoke_check_loadability",
                side_effect=RuntimeError("Smoke check FAILED"),
            ),
            pytest.raises(RuntimeError, match="Smoke check FAILED"),
        ):
            task.execute(db_client=MagicMock())
