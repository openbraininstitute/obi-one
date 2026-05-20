import logging

from obi_one.scientific.tasks.generate_simulations.config.circuit import (
    CircuitDiscriminator,
    CircuitScanConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_base import (
    NeuronSimulationScanConfig,
    NeuronSimulationSingleConfig,
)

__all__ = [
    "CircuitDiscriminator",
    "CircuitSimulationScanConfig",
    "CircuitSimulationSingleConfig",
]

L = logging.getLogger(__name__)


class CircuitSimulationScanConfig(CircuitScanConfig, NeuronSimulationScanConfig):
    """CircuitSimulationScanConfig."""


class CircuitSimulationSingleConfig(CircuitSimulationScanConfig, NeuronSimulationSingleConfig):
    """Only allows single values."""
