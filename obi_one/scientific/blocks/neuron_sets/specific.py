import abc
import logging
from typing import ClassVar

import typing_extensions

from obi_one.scientific.blocks.neuron_sets.base import NeuronSet, NeuronSetPopulationType
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
        """Returns the SONATA node set definition, optionally forcing to resolve individual IDs.

        Returns a tuple of (expression, combined) where:

        - expression (dict): A single SONATA node set expression. Examples:
            - Symbolic by population: {"population": "pop_name"}
            - Symbolic by properties: {"layer": "6", "synapse_class": "EXC"}
            - Resolved IDs: {"population": "pop_name", "node_id": [1, 2, 3]}

        - expression (list): A compound expression referencing multiple named node sets.
            Example: ["__ClassName__blockname__0__", "__ClassName__blockname__1__"]
            Each name must exist as a key in the combined dict.
            Also used for symbolic references to existing node sets: ["Layer6"]

        - combined (dict): Additional node set definitions needed by a compound expression.
            Example: {"__ClassName__blockname__0__": {"population": "A", "node_id": [...]},
                      "__ClassName__blockname__1__": {"population": "B", "node_id": [...]}}
            Empty ({}) when expression is a single dict.

        Args:
            circuit: The circuit to resolve the node set in.
            force_resolve_ids: If True, always resolve to explicit neuron IDs
                instead of preserving symbolic expressions.
        """
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


"""
Old types: to be deprecated.
"""
_NBS1_VPM_NODE_POP = "VPM"
_NBS1_POM_NODE_POP = "POm"
_RCA1_CA3_NODE_POP = "CA3_projections"

_EXCITATORY_NODE_SET = "Excitatory"
_INHIBITORY_NODE_SET = "Inhibitory"


class ExcitatoryNeurons(NeuronSet):
    """All biophysical excitatory neurons."""

    title: ClassVar[str] = "All Excitatory Neurons"

    @staticmethod
    def check_node_set(circuit: Circuit, _population: str) -> None:
        if _EXCITATORY_NODE_SET not in circuit.node_sets:
            msg = (
                f"Node set '{_EXCITATORY_NODE_SET}' not found in circuit '{circuit.name}'. "
                "Please use a different Neuron Set type "
                "or use a PredefinedNeuronSet with one of the "
                f"available node sets: {', '.join(circuit.node_sets)}"
            )
            raise ValueError(msg)

    def _get_expression(self, circuit: Circuit, population: str) -> list:  # ty:ignore[invalid-method-override]
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_node_set(circuit, population)
        return [_EXCITATORY_NODE_SET]


class InhibitoryNeurons(NeuronSet):
    """All biophysical inhibitory neurons."""

    title: ClassVar[str] = "All Inhibitory Neurons"

    @staticmethod
    def check_node_set(circuit: Circuit, _population: str) -> None:
        if _INHIBITORY_NODE_SET not in circuit.node_sets:
            msg = (
                f"Node set '{_INHIBITORY_NODE_SET}' not found in circuit '{circuit.name}'. "
                "Please use a different Neuron Set type "
                "or use a PredefinedNeuronSet with one of the "
                f"available node sets: {', '.join(circuit.node_sets)}"
            )
            raise ValueError(msg)

    def _get_expression(self, circuit: Circuit, population: str) -> list:  # ty:ignore[invalid-method-override]
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_node_set(circuit, population)
        return [_INHIBITORY_NODE_SET]


class nbS1VPMInputs(NeuronSet):  # noqa: N801
    """Virtual neurons projecting from the VPM thalamic nucleus.

    Specifically, virtual neurons projecting from the VPM thalamic nucleus to biophysical
    cortical neurons in the nbS1 model.
    """

    title: ClassVar[str] = "Demo: nbS1 VPM Inputs"

    @typing_extensions.override
    def _population(self, _population: str | None = None) -> str:  # ty:ignore[invalid-method-override]
        # Ignore default node population name. This is always VPM.
        return _NBS1_VPM_NODE_POP

    @typing_extensions.override
    def _get_expression(self, _circuit: Circuit, _population: str) -> dict:  # ty:ignore[invalid-method-override]
        return {"population": _NBS1_VPM_NODE_POP}


class nbS1POmInputs(NeuronSet):  # noqa: N801
    """Virtual neurons projecting from the POm thalamic nucleus.

    Specifically, virtual neurons projecting from the POm thalamic nucleus to biophysical
    cortical neurons in the nbS1 model.
    """

    title: ClassVar[str] = "Demo: nbS1 POm Inputs"

    @typing_extensions.override
    def _population(self, _population: str | None = None) -> str:  # ty:ignore[invalid-method-override]
        # Ignore default node population name. This is always POm.
        return _NBS1_POM_NODE_POP

    @typing_extensions.override
    def _get_expression(self, _circuit: Circuit, _population: str) -> dict:  # ty:ignore[invalid-method-override]
        return {"population": _NBS1_POM_NODE_POP}


class rCA1CA3Inputs(NeuronSet):  # noqa: N801
    """Virtual neurons projecting from CA3 to CA1.

    Specifically, virtual neurons projecting from the CA3 region to biophysical CA1 neurons
    in the rCA1 model.
    """

    title: ClassVar[str] = "Demo: rCA1 CA3 Inputs"

    @typing_extensions.override
    def _population(self, _population: str | None = None) -> str:  # ty:ignore[invalid-method-override]
        # Ignore default node population name. This is always CA3_projections.
        return _RCA1_CA3_NODE_POP

    @typing_extensions.override
    def _get_expression(self, _circuit: Circuit, _population: str) -> dict:  # ty:ignore[invalid-method-override]
        return {"population": _RCA1_CA3_NODE_POP}
