from obi_one.scientific.tasks.generate_simulations.config.base import (
    SimulationScanConfig,
    SimulationSingleConfigMixin,
)


class NeuronSimulationScanConfig(SimulationScanConfig):
    """Abstract base class for neuron-based simulation scan configurations."""


class NeuronSimulationSingleConfig(SimulationSingleConfigMixin):
    """Mixin for neuron-based single simulation configurations."""
