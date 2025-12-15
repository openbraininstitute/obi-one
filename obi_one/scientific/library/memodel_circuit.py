from typing import Self

from pydantic import model_validator

from obi_one.core.exception import OBIONEError
from obi_one.scientific.library.circuit import Circuit


class MEModelCircuit(Circuit):
    @model_validator(mode="after")
    def confirm_single_neuron_without_synapses(self) -> Self:
        sonata_circuit = self.sonata_circuit
        if len(sonata_circuit.nodes.ids()) != 1:
            msg = "MEModelCircuit must contain exactly one neuron."
            raise OBIONEError(msg)
        if len(sonata_circuit.edges.population_names) != 0:
            msg = "MEModelCircuit must not contain any synapses."
            raise OBIONEError(msg)
        return self


class MEModelWithSynapsesCircuit(Circuit):
    @model_validator(mode="after")
    def confirm_single_neuron(self) -> Self:
        sonata_circuit = self.sonata_circuit
        total_real = 0
        for pop_name in sonata_circuit.nodes.population_names:
            pop = sonata_circuit.nodes[pop_name]
            if pop.type != "virtual":
                n = pop.size
                total_real += n

        if total_real != 1:
            msg = "MEModelWithSynapsesCircuit must contain exactly one neuron."
            raise OBIONEError(msg)
        return self
