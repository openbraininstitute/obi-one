import abc
import logging
from typing import Annotated, ClassVar

import bluepysnap as snap
import numpy as np
from pydantic import Field, NonNegativeFloat

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.neuron_sets.base import NeuronSet, NeuronSetPopulationType
from obi_one.scientific.blocks.neuron_sets.constants import (
    BIOPHYSICAL_NEURON_SET_TITLE_SUFFIX,
    POINT_NEURON_SET_TITLE_SUFFIX,
    POPULATION_NEURON_SET_TITLE_PREFIX,
    VIRTUAL_NEURON_SET_TITLE_SUFFIX,
)
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

    def get_populations(self, circuit: Circuit) -> list[str]:  # noqa: ARG002
        """Returns population names included in the neuron set."""
        return [self.population]

    def _get_expression(self, circuit: Circuit) -> dict | list:
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_populations_in_circuit(circuit=circuit)
        return {"population": self.population}

    def _resolve_ids(self, circuit: Circuit) -> list[int]:
        """Returns the full list of neuron IDs (w/o subsampling)."""
        c = circuit.sonata_circuit
        expression = self._get_expression(circuit)
        name = "__TMP_NODE_SET__"
        add_node_set_to_circuit(c, {name: expression})

        try:
            node_ids = c.nodes[self.population].ids(name).tolist()
        except snap.BluepySnapError as e:
            # In case of an error (e.g., "No such attribute"), return empty list
            L.warning(e)
            node_ids = []

        return node_ids

    def get_neuron_ids(self, circuit: Circuit) -> dict[str, list[int]]:
        """Returns list of neuron IDs per population (with subsampling, if specified)."""
        ids = np.array(self._resolve_ids(circuit))

        if len(ids) > 0 and self.sample_percentage < _MAX_PERCENT:  # ty:ignore[unsupported-operator]
            rng = np.random.default_rng(self.sample_seed)
            num_sample = np.round((self.sample_percentage / 100.0) * len(ids)).astype(int)  # ty:ignore[unsupported-operator]
            ids = ids[rng.permutation([True] * num_sample + [False] * (len(ids) - num_sample))]

        if len(ids) == 0:
            L.warning("Neuron set empty!")

        return {self.population: ids.tolist()}

    def get_node_set_definition(
        self, circuit: Circuit, *, force_resolve_ids: bool = False
    ) -> tuple[dict | list, dict]:
        """Returns the SONATA node set definition, optionally forcing to resolve individual IDs.

        Returns a tuple of (expression, combined) where:

        - expression (dict): A single SONATA node set expression. Examples:
            - Symbolic by population: {"population": "pop_name"}
            - Symbolic by properties: {"layer": "6", "synapse_class": "EXC"}
            - Resolved IDs: {"population": "pop_name", "node_id": [1, 2, 3]}

        - expression (list): A compound expression referencing multiple named node sets.
            This is not used for population neuron sets.

        - combined (dict): Additional node set definitions needed by a compound expression.
            Always empty ({}) for population neuron sets.

        Args:
            circuit: The circuit to resolve the node set in.
            force_resolve_ids: If True, always resolve to explicit neuron IDs
                instead of preserving symbolic expressions.
        """
        if self.sample_percentage == _MAX_PERCENT and not force_resolve_ids:
            # Symbolic expression can be preserved
            expression = self._get_expression(circuit)
        else:
            # Individual IDs need to be resolved
            expression = {
                "population": self.population,
                "node_id": self.get_neuron_ids(circuit)[self.population],
            }

        return (expression, {})


class BiophysicalPopulationNeuronSetMixin:
    """Sample a percentage of neurons from a biophysical population."""

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


class PointPopulationNeuronSetMixin:
    """Sample a percentage of neurons from a point neuron population."""

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


class VirtualPopulationNeuronSetMixin:
    """Sample a percentage of neurons from a virtual population."""

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


class BiophysicalPopulationNeuronSet(BiophysicalPopulationNeuronSetMixin, PopulationBaseNeuronSet):
    """Sample a percentage of neurons from a biophysical population."""

    title: ClassVar[str] = (
        f"{POPULATION_NEURON_SET_TITLE_PREFIX}{BIOPHYSICAL_NEURON_SET_TITLE_SUFFIX}"
    )
    description: ClassVar[str] = "Sample a percentage of neurons from a biophysical population."


class PointPopulationNeuronSet(PointPopulationNeuronSetMixin, PopulationBaseNeuronSet):
    """Sample a percentage of neurons from a point neuron population."""

    title: ClassVar[str] = f"{POPULATION_NEURON_SET_TITLE_PREFIX}{POINT_NEURON_SET_TITLE_SUFFIX}"
    description: ClassVar[str] = "Sample a percentage of neurons from a point neuron population."


class VirtualPopulationNeuronSet(
    VirtualPopulationNeuronSetMixin,
    PopulationBaseNeuronSet,
):
    """Sample a percentage of neurons from a virtual population."""

    title: ClassVar[str] = f"{POPULATION_NEURON_SET_TITLE_PREFIX}{VIRTUAL_NEURON_SET_TITLE_SUFFIX}"
    description: ClassVar[str] = "Sample a percentage of neurons from a virtual population."
