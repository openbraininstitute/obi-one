import logging
import shutil
from pathlib import Path
from typing import ClassVar

import bluepysnap as snap
import h5py
import numpy as np
import pandas as pd
from connectome_manipulator.model_building import model_types
from entitysdk import Client, models
from pydantic import Field, PrivateAttr

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.from_id.circuit_from_id import MEModelWithSynapsesCircuitFromID
from obi_one.scientific.library.memodel_circuit import MEModelWithSynapsesCircuit

L = logging.getLogger(__name__)


class SynapseParameterizationSingleConfig(OBIBaseModel, SingleConfigMixin):
    name: ClassVar[str] = "Synapse parameterization"
    description: ClassVar[str] = (
        "Generates a physiological parameterization of an anatomical synaptome or replaces an"
        " existing paramterization."
    )

    class Initialize(Block):
        synaptome: MEModelWithSynapsesCircuitFromID = Field(
            title="Synaptome",
            description="Synaptome (i.e., circuit of scale single) to (re-)parameterize.",
        )
        pathway_property: str = Field(
            title="Pathway property",
            description="Neuron property (e.g., 'synapse_class') by which to group neurons into"
            " pathways between source and target neuron populations.",
        )
        pathway_param_dict: dict = Field(
            title="Pathway parameters",
            description="Synapse physiology distribution parameters for all pathways in the"
            " ConnPropsModel format of Connectome-Manipulator.",
        )  # TODO: This may be replaced by dedicated entities
        random_seed: int = Field(
            default=1,
            title="Random seed",
            description="Seed for drawing random values from physiological parameter"
            " distributions.",
        )
        overwrite_if_exists: bool = Field(
            title="Overwrite",
            description="Overwrite if a parameterization exists already.",
            default=False,
        )

    initialize: Initialize


class SynapseParameterizationTask(Task):
    config: SynapseParameterizationSingleConfig
    _synaptome: MEModelWithSynapsesCircuit | None = PrivateAttr(default=None)
    _synaptome_entity: models.Circuit | None = PrivateAttr(default=None)
    _pathway_model: model_types.ConnPropsModel | None = PrivateAttr(default=None)

    def _stage_synaptome(self, *, db_client: Client, entity_cache: bool) -> Path:
        self._synaptome_entity = self.config.initialize.synaptome.entity(db_client=db_client)
        root_dir = self.config.scan_output_root.resolve()
        output_dir = self.config.coordinate_output_root.resolve()

        if entity_cache:
            # Use a cache directory at the campaign root --> Won't be deleted after extraction!
            L.info("Using entity cache")
            stage_dir = (
                root_dir / "entity_cache" / "sonata_circuit" / str(self._synaptome_entity.id)
            )
        else:
            # Stage circuit directly in output directory --> Modify in-place!
            stage_dir = output_dir

        synaptome = self.config.initialize.synaptome.stage_circuit(
            db_client=db_client, dest_dir=stage_dir, entity_cache=entity_cache
        )

        if output_dir != stage_dir:
            # Copy staged circuit into output directory
            shutil.copytree(stage_dir, output_dir, dirs_exist_ok=False)
            synaptome = MEModelWithSynapsesCircuit(
                name=synaptome.name, path=str(output_dir / "circuit_config.json")
            )

        self._synaptome = synaptome

        return output_dir

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
        pathway_property = self.config.initialize.pathway_property
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
                    if self.config.initialize.overwrite_if_exists:
                        msg += "Re-parameterizing synapses."
                        L.info(msg)
                        edge_grp["0"][col][...] = new_values
                    else:
                        msg += "Choose 'overwrite' to re-parameterize synapses!"
                        raise ValueError(msg)
                else:
                    edge_grp["0"].create_dataset(col, data=new_values)

    def execute(self, *, db_client: Client = None, entity_cache: bool = False) -> None:
        if db_client is None:
            msg = "The synapse parameterization task requires a working db_client!"
            raise ValueError(msg)

        # Stage synaptome
        output_dir = self._stage_synaptome(db_client=db_client, entity_cache=entity_cache)

        # Check parameters
        circ = self._synaptome.sonata_circuit
        pathway_property = self.config.initialize.pathway_property
        if pathway_property not in circ.nodes.property_names:
            msg = f"Unknown pathway property '{pathway_property}'!"
            raise ValueError(msg)
        type_values = circ.nodes.property_values(pathway_property)
        if not all(
            _t in self.config.initialize.pathway_param_dict.get("src_types", [])
            for _t in type_values
        ):
            msg = f"Source type(s) missing in pathway parameter dict! Must contain: {type_values}"
            raise ValueError(msg)
        if not all(
            _t in self.config.initialize.pathway_param_dict.get("tgt_types", [])
            for _t in type_values
        ):
            msg = f"Target type(s) missing in pathway parameter dict! Must contain: {type_values}"
            raise ValueError(msg)

        # Initialize pathway parameter model
        self._pathway_model = model_types.ConnPropsModel(
            **self.config.initialize.pathway_param_dict
        )
        model_str = str(self._pathway_model)
        model_str = model_str.replace("M-types:", f"'{pathway_property}' pathways:")
        L.info(model_str)

        # Set random seed
        np.random.seed(self.config.initialize.random_seed)  # noqa: NPY002
        # TODO: Fix legacy np.random in connectome-manipulator code

        # Run parameterization
        edge_pop_names = circ.edges.population_names
        L.info(f"Running synapse parameterization for {len(edge_pop_names)} edge population(s)...")
        for edge_pop in edge_pop_names:
            edge = circ.edges[edge_pop]
            self._parameterize_edge_file(edge)

        # TODO: Register (re-)parameterized synaptome
