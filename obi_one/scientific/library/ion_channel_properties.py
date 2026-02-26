import itertools
from collections.abc import Mapping

from entitysdk.client import Client
from entitysdk.models.ion_channel_model import IonChannelModel

# from entitysdk.staging.ion_channel_model import find_conductance_name # curently in PR #175
from pydantic import BaseModel


class IonChannelVariablesOutput(BaseModel, Mapping):
    ion_channel_suffix: str
    current: list[str]
    non_specific_current: list[str]
    concentration: list[str]

    @property
    def variables(self) -> list[str]:
        current_variables = [f"{self.ion_channel_suffix}.{current}" for current in self.current]
        non_specific_current_variables = [
            f"{self.ion_channel_suffix}.{non_specific_current}"
            for non_specific_current in self.non_specific_current
        ]
        return list(
            itertools.chain(current_variables, non_specific_current_variables, self.concentration)
        )

    @property
    def variables_and_units(self) -> list[str]:
        current_variables = [
            {"variable": f"{self.ion_channel_suffix}.{current}", "unit": "mA/cm2"}
            for current in self.current
        ]
        non_specific_current_variables = [
            {"variable": f"{self.ion_channel_suffix}.{non_specific_current}", "unit": "mA/cm2"}
            for non_specific_current in self.non_specific_current
        ]
        concentration = [{{"variable": conc, "unit": "mM"}} for conc in self.concentration]
        return list(
            itertools.chain(current_variables, non_specific_current_variables, concentration)
        )


def get_ion_channel_variables(
    ion_channel_ids: list[str],
    db_client: Client,
) -> IonChannelVariablesOutput:
    output = {}
    for i, ion_channel_id in enumerate(ion_channel_ids):
        ion_channel = db_client.search_entity(
            entity_id=ion_channel_id,
            entity_type=IonChannelModel,
        )
        non_specific_current = [
            var_name
            for nonspecific in ion_channel.neuron_block.nonspecific or []
            for var_name in nonspecific
        ]
        write = [
            var_name
            for useion in ion_channel.neuron_block.useion or []
            for var_name in useion.write or []
        ]
        current = [var_name for var_name in write if var_name[0] == "i"]
        concentration = [var_name for var_name in write if var_name[-1] == "i"]

        # some ion channels can have the same name,
        # so we add the index to differentiate them in the output
        key = f"{i + 1}: {ion_channel.name}"
        output[key] = {
            "name": ion_channel.name,
            "variables": IonChannelVariablesOutput(
                ion_channel_siffix=ion_channel.nmodl_suffix,
                current=current,
                non_specific_current=non_specific_current,
                concentration=concentration,
            ),
        }

    return output
