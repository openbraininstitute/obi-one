import pytest

from obi_one.core.info import Info
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.tasks.circuit_simplification.algorithms.models import (
    AdexNestAlgorithm,
    LifNestAlgorithm,
    SingleCompartmentAlgorithm,
)
from obi_one.scientific.tasks.circuit_simplification.config import (
    CircuitSimplificationScanConfig,
)


class TestSimplificationConfig:
    """Tests for the single circuit simplification algorithm block."""

    @staticmethod
    def _config(**kwargs) -> CircuitSimplificationScanConfig:
        return CircuitSimplificationScanConfig(
            info=Info(campaign_name="test", campaign_description="test"),
            initialize=CircuitSimplificationScanConfig.Initialize(
                circuit=CircuitFromID(id_str="test-circuit-id")
            ),
            **kwargs,
        )

    def test_default_config(self):
        """The default config contains the single-compartment algorithm block."""
        config = CircuitSimplificationScanConfig.empty_config()
        assert isinstance(config.algorithm, SingleCompartmentAlgorithm)

    def test_algorithm_validation_rejects_unknown(self):
        """Unknown algorithm block discriminators are rejected."""
        with pytest.raises(ValueError, match="UnknownAlgorithm"):
            CircuitSimplificationScanConfig.model_validate(
                {"algorithm": {"type": "UnknownAlgorithm"}}
            )

    @pytest.mark.parametrize("algorithm_class", [SingleCompartmentAlgorithm, LifNestAlgorithm])
    def test_algorithm_validation_accepts_known(self, algorithm_class):
        """Each known algorithm block can be selected."""
        config = self._config(algorithm=algorithm_class())
        assert isinstance(config.algorithm, algorithm_class)

    def test_algorithm_validation_round_trips_from_dict(self):
        """The discriminator selects the block class when the config is read back."""
        data = self._config(algorithm=AdexNestAlgorithm()).model_dump()
        assert CircuitSimplificationScanConfig.model_validate(data).algorithm == AdexNestAlgorithm()

    def test_several_algorithms_are_rejected(self):
        """A campaign runs one algorithm, so a collection of algorithm blocks is rejected."""
        with pytest.raises(ValueError, match="algorithm"):
            self._config(algorithm=[SingleCompartmentAlgorithm(), LifNestAlgorithm()])
        with pytest.raises(ValueError, match="algorithm"):
            self._config(
                algorithm={
                    "single_compartment": SingleCompartmentAlgorithm(),
                    "lif": LifNestAlgorithm(),
                }
            )

    def test_algorithms_dictionary_is_no_longer_accepted(self):
        """The former ``algorithms`` block dictionary is not a field any more."""
        with pytest.raises(ValueError, match="algorithms"):
            self._config(algorithms={"single_compartment": SingleCompartmentAlgorithm()})

    def test_scan_config_creation(self):
        """A scan config holds the selected algorithm block."""
        config = self._config(algorithm=SingleCompartmentAlgorithm())
        assert isinstance(config.algorithm, SingleCompartmentAlgorithm)
