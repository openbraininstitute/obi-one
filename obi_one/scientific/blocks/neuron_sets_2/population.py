import abc
import logging
from typing import Annotated, ClassVar

import bluepysnap as snap
import numpy as np
from pydantic import Field, NonNegativeFloat

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.neuron_sets_2.base import NeuronSet, NeuronSetPopulationType
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.entity_property_types import (
    CircuitMappedProperties,
    CircuitUsability,
    MappedPropertiesGroup,
)
from obi_one.scientific.library.sonata_circuit_helpers import (
    add_node_set_to_circuit,
)

L = logging.getLogger(__name__)

_MAX_PERCENT = 100.0


class PopulationBaseNeuronSet(NeuronSet, abc.ABC):
    """Abstract base class for neuron sets defined by a node population \
        and optional sub-sampling.
    """

    population: str

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

    def get_populations(self) -> list[str]:
        """Returns population names included in the neuron set."""
        return [self.population]

    def _get_expression(self, circuit: Circuit) -> dict:
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_populations_in_circuit(circuit=circuit)
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

    def get_neuron_ids(self, circuit: Circuit) -> dict[str, np.ndarray]:
        """Returns list of neuron IDs per population (with subsampling, if specified)."""
        ids = np.array(self._resolve_ids(circuit))

        if len(ids) > 0 and self.sample_percentage < _MAX_PERCENT:
            rng = np.random.default_rng(self.sample_seed)
            num_sample = np.round((self.sample_percentage / 100.0) * len(ids)).astype(int)
            ids = ids[rng.permutation([True] * num_sample + [False] * (len(ids) - num_sample))]

        if len(ids) == 0:
            L.warning("Neuron set empty!")

        return {self.population: ids}

    def get_node_set_definition(
        self, circuit: Circuit, *, force_resolve_ids: bool = False
    ) -> tuple[dict | list, dict]:
        """Returns the SONATA node set definition, optionally forcing to resolve individual IDs.

        In case of a compound expression (list expression), any new definitions
        to be combined are returned as dict.
        """
        if self.sample_percentage == _MAX_PERCENT and not force_resolve_ids:
            # Symbolic expression can be preserved
            expression = self._get_expression(circuit)
        else:
            # Individual IDs need to be resolved
            expression = {
                "population": self.population,
                "node_id": self.get_neuron_ids(circuit)[self.population].tolist(),
            }

        return (expression, {})


class PopulationNeuronSet(PopulationBaseNeuronSet):
    """Sample a percentage of neurons from any population."""

    title: ClassVar[str] = "Population Sample % (Any)"
    description: ClassVar[str] = "Sample a percentage of neurons from a population of any type."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = NeuronSetPopulationType.ANY

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_NEURON_SETS,
            SchemaKey.FALSE_MESSAGE: "This circuit has no populations.",
        },
    }

    population: str = Field(
        min_length=1,
        title="Population",
        description="Name of the node population to select from.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.ENTITY_PROPERTY_DROPDOWN,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitMappedProperties.NEURONAL_POPULATION,
        },
    )


class BiophysicalPopulationNeuronSet(PopulationBaseNeuronSet):
    """Sample a percentage of neurons from a biophysical population."""

    title: ClassVar[str] = "Population Sample % (Biophysical)"
    description: ClassVar[str] = "Sample a percentage of neurons from a biophysical population."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = (
        NeuronSetPopulationType.BIOPHYSICAL
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_BIOPHYSICAL_NEURON_SETS,
            SchemaKey.FALSE_MESSAGE: "This circuit has no biophysical populations.",
        },
    }

    population: str = Field(
        min_length=1,
        title="Population",
        description="Name of the biophysical node population to select from.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.ENTITY_PROPERTY_DROPDOWN,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitMappedProperties.BIOPHYSICAL_NEURONAL_POPULATION,
        },
    )


class PointPopulationNeuronSet(PopulationBaseNeuronSet):
    """Sample a percentage of neurons from a point neuron population."""

    title: ClassVar[str] = "Population Sample % (Point)"
    description: ClassVar[str] = "Sample a percentage of neurons from a point neuron population."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = NeuronSetPopulationType.POINT

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_POINT_NEURON_SETS,
            SchemaKey.FALSE_MESSAGE: "This circuit has no point neuron populations.",
        },
    }

    population: str = Field(
        min_length=1,
        title="Population",
        description="Name of the point neuron node population to select from.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.ENTITY_PROPERTY_DROPDOWN,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitMappedProperties.POINT_NEURONAL_POPULATION,
        },
    )


class VirtualPopulationNeuronSet(PopulationBaseNeuronSet):
    """Sample a percentage of neurons from a virtual population."""

    title: ClassVar[str] = "Population Sample % (Virtual)"
    description: ClassVar[str] = "Sample a percentage of neurons from a virtual population."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = NeuronSetPopulationType.VIRTUAL

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_VIRTUAL_NEURON_SETS,
            SchemaKey.FALSE_MESSAGE: "This circuit has no virtual populations.",
        },
    }

    population: str = Field(
        min_length=1,
        title="Population",
        description="Name of the virtual node population to select from.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.ENTITY_PROPERTY_DROPDOWN,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitMappedProperties.VIRTUAL_NEURONAL_POPULATION,
        },
    )


class NonVirtualPopulationNeuronSet(PopulationBaseNeuronSet):
    """Sample a percentage of neurons from a non-virtual population."""

    title: ClassVar[str] = "Population Sample % (Non-Virtual)"
    description: ClassVar[str] = "Sample a percentage of neurons from a non-virtual population."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = (
        NeuronSetPopulationType.NONVIRTUAL
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_NONVIRTUAL_NEURON_SETS,
            SchemaKey.FALSE_MESSAGE: "This circuit has no non-virtual populations.",
        },
    }

    population: str = Field(
        min_length=1,
        title="Population",
        description="Name of the non-virtual node population to select from.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.ENTITY_PROPERTY_DROPDOWN,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitMappedProperties.NONVIRTUAL_NEURONAL_POPULATION,
        },
    )
