import abc
import logging
from typing import Annotated, ClassVar, Self

import pandas as pd
from pydantic import Field, model_validator

from obi_one.core.base import OBIBaseModel
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.neuron_sets.population import (
    BiophysicalPopulationNeuronSetMixin,
    PointPopulationNeuronSetMixin,
    PopulationBaseNeuronSet,
    VirtualPopulationNeuronSetMixin,
)
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.entity_property_types import (
    CircuitMappedProperties,
    MappedPropertiesGroup,
)

L = logging.getLogger("obi-one")


class NeuronPropertyFilter(OBIBaseModel):
    filter_dict: dict[str, list[str] | list[int]] = Field(
        title="Filter",
        description=(
            "Filter dictionary. Note: this is NOT a Block and the list here is not to"
            " support multi-dimensional parameters but to support a key-value pair with"
            " multiple values i.e. {'layer': ['2', '3']}"
        ),
    )

    @model_validator(mode="after")
    def check_filter_dict_values(self) -> Self:
        for key, values in self.filter_dict.items():
            if not isinstance(values, list) or len(values) == 0:
                msg = f"Filter key '{key}' must have a non-empty list of values."
                raise ValueError(msg)
        return self

    @property
    def filter_keys(self) -> list[str]:
        return list(self.filter_dict.keys())

    @property
    def filter_values(self) -> list[list]:
        return list(self.filter_dict.values())

    def filter(self, df_in: pd.DataFrame, *, reindex: bool = True) -> pd.DataFrame:
        ret = df_in
        for filter_key, filter_values in self.filter_dict.items():
            str_values = [str(entry) for entry in filter_values]
            vld = ret[filter_key].astype(str).isin(str_values)
            ret = ret.loc[vld]
            if reindex:
                ret = ret.reset_index(drop=True)
        return ret

    def test_validity(self, circuit: Circuit, node_population: str) -> None:
        circuit_prop_names = circuit.sonata_circuit.nodes[node_population].property_names

        if not all(prop in circuit_prop_names for prop in self.filter_keys):
            msg = f"Invalid neuron properties! Available properties: {circuit_prop_names}"
            raise ValueError(msg)

    def __repr__(self) -> str:
        """Return a string representation of the NeuronPropertyFilter object."""
        if len(self.filter_dict) == 0:
            return "NoFilter"
        string_rep = ""
        for filter_key, filter_value in self.filter_dict.items():
            string_rep += f"{filter_key}="
            for value in filter_value:
                string_rep += f"{value},"
        return string_rep[:-1]  # Remove trailing comma and space


class PropertyPopulationBaseNeuronSet(PopulationBaseNeuronSet, abc.ABC):
    """Abstract base class for a neuron set definition based on neuron properties
    in a given node population.
    """

    property_filter: (
        NeuronPropertyFilter | Annotated[list[NeuronPropertyFilter], Field(min_length=1)]
    ) = Field(
        title="Neuron Property Filter",
        description="Neuron property values to use for filtering neuron IDs.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.NEURON_PROPERTY_FILTER,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitMappedProperties.NODE_PROPERTY_UNIQUE_VALUES_BY_POPULATION,
            "population_source_dropdown_key": "population",
        },
    )

    def check_properties(self, circuit: Circuit) -> None:
        self.property_filter.test_validity(circuit, self.population)  # ty:ignore[unresolved-attribute]

    def _resolve_in_population(self, circuit: Circuit, population: str) -> list[int]:
        """Resolve property filter in a given population, returning matching neuron IDs."""
        c = circuit.sonata_circuit
        try:
            df = (
                c.nodes[population]
                .get(
                    properties=self.property_filter.filter_keys  # ty:ignore[unresolved-attribute]
                )
                .reset_index()
            )
            df = self.property_filter.filter(df)  # ty:ignore[unresolved-attribute]
        except Exception:  # noqa: BLE001
            return []
        return df["node_ids"].to_numpy().tolist()

    def _resolve_ids(self, circuit: Circuit) -> list[int]:
        """Returns the full list of neuron IDs (w/o subsampling)."""
        self.check_populations_in_circuit(circuit=circuit)
        self.check_properties(circuit)
        return self._resolve_in_population(circuit, self.population)

    def _get_expression(self, circuit: Circuit) -> dict:
        """Returns the SONATA node set expression (w/o subsampling).

        If the property filter only matches neurons in self.population, keeps
        it symbolic (without population key). Otherwise resolves IDs.
        """
        self.check_populations_in_circuit(circuit=circuit)
        self.check_properties(circuit)

        # Check if properties also resolve in other populations
        resolves_elsewhere = any(
            len(self._resolve_in_population(circuit, npop)) > 0
            for npop in circuit.sonata_circuit.nodes.population_names
            if npop != self.population
        )

        if not resolves_elsewhere:
            # Only resolves in self.population — keep symbolic (no population key)
            expression = {}
            for key, values in self.property_filter.filter_dict.items():  # ty:ignore[unresolved-attribute]
                expression[key] = values[0] if len(values) == 1 else list(values)
            return expression

        # Resolves in multiple populations — must use explicit IDs
        node_ids = self._resolve_in_population(circuit, self.population)
        return {"population": self.population, "node_id": node_ids}


class BiophysicalPopulationPropertyNeuronSet(
    PropertyPopulationBaseNeuronSet, BiophysicalPopulationNeuronSetMixin
):
    """Neuron set definition based on neuron properties.

    Resolved in one selected biophysical node population.
    """

    title: ClassVar[str] = "BY NODE PROPERTY (Biophysical)"
    description: ClassVar[str] = (
        "Use neurons based on properties, resolved in a single biophysical population."
    )


class VirtualPopulationPropertyNeuronSet(
    PropertyPopulationBaseNeuronSet, VirtualPopulationNeuronSetMixin
):
    """Neuron set definition based on neuron properties.

    Resolved in one selected virtual node population.
    """

    title: ClassVar[str] = "By Properties (Virtual)"
    description: ClassVar[str] = (
        "Use neurons based on properties, resolved in a single virtual population."
    )


class PointPopulationPropertyNeuronSet(
    PropertyPopulationBaseNeuronSet, PointPopulationNeuronSetMixin
):
    """Neuron set definition based on neuron properties.

    Resolved in one selected point neuron population.
    """

    title: ClassVar[str] = "By Properties (Point)"
    description: ClassVar[str] = (
        "Use neurons based on properties, resolved in a single point neuron population."
    )
