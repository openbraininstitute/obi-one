import abc
import logging
from typing import ClassVar

from obi_one.scientific.blocks.neuron_sets_2.base import NeuronSet, NeuronSetPopulationType
from obi_one.scientific.library.circuit import Circuit

L = logging.getLogger(__name__)


class AllNeuronsBase(NeuronSet, abc.ABC):
    """Abstract base class for neuron sets selecting all neurons of a given type."""

    def get_neuron_ids(self, circuit: Circuit) -> dict[str, list[int]]:
        """Returns all neuron IDs per population."""
        ids_dict = {}
        for npop in self.get_populations(circuit):
            ids_dict[npop] = circuit.sonata_circuit.nodes[npop].ids().tolist()
        return ids_dict

    def get_node_set_definition(
        self, circuit: Circuit, *, force_resolve_ids: bool = False
    ) -> tuple[dict | list, dict]:
        """Returns node set definition combining all matching populations."""
        if not self.has_block_name():
            msg = "Block name must be set."
            raise ValueError(msg)
        if force_resolve_ids:
            ids_per_npop = self.get_neuron_ids(circuit)
            prefix = f"__{self.__class__.__name__}__{self.block_name}"
            return NeuronSet.ids_to_node_set_definition(
                ids_per_npop, prefix=prefix, simplified=True
            )
        # Symbolic: list all population node sets
        populations = self.get_populations(circuit)
        if len(populations) == 1:
            return {"population": populations[0]}, {}
        expression = []
        combined = {}
        for idx, npop in enumerate(populations):
            key = f"__{self.__class__.__name__}__{self.block_name}__{idx}__"
            combined[key] = {"population": npop}
            expression.append(key)
        return expression, combined


class AllNeurons(AllNeuronsBase):
    """All neurons across all populations."""

    title: ClassVar[str] = "All Neurons"
    description: ClassVar[str] = "All neurons from all node populations."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = NeuronSetPopulationType.ANY

    def get_populations(self, circuit: Circuit) -> list[str]:  # noqa: PLR6301
        """Returns all population names in the circuit."""
        return Circuit.get_node_population_names(
            circuit.sonata_circuit,
            incl_biophysical=True,
            incl_point=True,
            incl_virtual=True,
        )


class AllBiophysicalNeurons(AllNeuronsBase):
    """All biophysical neurons across all biophysical populations."""

    title: ClassVar[str] = "All Biophysical Neurons"
    description: ClassVar[str] = "All neurons from all biophysical node populations."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = (
        NeuronSetPopulationType.BIOPHYSICAL
    )

    def get_populations(self, circuit: Circuit) -> list[str]:  # noqa: PLR6301
        """Returns all biophysical population names."""
        return Circuit.get_node_population_names(
            circuit.sonata_circuit,
            incl_biophysical=True,
            incl_point=False,
            incl_virtual=False,
        )


class AllPointNeurons(AllNeuronsBase):
    """All point neurons across all point neuron populations."""

    title: ClassVar[str] = "All Point Neurons"
    description: ClassVar[str] = "All neurons from all point neuron populations."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = NeuronSetPopulationType.POINT

    def get_populations(self, circuit: Circuit) -> list[str]:  # noqa: PLR6301
        """Returns all point neuron population names."""
        return Circuit.get_node_population_names(
            circuit.sonata_circuit,
            incl_biophysical=False,
            incl_point=True,
            incl_virtual=False,
        )


class AllVirtualNeurons(AllNeuronsBase):
    """All virtual neurons across all virtual populations."""

    title: ClassVar[str] = "All Virtual Neurons"
    description: ClassVar[str] = "All neurons from all virtual node populations."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = NeuronSetPopulationType.VIRTUAL

    def get_populations(self, circuit: Circuit) -> list[str]:  # noqa: PLR6301
        """Returns all virtual population names."""
        return Circuit.get_node_population_names(
            circuit.sonata_circuit,
            incl_biophysical=False,
            incl_point=False,
            incl_virtual=True,
        )


class AllNonVirtualNeurons(AllNeuronsBase):
    """All non-virtual neurons (biophysical + point) across all populations."""

    title: ClassVar[str] = "All Non-Virtual Neurons"
    description: ClassVar[str] = "All neurons from all non-virtual node populations."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = (
        NeuronSetPopulationType.NONVIRTUAL
    )

    def get_populations(self, circuit: Circuit) -> list[str]:  # noqa: PLR6301
        """Returns all non-virtual population names."""
        return Circuit.get_node_population_names(
            circuit.sonata_circuit,
            incl_biophysical=True,
            incl_point=True,
            incl_virtual=False,
        )
