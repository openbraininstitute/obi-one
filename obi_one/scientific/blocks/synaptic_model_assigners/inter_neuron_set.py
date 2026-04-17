import logging

import bluepysnap as snap
import h5py
import numpy as np
import pandas as pd
from connectome_manipulator.model_building import model_types
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.synaptic_model_assigners.base import SynapseModelAssigner
from obi_one.scientific.unions.unions_neuron_sets import NeuronSetReference
from obi_one.scientific.unions.unions_synaptic_models import (
    SynapticModelReference,
)

L = logging.getLogger(__name__)


class InterNeuronSetSynapticModelAssigner(SynapseModelAssigner):
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

    synaptic_model: SynapticModelReference = Field(
        title="Synaptic Model",
        description="Synaptic model to assign to the synapses between the source and target"
        " neuron sets.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: SynapticModelReference.__name__,
        },
    )

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
        # Get pathway source/target values
        pathway_property = self.pathway_property
        if pathway_property not in edge.source.property_names:
            msg = (
                f"Pathway property '{pathway_property}' not found in source nodes:"
                f" Skipping edge population '{edge.name}'!"
            )
            L.warning(msg)
            return
        if pathway_property not in edge.target.property_names:
            msg = (
                f"Pathway property '{pathway_property}' not found in target nodes:"
                f" Skipping edge population '{edge.name}'!"
            )
            L.warning(msg)
            return
        cls_src = edge.source.get(properties=pathway_property)
        cls_tgt = edge.target.get(properties=pathway_property)

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

    def assign_synaptic_model(self, circ: snap.Circuit) -> None:
        source_node_set = self.source_neuron_set.resolve(circ)
        target_node_set = self.target_neuron_set.resolve(circ)

        prop_stats = {}
        for param_name, param_dict in self.synaptic_model.block.parameter_dictionaries().items:
            prop_stats[param_name] = {source_node_set: {target_node_set: param_dict}}

        self._pathway_model = model_types.ConnPropsModel(
            src_types=[source_node_set],
            tgt_types=[target_node_set],
            prop_stats=prop_stats,
            prop_cov=self.synaptic_model.cov_dict,
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
