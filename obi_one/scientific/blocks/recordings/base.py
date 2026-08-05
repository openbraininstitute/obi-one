from abc import ABC, abstractmethod
from pathlib import Path
from typing import Annotated

import entitysdk
from pydantic import Field, NonNegativeFloat, PositiveFloat, PrivateAttr

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.parametric_multi_values import NonNegativeFloatRange
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.neuron_sets.base import NeuronSetPopulationType
from obi_one.scientific.library.constants import MIN_TIMESTEP_MILLISECONDS
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
    NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION,
)


class Recording(Block, ABC):
    neuron_set: NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="Neuron Set",
        description="Neuron set to record from.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
        },
    )

    _start_time: NonNegativeFloat = 0.0
    _end_time: PositiveFloat = 100.0

    dt: (
        Annotated[NonNegativeFloat, Field(ge=MIN_TIMESTEP_MILLISECONDS)]
        | list[Annotated[NonNegativeFloat, Field(ge=MIN_TIMESTEP_MILLISECONDS)]]
        | Annotated[NonNegativeFloatRange, Field(ge=MIN_TIMESTEP_MILLISECONDS)]
    ) = Field(
        default=0.1,
        title="Timestep",
        description="Interval between recording time steps in milliseconds (ms).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    _default_node_set: str = PrivateAttr(default="All")
    _sonata_simulation_config_directory: Path | None = PrivateAttr(default=None)

    def config(
        self,
        end_time: NonNegativeFloat | None = None,
        default_node_set: str = "All",
        db_client: entitysdk.client.Client | None = None,
        sonata_simulation_config_directory: Path | None = None,
    ) -> dict:
        self._default_node_set = default_node_set
        self._sonata_simulation_config_directory = sonata_simulation_config_directory

        if (self.neuron_set is not None) and (
            self.neuron_set.block.get_neuron_set_population_type()
            not in {
                NeuronSetPopulationType.BIOPHYSICAL,
                NeuronSetPopulationType.POINT,
                NeuronSetPopulationType.NONVIRTUAL,
            }
        ):
            msg = (
                f"Neuron Set '{self.neuron_set.block.block_name}' for {self.__class__.__name__}: "
                f"'{self.block_name}' should be non-virtual (biophysical or point)!"
            )
            raise OBIONEError(msg)

        if end_time is None:
            msg = f"End time must be specified for recording '{self.block_name}'."
            raise OBIONEError(msg)
        self._end_time = end_time

        sonata_config = self._generate_config(db_client=db_client)

        if self._end_time <= self._start_time:
            msg = (
                f"Recording '{self.block_name}' for Neuron Set "
                "'{self.neuron_set.block.block_name}': "
                "End time must be later than start time!"
            )
            raise OBIONEError(msg)

        return sonata_config

    @abstractmethod
    def _generate_config(self, db_client: entitysdk.client.Client | None = None) -> dict:
        pass
