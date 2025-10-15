import contextlib
import logging
from typing import Annotated, Literal, Self

import numpy as np
from pydantic import Field, field_validator, model_validator

from obi_one.scientific.blocks.neuron_sets.property import PropertyNeuronSet
from obi_one.scientific.library.circuit import Circuit

L = logging.getLogger("obi-one")

CircuitNode = Annotated[str, Field(min_length=1)]
NodeSetType = CircuitNode | list[CircuitNode]

with contextlib.suppress(ImportError):  # Try to import connalysis
    from obi_one.scientific.library.simplex_extractors import simplex_submat


class SimplexMembershipBasedNeuronSet(PropertyNeuronSet):
    """Sample neurons from the set of neurons that form simplices.

    Simplices of a given dimension with a chosen source or target 'central' neuron can be specified.
    """

    central_neuron_id: int | list[int] = Field(
        name="Central neuron id",
        description="Node id (index) that will be source or target of the simplices extracted",
    )
    dim: int | list[int] = Field(
        name="Dimension",
        description="Dimension of the simplices to be extracted",
    )
    central_neuron_simplex_position: (
        Literal["source", "target"] | list[Literal["source", "target"]]
    ) = Field(
        "source",
        name="Central neuron simplex position",
        description="Position of the central neuron/node in the simplex, it can be either"
        " 'source' or 'target'",
    )
    subsample: bool | list[bool] = Field(
        default=True,
        name="subsample",
        description="Whether to subsample the set of nodes in the simplex lists or not",
    )
    n_count_max: int | list[int] | None = Field(
        default=False,
        name="Max node count",
        description="Maximum number of nodes to be subsampled",
    )
    subsample_method: (
        Literal["node_participation", "random"] | list[Literal["node_participation", "random"]]
    ) = Field(
        "node_participation",
        name="Method to subsample nodes from the extracted simplices",
        description="""
        **Method to subsample nodes**:
        - `random`: randomly selects nodes from all nodes in the simplices
        - `node_participation`: selects nodes with highest node participation
            """,
    )
    simplex_type: (
        Literal["directed", "reciprocal", "undirected"]
        | list[Literal["directed", "reciprocal", "undirected"]]
    ) = Field(
        "directed",
        name="Simplex type",
        description="Type of simplex to consider. See more at \
            https://openbraininstitute.github.io/connectome-analysis/network_topology/#src.connalysis.network.topology.simplex_counts",
    )
    seed: int | list[int] | None = Field(
        None,
        name="seed",
        description="Seed used for random subsampling method",
    )

    @field_validator("dim")
    @staticmethod
    def dim_check(v: int) -> int:
        if v <= 1:
            msg = "Simplex dimension must be greater than 1"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def check_n_count_max(self) -> Self:
        n_count_max = self.n_count_max
        if self.subsample and n_count_max is None:
            msg = "n_count_max must be specified when subsample is True"
            raise ValueError(msg)
        return self

    def _get_expression(self, circuit: Circuit, population: str) -> dict:
        if "simplex_submat" not in globals():
            msg = (
                "Import of 'simplex_submat' failed. You probably need to install connalysis"
                " locally."
            )
            raise ValueError(msg)

        self.check_properties(circuit, population)
        self.check_node_sets(circuit, population)
        # Always needs to be resolved
        base_expression = self._get_resolved_expression(circuit, population)

        # Restrict connectivity matrix to chosen subpopulation and find index of center
        conn = circuit.connectivity_matrix.subpopulation(base_expression["node_id"])
        index = np.where(conn.vertices["node_ids"] == self.central_neuron_id)[0]
        if len(index) == 0:
            msg = (
                f"The neuron of index {self.central_neuron_id} is not in the subpopulation selected"
            )
            raise ValueError(msg)
        index = index[0]

        # Get nodes on simplices index by 0 ... conn._shape[0]
        selection = simplex_submat(
            conn.matrix,
            index,
            self.dim,
            v_position=self.central_neuron_simplex_position,
            subsample=self.subsample,
            n_count_max=self.n_count_max,
            subsample_method=self.subsample_method,
            simplex_type=self.simplex_type,
            seed=self.seed,
        )

        # Get node_ids (i.e., get correct index) and build expression dict
        selection = conn.vertices["node_ids"].iloc[selection]
        expression = {"population": population, "node_id": selection.tolist()}
        return expression


