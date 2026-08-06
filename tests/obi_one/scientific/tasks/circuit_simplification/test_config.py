"""Config validation tests for circuit simplification."""

import pytest

from obi_one.core.info import Info
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.tasks.circuit_simplification.task import (
    CircuitSimplificationScanConfig,
)


class TestSimplificationConfig:
    """Tests for the Simplification block configuration."""

    def test_default_config(self):
        """Test default config creation."""
        s = CircuitSimplificationScanConfig.Simplification()
        assert s.algorithms == ["single_compartment"]

    def test_algorithm_validation_rejects_unknown(self):
        """Test that unknown algorithms are rejected (Literal type fires first)."""
        with pytest.raises(ValueError, match="Input should be"):
            CircuitSimplificationScanConfig.Simplification(algorithms=["nonexistent_algo"])

    def test_algorithm_validation_accepts_known(self):
        """Test that known algorithms are accepted."""
        s = CircuitSimplificationScanConfig.Simplification(
            algorithms=["single_compartment", "lif_nest"]
        )
        assert "single_compartment" in s.algorithms
        assert "lif_nest" in s.algorithms

    def test_scan_config_creation(self):
        """Test creating a ScanConfig with required fields.

        Note: CircuitSimplificationSingleConfig cannot be directly instantiated
        because ``algorithms`` is a list field, which SingleConfigMixin
        prohibits. SingleConfigs are created by the scan expansion process.
        """
        cfg = CircuitSimplificationScanConfig(
            info=Info(campaign_name="test", campaign_description="test campaign"),
            initialize=CircuitSimplificationScanConfig.Initialize(
                circuit=CircuitFromID(id_str="test-circuit-id")
            ),
            simplification=CircuitSimplificationScanConfig.Simplification(
                algorithms=["single_compartment"]
            ),
        )
        assert cfg.simplification.algorithms == ["single_compartment"]
