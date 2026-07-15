import abc
from typing import ClassVar

from libsonata import SimulatorType
from pydantic import PositiveFloat

from obi_one.core.exception import OBIONEError
from obi_one.scientific.blocks.neuron_sets.predefined import PointPopulationPredefinedNeuronSet
from obi_one.scientific.blocks.neuron_sets.specific import AllPointNeurons
from obi_one.scientific.library.circuit import Circuit
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

    # The simulation runs every point neuron by default, so its default neuron set is named for
    # what it contains -- an untargeted simulation runs the whole circuit.
    default_node_set_name: ClassVar[str] = "Default: All Point Neurons"
    default_neuron_set_type: ClassVar[type[AllPointNeurons]] = AllPointNeurons

    # A stimulus left without a target instead drives the `sugar` node set -- the gustatory
    # receptor neurons the Shiu et al. (2024) FlyWire model stimulates -- rather than the whole
    # circuit. This is a separate, smaller default so the two never conflict.
    default_stimulus_node_set_name: ClassVar[str] = "Default: Sugar gustatory receptor neurons"
    default_stimulus_node_set: ClassVar[str] = "sugar"

    @property
    def default_neuron_set_reference(self) -> PointNeuronSetReference:
        """Returns the default neuron set reference for the simulation (all point neurons)."""
        ref = PointNeuronSetReference(
            block_dict_name="neuron_sets", block_name=self.default_node_set_name
        )
        ref.block = self.default_neuron_set_type()
        ref.block.set_block_name(self.default_node_set_name)
        return ref

    def default_stimulus_neuron_set_reference(self, circuit: Circuit) -> PointNeuronSetReference:
        """Returns the default neuron set reference for an untargeted stimulus (the `sugar` set).

        It names an existing node set, so unlike the simulation default it has to resolve the
        circuit's point population.
        """
        ref = PointNeuronSetReference(
            block_dict_name="neuron_sets", block_name=self.default_stimulus_node_set_name
        )
        ref.block = PointPopulationPredefinedNeuronSet(
            node_set=self.default_stimulus_node_set,
            population=self._point_population(circuit),
        )
        ref.block.set_block_name(self.default_stimulus_node_set_name)
        return ref

    @staticmethod
    def _point_population(circuit: Circuit) -> str:
        """Return the circuit's single point node population."""
        populations = Circuit.get_node_population_names(
            circuit.sonata_circuit, incl_virtual=False, incl_biophysical=False
        )
        if len(populations) != 1:
            msg = (
                f"A Brian2 simulation needs exactly one point node population; "
                f"circuit '{circuit.name}' has {len(populations)}: {populations}."
            )
            raise OBIONEError(msg)
        return populations[0]

    class Initialize(BaseSimulationScanConfig.Initialize):
        pass
