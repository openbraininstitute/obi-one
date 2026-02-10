import logging
from typing import Self

import entitysdk.client
import entitysdk.exception
from entitysdk.models import MEModel
from pydantic import model_validator

from obi_one.core.exception import OBIONEError
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.emodel_parameters import (
    MechanismVariable,
    get_mechanism_variables,
)

L = logging.getLogger(__name__)


def try_get_mechanism_variables(
    db_client: entitysdk.client.Client,
    entity_id: str,
) -> list[MechanismVariable] | None:
    """Try to fetch mechanism variables if entity_id refers to an MEModel.

    Returns None if the entity is not an MEModel or if fetching fails.
    Catches all exceptions so callers can safely treat this as optional data.
    """
    try:
        memodel = db_client.get_entity(entity_id=entity_id, entity_type=MEModel)
    except entitysdk.exception.EntitySDKError:
        return None

    try:
        return get_mechanism_variables(db_client, memodel)
    except Exception:
        L.warning("Failed to fetch mechanism variables for entity %s", entity_id, exc_info=True)
        return None


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
