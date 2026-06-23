import abc
from typing import ClassVar

from libsonata import SimulatorType
from pydantic import PositiveFloat

from obi_one.scientific.blocks.neuron_sets.specific import AllPointNeurons
from obi_one.scientific.library.constants import (
    SIMULATION_TIMESTEP_MILLISECONDS,
)
from obi_one.scientific.tasks.generate_simulations.config.base import (
    BaseSimulationScanConfig,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    PointNeuronSetReference,
)


class Brian2SimulationScanConfig(BaseSimulationScanConfig, abc.ABC):
    """Abstract base class for Brian2-based simulation scan configurations."""

    _target_simulator: ClassVar[SimulatorType] = SimulatorType.Brian2
    _timestep: ClassVar[PositiveFloat] = SIMULATION_TIMESTEP_MILLISECONDS

    # discrepency between name and type here is a short term hack.
    default_node_set_name: ClassVar[str] = "Default: Sugar gustatory receptor neurons"
    default_neuron_set_type: ClassVar[type[AllPointNeurons]] = AllPointNeurons

    @property
    def default_neuron_set_reference(self) -> PointNeuronSetReference:
        """Returns the default neuron set reference for the simulation."""
        default_neuron_set_block_reference = PointNeuronSetReference(
            block_dict_name="neuron_sets", block_name=self.default_node_set_name
        )

        default_neuron_set_block_reference.block = self.default_neuron_set_type()
        default_neuron_set_block_reference.block.set_block_name(self.default_node_set_name)

        return default_neuron_set_block_reference

    class Initialize(BaseSimulationScanConfig.Initialize):
        pass
