import abc
import logging
from enum import StrEnum
from typing import Annotated

import bluepysnap as snap
from pydantic import Field, NonNegativeFloat, model_validator

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.neuron_sets_2.base import NeuronSet
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.entity_property_types import (
    CircuitMappedProperties,
    MappedPropertiesGroup,
)
from obi_one.scientific.library.sonata_circuit_helpers import (
    add_node_set_to_circuit,
)

L = logging.getLogger(__name__)


"""PopulationNeuronSet(NeuronSet) [NEW]
- node_population
- sample_percentage
- sample_seed
- _population_type

- Allows a user to select a whole node population, i.e., restricted to a single node population
- Supports sub-sampling
- Is aware of the population type (i.e., biophysical, point, virtual)
- Can be used for either biophysical, point, or virtual populations
- Replaces: AllNeurons, nbS1VPMInputs, nbS1POmInputs, rCA1CA3Inputs, etc.
"""


class SonataPopulationType(StrEnum):
    BIOPHYSICAL = "biophysical"
    POINT = "point"
    VIRTUAL = "virtual"


_MAX_PERCENT = 100.0


class PopulationNeuronSet(NeuronSet, abc.ABC):
    """"""

    population = None
    _population_type: SonataPopulationType | None = None

    sample_percentage: (
        Annotated[NonNegativeFloat, Field(le=100)]
        | Annotated[list[Annotated[NonNegativeFloat, Field(le=100)]], Field(min_length=1)]
    ) = Field(
        default=100.0,
        title="Sample (Percentage)",
        description="Percentage of neurons to sample between 0 and 100%",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.PERCENT,
        },
    )

    sample_seed: int | list[int] = Field(
        default=1,
        title="Sample Seed",
        description="Seed for random sampling.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    @model_validator(mode="after")
    def check_population_exists_in_circuit(self, circuit: Circuit) -> None:
        """Check self.population exists in circuit."""
        if self.population is None:
            msg = "Sub-class of PopulationNeuronSet must specify a node population name!"
            raise ValueError(msg)
        if self.population not in (
            populations := Circuit.get_node_population_names(circuit.sonata_circuit)
        ):
            msg = (
                f"Node population '{self.population}' not found in circuit '{circuit.name}'. "
                f"Available node populations: {', '.join(populations)}"
            )
            raise ValueError(msg)

    def population_type(self, circuit: Circuit) -> SonataPopulationType:
        """Returns the population type (i.e. biophysical, point, virtual)."""
        return circuit.sonata_circuit.nodes[self.population].type

    def _get_expression(self, circuit: Circuit) -> dict:
        """Returns the SONATA node set expression (w/o subsampling)."""
        return {"population": self.population}

    def _resolve_ids(self, circuit: Circuit) -> list[int]:
        """Returns the full list of neuron IDs (w/o subsampling)."""
        expression = self._get_expression(circuit)
        name = "__TMP_NODE_SET__"
        add_node_set_to_circuit(circuit.sonata_circuit, {name: expression})

        try:
            node_ids = circuit.sonata_circuit.nodes[self.population].ids(name)
        except snap.BluepySnapError as e:
            # In case of an error, return empty list
            L.warning(e)
            node_ids = []

        return node_ids

    def get_neuron_ids(self, circuit: Circuit) -> np.ndarray:
        """Returns list of neuron IDs (with subsampling, if specified)."""
        # self.enforce_no_multi_param()
        # self.check_population(circuit)
        ids = np.array(self._resolve_ids(circuit))

        if len(ids) > 0 and self.sample_percentage < _MAX_PERCENT:
            rng = np.random.default_rng(self.sample_seed)
            num_sample = np.round((self.sample_percentage / 100.0) * len(ids)).astype(int)
            ids = ids[rng.permutation([True] * num_sample + [False] * (len(ids) - num_sample))]

        if len(ids) == 0:
            L.warning("Neuron set empty!")

        return ids

    def get_node_set_definition(self, circuit: Circuit, *, force_resolve_ids: bool = False) -> dict:
        """Returns the SONATA node set definition, optionally forcing to resolve individual \
            IDs.
        """
        # self.enforce_no_multi_param()
        if self.sample_percentage == _MAX_PERCENT and not force_resolve_ids:
            # Symbolic expression can be preserved
            # self.check_population(circuit, ignore_none=True)
            expression = self._get_expression(circuit)
        else:
            # Individual IDs need to be resolved
            # self.check_population(circuit)
            expression = {
                "population": self.population,
                "node_id": self.get_neuron_ids(circuit).tolist(),
            }

        return expression


class BiophysicalPopulationNeuronSet(PopulationNeuronSet):
    """Only biophysical node populations are selectable."""

    population: str = Field(
        default="",
        min_length=1,
        title="Population",
        description="Name of the biophysical node population to select from.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.ENTITY_PROPERTY_DROPDOWN,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitMappedProperties.BIOPHYSICAL_NODE_POPULATION,
        },
    )


class PointNeuronPopulationNeuronSet(PopulationNeuronSet):
    """Only point neuron node populations are selectable."""

    population: str = Field(
        default="",
        min_length=1,
        title="Population",
        description="Name of the point neuron node population to select from.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.ENTITY_PROPERTY_DROPDOWN,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitMappedProperties.POINT_NODE_POPULATION,
        },
    )


class VirtualPopulationNeuronSet(PopulationNeuronSet):
    """Only virtual node populations are selectable."""

    population: str = Field(
        default="",
        min_length=1,
        title="Population",
        description="Name of the virtual node population to select from.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.ENTITY_PROPERTY_DROPDOWN,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitMappedProperties.VIRTUAL_NODE_POPULATION,
        },
    )
