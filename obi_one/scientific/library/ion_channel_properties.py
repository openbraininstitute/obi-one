import itertools
import uuid
from collections.abc import Iterator, Mapping
from typing import Annotated

from click import UUID
from entitysdk.client import Client
from entitysdk.models.ion_channel_model import IonChannelModel
from pydantic import BaseModel, Field


class IonChannelVariable(BaseModel):
    """Single variable of an ion channel model to be recorded.

    Contains the ion channel ID, variable name, and unit.

    Example (GLOBAL ion channel):
        ion_channel_id: uuid.UUID("...")
        channel_name: "StochKv3"
        variable_name: "ik_StochKv3"
        unit: "mA/cm2"
    """

    ion_channel_id: Annotated[uuid.UUID, Field(description="ID of the ion channel")] | None = None
    channel_name: (
        Annotated[
            str,
            Field(
                min_length=1,
                description="Channel suffix (e.g., 'NaTg') used as key in conditions.mechanisms",
            ),
        ]
        | None
    ) = None
    variable_name: str = Field(
        description="Name of the variable (e.g., 'vmin_StochKv3', 'gCa_HVAbar_Ca_HVA2', 'cm', 'Ra')"
    )
    unit: str = Field(
        description="Unit of the variable (e.g., 'mA/cm2', 'mV', 'mM')",
    )


class IonChannelVariablesOutput(BaseModel, Mapping):
    ion_channel_id: str | uuid.UUID
    ion_channel_suffix: str
    current: list[str]
    non_specific_current: list[str]
    concentration: list[str]

    def __getitem__(self, key: str) -> str | uuid.UUID | list[str]:
        """Get item by key."""
        return self.model_dump()[key]

    def __len__(self) -> int:
        """Length."""
        return len(self.model_fields)

    def __iter__(self) -> Iterator:  # ty:ignore[invalid-method-override]
        """Iterable."""
        return iter(self.model_dump())

    @property
    def variables(self) -> list[str]:
        current_variables = [
            IonChannelVariable(
                ion_channel_id=self.ion_channel_id,  # ty:ignore[invalid-argument-type]
                channel_name=self.ion_channel_suffix,
                variable_name=f"{current}_{self.ion_channel_suffix}",
                unit="mA/cm2",
            )
            for current in self.current
        ]
        non_specific_current_variables = [
            IonChannelVariable(
                ion_channel_id=self.ion_channel_id,  # ty:ignore[invalid-argument-type]
                channel_name=self.ion_channel_suffix,
                variable_name=f"{non_specific_current}_{self.ion_channel_suffix}",
                unit="mA/cm2",
            )
            for non_specific_current in self.non_specific_current
        ]
        concentration = [
            IonChannelVariable(
                ion_channel_id=self.ion_channel_id,  # ty:ignore[invalid-argument-type]
                channel_name=self.ion_channel_suffix,
                variable_name=conc,
                unit="mM",
            )
            for conc in self.concentration
        ]
        return list(
            itertools.chain(current_variables, non_specific_current_variables, concentration)
        )  # ty:ignore[invalid-return-type]


def get_ion_channel_variables(
    ion_channel_ids: list[str],
    db_client: Client,
) -> IonChannelVariablesOutput:
    output = {}
    for i, ion_channel_id in enumerate(ion_channel_ids):
        ion_channel = db_client.get_entity(
            entity_id=UUID(ion_channel_id),
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
        output[key] = IonChannelVariablesOutput(
            ion_channel_id=ion_channel_id,
            ion_channel_suffix=ion_channel.nmodl_suffix,
            current=current,
            non_specific_current=non_specific_current,
            concentration=concentration,
        )

    return output  # ty:ignore[invalid-return-type]
