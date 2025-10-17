import abc
import logging
from typing import Annotated, Self

import numpy as np
import pandas as pd
from pydantic import Field, model_validator

from obi_one.core.base import OBIBaseModel
from obi_one.scientific.blocks.neuron_sets.base import NeuronSet
from obi_one.scientific.library.circuit import Circuit

L = logging.getLogger("obi-one")


CircuitNode = Annotated[str, Field(min_length=1)]
NodeSetType = CircuitNode | list[CircuitNode]


class NeuronPropertyFilter(OBIBaseModel, abc.ABC):
    filter_dict: dict[str, list] = Field(
        name="Filter",
        description="Filter dictionary. Note as this is NOT a Block and the list here is \
                    not to support multi-dimensional parameters but to support a key-value pair \
                    with multiple values i.e. {'layer': ['2', '3']}}",
        default={},
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
        for filter_key, _filter_value in self.filter_dict.items():
            filter_value = [str(_entry) for _entry in _filter_value]
            vld = ret[filter_key].astype(str).isin(filter_value)
            ret = ret.loc[vld]
            if reindex:
                ret = ret.reset_index(drop=True)
        return ret

    def test_validity(self, circuit: Circuit, node_population: str) -> None:
        circuit_prop_names = circuit.sonata_circuit.nodes[node_population].property_names

        if not all(_prop in circuit_prop_names for _prop in self.filter_keys):
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


class PropertyNeuronSet(NeuronSet):
    """Neuron set definition based on neuron properties, optionally combined with (named) node \
        sets.
    """

    property_filter: NeuronPropertyFilter | list[NeuronPropertyFilter] = Field(
        name="Neuron property filter",
        description="NeuronPropertyFilter object or list of NeuronPropertyFilter objects",
        default=(),
    )
    node_sets: (
        tuple[Annotated[str, Field(min_length=1)], ...]
        | Annotated[list[tuple[Annotated[str, Field(min_length=1)], ...]], Field(min_length=1)]
    ) = ()

    def check_properties(self, circuit: Circuit, population: str | None = None) -> None:
        population = self._population(population)
        self.property_filter.test_validity(circuit, population)

    def check_node_sets(self, circuit: Circuit, _population: str) -> None:
        for _nset in self.node_sets:
            if _nset not in circuit.node_sets:
                msg = f"Node set '{_nset}' not found in circuit '{circuit}'!"
                raise ValueError(msg)

    def _get_resolved_expression(self, circuit: Circuit, population: str | None = None) -> dict:
        """A helper function used to make subclasses work."""
        c = circuit.sonata_circuit
        population = self._population(population)

        df = c.nodes[population].get(properties=self.property_filter.filter_keys).reset_index()
        df = self.property_filter.filter(df)

        node_ids = df["node_ids"].to_numpy()

        if len(self.node_sets) > 0:
            node_ids_nset = np.array([]).astype(int)
            for _nset in self.node_sets:
                node_ids_nset = np.union1d(node_ids_nset, c.nodes[population].ids(_nset))
            node_ids = np.intersect1d(node_ids, node_ids_nset)

        expression = {"population": population, "node_id": node_ids.tolist()}
        return expression

    def _get_expression(self, circuit: Circuit, population: str) -> dict:
        """Returns the SONATA node set expression (w/o subsampling)."""
        population = self._population(population)
        self.check_properties(circuit, population)
        self.check_node_sets(circuit, population)

        def __resolve_sngl(prop_vals: list) -> list:
            if len(prop_vals) == 1:
                return prop_vals[0]
            return list(prop_vals)

        if len(self.node_sets) == 0:
            # Symbolic expression can be preserved
            expression = {
                property_key: __resolve_sngl(property_value)
                for property_key, property_value in self.property_filter.filter_dict.items()
            }
        else:
            # Individual IDs need to be resolved
            return self._get_resolved_expression(circuit, population)

        return expression
