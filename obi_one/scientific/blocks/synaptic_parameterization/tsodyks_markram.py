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
from obi_one.scientific.unions.unions_neuron_sets import NeuronSetReference

L = logging.getLogger(__name__)


class TsodyksMarkramSynapseParameterization(SynapseParameterization):
    source_neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Source)",
        description="Source neuron set to simulate",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: NeuronSetReference.__name__,
            SchemaKey.SUPPORTS_VIRTUAL: True,
        },
    )

    targeted_neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Target)",
        description="Target neuron set to simulate",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: NeuronSetReference.__name__,
            SchemaKey.SUPPORTS_VIRTUAL: False,
        },
    )

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
    
    def _wrap_get_model_output(
        self, cls_src: pd.Series, cls_tgt: pd.Series, row: pd.Series
    ) -> pd.DataFrame:
        src_type = cls_src[row["source"]]
        tgt_type = cls_tgt[row["target"]]
        idx = row["index"]

        mdl = self._pathway_model.get_model_output(
            src_type=src_type, tgt_type=tgt_type, n_syn=len(idx)
        )
        mdl["_index"] = idx
        return mdl
    
    def _parameterize_edge_file(self, edge: snap.edges.EdgePopulation) -> None:
    #     # Get pathway source/target values
    #     pathway_property = self.pathway_property
    #     if pathway_property not in edge.source.property_names:
    #         msg = (
    #             f"Pathway property '{pathway_property}' not found in source nodes:"
    #             f" Skipping edge population '{edge.name}'!"
    #         )
    #         L.warning(msg)
    #         return
    #     if pathway_property not in edge.target.property_names:
    #         msg = (
    #             f"Pathway property '{pathway_property}' not found in target nodes:"
    #             f" Skipping edge population '{edge.name}'!"
    #         )
    #         L.warning(msg)
    #         return
    #     cls_src = edge.source.get(properties=pathway_property)
    #     cls_tgt = edge.target.get(properties=pathway_property)

        # Open edge file
        edge_prefix = f"edges/{edge.name}"
        with h5py.File(edge.h5_filepath, "a") as h5:
            edge_grp = h5[edge_prefix]

            # Get connectivity
            src_ids = edge_grp["source_node_id"]
            tgt_ids = edge_grp["target_node_id"]
            src_tgt_df = pd.DataFrame(
                {"source": src_ids, "target": tgt_ids, "index": range(len(src_ids))}
            )
            src_tgt_df = src_tgt_df.groupby(["source", "target"])["index"].apply(list).reset_index()

            # Draw values
            drawn_values = [
                self._wrap_get_model_output(cls_src, cls_tgt, src_tgt_df.iloc[i])
                for i in range(len(src_tgt_df))
            ]
            new_props = pd.concat(drawn_values, axis=0).set_index("_index", drop=True).sort_index()
            for col in new_props.columns:
                new_values = new_props[col].to_numpy()
                if col in edge_grp["0"]:
                    msg = (
                        f"Synapse property '{col}' already exists in edge population"
                        f" '{edge.name}': "
                    )
                    if self.overwrite_if_exists:
                        msg += "Re-parameterizing synapses."
                        L.info(msg)
                        edge_grp["0"][col][...] = new_values
                    else:
                        msg += "Choose 'overwrite' to re-parameterize synapses!"
                        raise ValueError(msg)
                else:
                    edge_grp["0"].create_dataset(col, data=new_values)

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
