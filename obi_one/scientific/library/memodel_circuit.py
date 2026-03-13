import json
import logging
from typing import Self

import entitysdk.client
import entitysdk.exception
from entitysdk.models import MEModel
from pydantic import BaseModel, model_validator

from obi_one.core.exception import OBIONEError
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.emodel_parameters import (
    ChannelSectionListMapping,
    MechanismVariable,
    get_mechanism_variables,
)

L = logging.getLogger(__name__)


class MechanismVariableDetail(BaseModel):
    """Details for a single mechanism variable across all section lists."""

    units: str = ""
    limits: list[float] | None = None
    variable_type: str  # "RANGE" or "GLOBAL"
    section_lists_original_values: dict[str, float | None]


class IonChannelVariables(BaseModel):
    """Ion channel entry with its section lists, entity id, and mechanism variables."""

    section_lists: list[str]
    entity_id: str | None = None
    variables: dict[str, MechanismVariableDetail]


def _build_mechanism_variables_by_ion_channel_response(
    variables: list[MechanismVariable],
    channel_mapping: ChannelSectionListMapping,
) -> dict[str, IonChannelVariables]:
    """Convert flat variables list and channel mapping to channel-grouped response."""
    raw: dict[str, dict] = {}

    for var in variables:
        channel = var.channel_name or "unknown"
        if channel not in raw:
            if channel == "-":
                # For section properties, collect all unique section lists from the model
                all_section_lists = set()
                for channel_info in channel_mapping.channel_to_section_lists.values():
                    all_section_lists.update(channel_info.section_lists)
                # If no section lists found, use defaults
                if not all_section_lists:
                    all_section_lists = {"somatic", "apical", "basal", "axonal"}

                raw[channel] = {
                    "section_lists": list(all_section_lists),
                    "entity_id": None,  # Section properties don't have entity IDs
                    "variables": {},
                }
            else:
                channel_info = channel_mapping.channel_to_section_lists.get(channel)
                raw[channel] = {
                    "section_lists": channel_info.section_lists if channel_info else [],
                    "entity_id": channel_info.entity_id if channel_info else None,
                    "variables": {},
                }
        var_entry = raw[channel]["variables"].setdefault(
            var.neuron_variable,
            {
                "units": var.units,
                "limits": var.limits,
                "variable_type": var.variable_type,
                "section_lists_original_values": {},
            },
        )
        var_entry["section_lists_original_values"][var.section_list] = var.value

    return {
        channel: IonChannelVariables(
            section_lists=data["section_lists"],
            entity_id=data["entity_id"],
            variables={
                var_name: MechanismVariableDetail(**var_data)
                for var_name, var_data in data["variables"].items()
            },
        )
        for channel, data in raw.items()
    }


def try_get_mechanism_variables(
    db_client: entitysdk.client.Client,
    entity_id: str,
) -> dict[str, IonChannelVariables] | None:
    """Try to fetch mechanism variables if entity_id refers to an MEModel.

    Returns None if the entity is not an MEModel or if fetching fails.
    Catches all exceptions so callers can safely treat this as optional data.
    """
    try:
        memodel = db_client.get_entity(entity_id=entity_id, entity_type=MEModel)
    except entitysdk.exception.EntitySDKError:
        return None

    try:
        variables, channel_mapping = get_mechanism_variables(db_client, memodel)
        return _build_mechanism_variables_by_ion_channel_response(variables, channel_mapping)
    except (entitysdk.exception.EntitySDKError, json.JSONDecodeError, KeyError, AttributeError):
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
