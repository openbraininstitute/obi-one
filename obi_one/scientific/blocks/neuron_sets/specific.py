import contextlib
import logging
from typing import Annotated, ClassVar

import typing_extensions
from pydantic import Field

from obi_one.scientific.blocks.neuron_sets.base import AbstractNeuronSet
from obi_one.scientific.library.circuit import Circuit

L = logging.getLogger("obi-one")
_NBS1_VPM_NODE_POP = "VPM"
_NBS1_POM_NODE_POP = "POm"
_RCA1_CA3_NODE_POP = "CA3_projections"

_ALL_NODE_SET = "All"
_EXCITATORY_NODE_SET = "Excitatory"
_INHIBITORY_NODE_SET = "Inhibitory"

CircuitNode = Annotated[str, Field(min_length=1)]
NodeSetType = CircuitNode | list[CircuitNode]

with contextlib.suppress(ImportError):  # Try to import connalysis
    pass


class AllNeurons(AbstractNeuronSet):
    """All biophysical neurons."""

    title: ClassVar[str] = "All Neurons"

    @staticmethod
    def check_node_set(circuit: Circuit, _population: str) -> None:
        if _ALL_NODE_SET not in circuit.node_sets:
            msg = f"Node set '{_ALL_NODE_SET}' not found in circuit '{circuit}'!"
            raise ValueError(msg)

    def _get_expression(self, circuit: Circuit, population: str) -> list:
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_node_set(circuit, population)
        return [_ALL_NODE_SET]


class ExcitatoryNeurons(AbstractNeuronSet):
    """All biophysical excitatory neurons."""

    title: ClassVar[str] = "All Excitatory Neurons"

    @staticmethod
    def check_node_set(circuit: Circuit, _population: str) -> None:
        if _EXCITATORY_NODE_SET not in circuit.node_sets:
            msg = f"Node set '{_EXCITATORY_NODE_SET}' not found in circuit '{circuit}'!"
            raise ValueError(msg)

    def _get_expression(self, circuit: Circuit, population: str) -> list:
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_node_set(circuit, population)
        return [_EXCITATORY_NODE_SET]


class InhibitoryNeurons(AbstractNeuronSet):
    """All biophysical inhibitory neurons."""

    title: ClassVar[str] = "All Inhibitory Neurons"

    @staticmethod
    def check_node_set(circuit: Circuit, _population: str) -> None:
        if _INHIBITORY_NODE_SET not in circuit.node_sets:
            msg = f"Node set '{_INHIBITORY_NODE_SET}' not found in circuit '{circuit}'!"
            raise ValueError(msg)

    def _get_expression(self, circuit: Circuit, population: str) -> list:
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_node_set(circuit, population)
        return [_INHIBITORY_NODE_SET]


class nbS1VPMInputs(AbstractNeuronSet):  # noqa: N801
    """Virtual neurons projecting from the VPM thalamic nucleus.

    Specifically, virtual neurons projecting from the VPM thalamic nucleus to biophysical
    cortical neurons in the nbS1 model.
    """

    title: ClassVar[str] = "Demo: nbS1 VPM Inputs"

    @typing_extensions.override
    def _population(self, _population: str | None = None) -> str:
        # Ignore default node population name. This is always VPM.
        return _NBS1_VPM_NODE_POP

    @typing_extensions.override
    def _get_expression(self, _circuit: Circuit, _population: str) -> dict:
        return {"population": _NBS1_VPM_NODE_POP}


class nbS1POmInputs(AbstractNeuronSet):  # noqa: N801
    """Virtual neurons projecting from the POm thalamic nucleus.

    Specifically, virtual neurons projecting from the POm thalamic nucleus to biophysical
    cortical neurons in the nbS1 model.
    """

    title: ClassVar[str] = "Demo: nbS1 POm Inputs"

    @typing_extensions.override
    def _population(self, _population: str | None = None) -> str:
        # Ignore default node population name. This is always POm.
        return _NBS1_POM_NODE_POP

    @typing_extensions.override
    def _get_expression(self, _circuit: Circuit, _population: str) -> dict:
        return {"population": _NBS1_POM_NODE_POP}


class rCA1CA3Inputs(AbstractNeuronSet):  # noqa: N801
    """Virtual neurons projecting from CA3 to CA1.

    Specifically, virtual neurons projecting from the CA3 region to biophysical CA1 neurons
    in the rCA1 model.
    """

    title: ClassVar[str] = "Demo: rCA1 CA3 Inputs"

    @typing_extensions.override
    def _population(self, _population: str | None = None) -> str:
        # Ignore default node population name. This is always CA3_projections.
        return _RCA1_CA3_NODE_POP

    @typing_extensions.override
    def _get_expression(self, _circuit: Circuit, _population: str) -> dict:
        return {"population": _RCA1_CA3_NODE_POP}
