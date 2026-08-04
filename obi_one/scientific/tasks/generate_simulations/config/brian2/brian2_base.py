import abc
from typing import ClassVar

from libsonata import SimulatorType
from pydantic import PositiveFloat

from obi_one.core.block_reference import BlockReference
from obi_one.core.exception import OBIONEError
from obi_one.scientific.blocks.neuron_sets.predefined import PointPopulationPredefinedNeuronSet
from obi_one.scientific.blocks.neuron_sets.specific import AllPointNeurons
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import (
    SIMULATION_TIMESTEP_MILLISECONDS,
)
from obi_one.scientific.tasks.generate_simulations.config.base import (
    BaseSimulationScanConfig,
    build_neuron_set_reference,
)
from obi_one.scientific.unions_and_references.reference_tags import ReferenceTag


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

    def default_block_references(self, circuit: Circuit) -> dict[str, BlockReference]:
        """As the base, except that an untargeted stimulus drives the `sugar` set.

        That set names an existing node set rather than a whole population, so unlike every other
        default it has to be resolved against the circuit.
        """
        return {
            **super().default_block_references(circuit),
            ReferenceTag.STIMULUS_TARGET: build_neuron_set_reference(
                self.default_stimulus_node_set_name,
                PointPopulationPredefinedNeuronSet(
                    node_set=self.default_stimulus_node_set,
                    population=self._point_population(circuit),
                ),
            ),
        }

    def check_simulation_target(self, circuit: Circuit) -> None:
        """Nothing to check: a Brian2 simulation can only reference point neuron sets.

        Its neuron set union admits no virtual type, so the base class's check cannot fail here.
        """

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
