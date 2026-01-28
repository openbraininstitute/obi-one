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


def get_ion_channel_variables(
    ion_channel_id: str,
    db_client: Client,
) -> IonChannelVariablesOutput:
    ion_channel = db_client.get_entity(
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

    return IonChannelVariablesOutput(
        ion_channel_siffix=ion_channel.nmodl_suffix,
        current=current,
        non_specific_current=non_specific_current,
        concentration=concentration,
    )
