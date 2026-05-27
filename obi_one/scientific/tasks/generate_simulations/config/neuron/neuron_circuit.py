import logging

from obi_one.scientific.tasks.generate_simulations.config.circuit import (
    CircuitDiscriminator,
    CircuitSimulationScanConfig,
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


class CircuitSimulationScanConfig(CircuitSimulationScanConfig, NeuronSimulationScanConfig):
    """CircuitSimulationScanConfig."""


class CircuitSimulationSingleConfig(CircuitSimulationScanConfig, NeuronSimulationSingleConfig):
    """Only allows single values."""