class SimplexNeuronSet(PropertyNeuronSet):
    """Get neurons that form simplices of a given dimension with a chosen source or target neuron.
    If a smaller sample is required, it samples simplices while the number of nodes on them is still
    smaller or equal than a set target size.
    """

    central_neuron_id: int | list[int] = Field(
        name="Central neuron id",
        description="Node id (index) that will be source or target of the simplices extracted",
    )
    dim: int | list[int] = Field(
        name="Dimension",
        description="Dimension of the simplices to be extracted",
    )
    central_neuron_simplex_position: (
        Literal["source", "target"] | list[Literal["source", "target"]]
    ) = Field(
        "source",
        name="Central neuron simplex position",
        description="Position of the central neuron/node in the simplex, it can be either"
        " 'source' or 'target'",
    )
    subsample: bool = Field(
        default=False,
        name="subsample",
        description="Whether to subsample the set of nodes in the simplex lists or not",
    )
    n_count_max: int | list[int] | None = Field(
        None,
        name="Max node count",
        description="Maximum number of nodes to be subsampled",
    )
    simplex_type: (
        Literal["directed", "reciprocal", "undirected"]
        | list[Literal["directed", "reciprocal", "undirected"]]
    ) = Field(
        "directed",
        name="Simplex type",
        description="Type of simplex to consider. See more at \
            https://openbraininstitute.github.io/connectome-analysis/network_topology/#src.connalysis.network.topology.simplex_counts",
    )
    seed: int | list[int] | None = Field(
        None,
        name="seed",
        description="Seed used for random subsampling method",
    )

    @field_validator("dim")
    @staticmethod
    def dim_check(v: int) -> int:
        if v <= 1:
            msg = "Simplex dimension must be greater than 1"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def check_n_count_max(self) -> Self:
        n_count_max = self.n_count_max
        if self.subsample and n_count_max is None:
            msg = "n_count_max must be specified when subsample is True"
            raise ValueError(msg)
        return self

    def _get_expression(self, circuit: Circuit, population: str) -> dict:
        if "simplex_submat" not in globals():
            msg = (
                "Import of 'simplex_submat' failed. You probably need to install connalysis"
                " locally."
            )
            raise ValueError(msg)

        self.check_properties(circuit, population)
        self.check_node_sets(circuit, population)
        # Always needs to be resolved
        base_expression = self._get_resolved_expression(circuit, population)

        # Restrict connectivity matrix to chosen subpopulation and find index of center
        conn = circuit.connectivity_matrix.subpopulation(base_expression["node_id"])
        index = np.where(conn.vertices["node_ids"] == self.central_neuron_id)[0]
        if len(index) == 0:
            msg = (
                f"The neuron of index {self.central_neuron_id} is not in the subpopulation selected"
            )
            raise ValueError(msg)
        index = index[0]

        # Get nodes on simplices index by 0 ... conn._shape[0]
        selection = simplex_submat(
            conn.matrix,
            index,
            self.dim,
            v_position=self.central_neuron_simplex_position,
            subsample=self.subsample,
            n_count_max=self.n_count_max,
            subsample_method="sample_simplices",
            simplex_type=self.simplex_type,
            seed=self.seed,
        )

        # Get node_ids (i.e., get correct index) and build expression dict
        selection = conn.vertices["node_ids"].iloc[selection]
        expression = {"population": population, "node_id": selection.tolist()}
        return expression
