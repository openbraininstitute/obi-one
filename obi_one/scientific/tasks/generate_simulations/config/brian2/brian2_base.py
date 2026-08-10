import abc
from typing import ClassVar

from libsonata import SimulatorType
from pydantic import PositiveFloat

from obi_one.scientific.blocks.neuron_sets.specific import AllPointNeurons
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import (
    SIMULATION_TIMESTEP_MILLISECONDS,
)
from obi_one.scientific.tasks.generate_simulations.config.base import (
    BaseSimulationScanConfig,
)


class Brian2SimulationScanConfig(BaseSimulationScanConfig, abc.ABC):
    """Abstract base class for Brian2-based simulation scan configurations."""

    _target_simulator: ClassVar[SimulatorType] = SimulatorType.Brian2
    _timestep: ClassVar[PositiveFloat] = SIMULATION_TIMESTEP_MILLISECONDS

    # The simulation runs every point neuron by default, so its default neuron set is named for
    # what it contains -- an untargeted simulation runs the whole circuit. An untargeted stimulus
    # drives the same set, as in every other family.
    default_node_set_name: ClassVar[str] = "Default: All Point Neurons"
    default_neuron_set_type: ClassVar[type[AllPointNeurons]] = AllPointNeurons

    def check_simulation_target(self, circuit: Circuit) -> None:
        """Nothing to check: a Brian2 simulation can only reference point neuron sets.

        Its neuron set union admits no virtual type, so the base class's check cannot fail here.
        """

    class Initialize(BaseSimulationScanConfig.Initialize):
        pass
