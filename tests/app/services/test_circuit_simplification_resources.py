"""Service resource-estimation tests for circuit simplification."""

import inspect

import pytest

from app.mappings import TASK_DEFINITIONS
from app.services.resource_estimation.circuit_simplification import (
    FILTER_ALGORITHMS,
    FILTER_WORK_UNITS_PER_CORE,
    POINT_NEURON_WORK_UNITS_PER_CORE,
    REDUCTION_ALGORITHMS,
    _get_required_cpu_memory_combo,
    estimate_resources_for_algorithms,
)
from app.services.task import estimate_task_resources
from app.types import TaskType


class TestTaskDefinitionsEntry:
    """Test that circuit_simplification is in TASK_DEFINITIONS (P0)."""

    def test_task_type_in_definitions(self):
        """circuit_simplification should be in TASK_DEFINITIONS."""
        assert TaskType.circuit_simplification in TASK_DEFINITIONS

    def test_task_definition_has_resources(self):
        """The TASK_DEFINITIONS entry should have resources."""
        td = TASK_DEFINITIONS[TaskType.circuit_simplification]
        resources = getattr(td, "resources", None)
        assert resources is not None
        assert getattr(resources, "cores", 0) >= 1


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


class TestResourceEstimation:
    def test_reduction_algorithms(self):
        assert {"neuron_reduce", "neat_reduction"} == REDUCTION_ALGORITHMS

    def test_reduction_needs_more_cores_than_point_neuron(self):
        point = estimate_resources_for_algorithms(["lif_nest"], nbio=10_000)
        reduction = estimate_resources_for_algorithms(["neat_reduction"], nbio=10_000)
        assert reduction[0] > point[0]
        assert reduction[2] >= point[2]

    def test_time_adds_up_over_algorithms(self):
        _, _, single = estimate_resources_for_algorithms(["neuron_reduce"], nbio=100_000)
        _, _, both = estimate_resources_for_algorithms(
            ["neuron_reduce", "neat_reduction"], nbio=100_000
        )
        assert both > single

    def test_small_circuit_uses_minimum_preset(self):
        assert estimate_resources_for_algorithms(["adex_brian2"], nbio=10) == (1, 4, 1)
