import logging
import pandas import pd
import h5py
from typing import Annotated, Never

import bluepysnap as snap
import numpy as np
from connectome_manipulator.model_building import model_types
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.synaptic_parameterization.base import SynapseParameterization
from obi_one.scientific.unions.unions_distributions import (
    SynapticParameterizationDistributionReference,
)

L = logging.getLogger(__name__)

from obi_one.core.block import Block

class TsodyksMarkramSynapseParameterization(Block):

    u_hill_coefficient_distribution: SynapticParameterizationDistributionReference = Field(
        title="U Hill Coefficient Distribution",
        description="Distribution of the Hill coefficient for the steady-state utilization"
        " of synaptic efficacy (u).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: SynapticParameterizationDistributionReference.__name__,
        },
    )

    u_hill_coefficient_shared_within: bool = Field(
        default=False,
        title="U Hill Coefficient Shared Within",
        description="Whether the Hill coefficient for the steady-state utilization of synaptic"
        " efficacy (u) is shared within the synapses between the source and target"
        " neuron sets.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN,
        },
    )

    gsyn_distribution: SynapticParameterizationDistributionReference = Field(
        title="g_syn Distribution",
        description="Distribution of synaptic conductance (g_syn).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: SynapticParameterizationDistributionReference.__name__,
        },
    )

    gsyn_distribution_shared_within: bool = Field(
        default=False,
        title="g_syn Distribution Shared Within",
        description="Whether the synaptic conductance (g_syn) is shared within the synapses"
        " between the source and target neuron sets.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN,
        },
    )

    @property
    def cov_mat(self) -> dict:
        return []

    @property
    def cov_dict(self) -> dict:
        return {}

    def u_hill_coefficient_dict(self) -> dict:
        d = self.u_hill_coefficient_distribution.resolve()
        d["shared_within"] = self.u_hill_coefficient_shared_within
        return d
    
    def gsyn_dict(self) -> dict:
        d = self.gsyn_distribution.resolve()
        d["shared_within"] = self.gsyn_distribution_shared_within
        return d


    def go_for_it(self, circ: snap.Circuit) -> Never:
        source_node_set = self.source_neuron_set.resolve(circ)
        target_node_set = self.target_neuron_set.resolve(circ)

        prop_stats = {
            "u_hill_coefficient": {source_node_set: {
                    target_node_set: self.u_hill_coefficient_dict()
                }},
            "gsyn": {source_node_set: {
                    target_node_set: self.gsyn_dict()
                }},
        }

        model1 = model_types.ConnPropsModel(
            src_types=[source_node_set],
            tgt_types=[target_node_set],
            prop_stats=prop_stats,
            prop_cov=self.cov_dict,
        )

        # Set random seed
        np.random.seed(self.random_seed)  # noqa: NPY002
        # TODO: Fix legacy np.random in connectome-manipulator code

        # Run parameterization
        edge_pop_names = circ.edges.population_names
        L.info(f"Running synapse parameterization for {len(edge_pop_names)} edge population(s)...")
        for edge_pop in edge_pop_names:
            edge = circ.edges[edge_pop]
            self._parameterize_edge_file(edge)


CORRELATION_COEFFICIENT_FIELD = (
    Annotated[
        float,
        Field(ge=-1.0, le=1.0),
    ]
    | Annotated[
        list[
            Annotated[
                float,
                Field(
                    ge=-1.0,
                    le=1.0,
                ),
            ]
        ],
        Field(min_length=1),
    ]
)


class CorrelatedTsodyksMarkramSynapseParameterization(TsodyksMarkramSynapseParameterization):
    u_hill_coefficient_and_gsyn_correlation: CORRELATION_COEFFICIENT_FIELD = Field(
        title="Correlation between U Hill Coefficient and g_syn",
        description="Correlation coefficient between the Hill coefficient and g_syn",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    @property
    def cov_mat(self) -> dict:
        return np.array(
            [
                [1.0, self.u_hill_coefficient_and_gsyn_correlation],
                [self.u_hill_coefficient_and_gsyn_correlation, 1.0],
            ]
        )

    @property
    def cov_dict(self) -> dict:
        return {
            "props": ["u_hill_coefficient", "gsyn"],
            "cov_mat": {self.source_neuron_set: {self.target_neuron_set: self.cov_mat}},
        }
