import pytest

from obi_one.core.info import Info
from obi_one.scientific.blocks.simplification_algorithms import (
    AdexNestAlgorithm,
    LifNestAlgorithm,
    SingleCompartmentAlgorithm,
)
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.tasks.circuit_simplification.task import (
    CircuitSimplificationScanConfig,
)


class TestSimplificationConfig:
    """Tests for the circuit simplification algorithm block dictionary."""

    def test_default_config(self):
        """The default config contains the single-compartment algorithm block."""
        config = CircuitSimplificationScanConfig.empty_config()
        assert list(config.algorithms) == ["single_compartment"]
        assert isinstance(config.algorithms["single_compartment"], SingleCompartmentAlgorithm)

    def test_algorithm_validation_rejects_unknown(self):
        """Unknown algorithm block discriminators are rejected."""
        with pytest.raises(ValueError, match="UnknownAlgorithm"):
            CircuitSimplificationScanConfig.model_validate(
                {"algorithms": {"invalid": {"type": "UnknownAlgorithm"}}}
            )

    def test_algorithm_validation_accepts_known(self):
        """Multiple known algorithm blocks can be selected together."""
        config = CircuitSimplificationScanConfig(
            info=Info(campaign_name="test", campaign_description="test"),
            initialize=CircuitSimplificationScanConfig.Initialize(
                circuit=CircuitFromID(id_str="test-circuit-id")
            ),
            algorithms={
                "single_compartment": SingleCompartmentAlgorithm(),
                "lif_nest": LifNestAlgorithm(),
                "adex_nest": AdexNestAlgorithm(),
            },
        )
        assert list(config.algorithms) == ["single_compartment", "lif_nest", "adex_nest"]
        assert all(block.has_block_name() for block in config.algorithms.values())

    def test_scan_config_creation(self):
        """A scan config can contain multiple selected algorithm blocks."""
        config = CircuitSimplificationScanConfig(
            info=Info(campaign_name="test", campaign_description="test campaign"),
            initialize=CircuitSimplificationScanConfig.Initialize(
                circuit=CircuitFromID(id_str="test-circuit-id")
            ),
            algorithms={"single_compartment": SingleCompartmentAlgorithm()},
        )
        assert list(config.algorithms) == ["single_compartment"]
