import os
import subprocess
import json
import numpy

from obi_one.scientific.library.map_em_synapses import (
    map_afferents_to_spiny_morphology, write_edges, write_nodes,
)
from obi_one.scientific.library.map_em_synapses.write_sonata_edge_file import (
    _STR_PRE_NODE, _STR_POST_NODE
)
from obi_one.scientific.library.map_em_synapses.write_sonata_nodes_file import (
    assemble_collection_from_specs
)
from obi_one.scientific.library.map_em_synapses._defaults import (
    default_node_spec_for,
    sonata_config_for
)

from entitysdk import Client
from entitysdk.models import EMCellMesh, EMDenseReconstructionDataset, Circuit
from entitysdk._server_schemas import CircuitBuildCategory, CircuitScale
from entitysdk._server_schemas import AssetLabel, ContentType

from neurom.io.utils import load_morphology_with_spines

from typing import ClassVar

from obi_one.core.scan_config import ScanConfig
from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphology, CellMorphologyFromID
from obi_one.scientific.from_id.em_dataset_from_id import EMDataSetFromID
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task


def plot_mapping_stats(mapped_synapses_df, mesh_res,
                       plt_max_dist=3.0, nbins=99):
    from matplotlib import pyplot as plt

    dbins = numpy.linspace(0, plt_max_dist, nbins)
    w = numpy.mean(numpy.diff(dbins))

    frst_dist = numpy.maximum(mapped_synapses_df["distance"], 0.0)
    sec_dist = mapped_synapses_df["competing_distance"]

    fig = plt.figure(figsize=(2.5, 4))
    ax = fig.add_subplot(2, 1, 1)

    ax.bar(dbins[1:], numpy.histogram(frst_dist, bins=dbins)[0], width=w, label="Dist.: Nearest structure")
    ax.bar(dbins[1:], numpy.histogram(sec_dist, bins=dbins)[0], width=w, label="Dist.: Second nearest structure")
    ymx = ax.get_ylim()[1] * 0.85
    ax.plot([mesh_res, mesh_res], [0, ymx], color="black", label="Mesh resolution")
    ax.set_ylabel("Synapse count")
    ax.set_frame_on(False)
    plt.legend()
    return fig


class EMSynapseMappingSingleConfig(OBIBaseModel, SingleConfigMixin):
    name : ClassVar[str] = "Map synapse locations"
    description : ClassVar[str] = "Map location of afferent synapses from EM onto a spiny morphology"
    cave_token : str | None = None

    class Initialize(Block):
        spiny_neuron : CellMorphologyFromID
        edge_population_name : str = "synaptome_afferents"
        node_population_pre : str = "synaptome_afferent_neurons"
        node_population_post : str = "biophysical_neuron"

    initialize : Initialize

# class EMSynapseMappingSingleConfig(EMSynapseMappingScanConfig, SingleConfigMixin):
#     pass

class EMSynapseMappingTask(Task):
    config : EMSynapseMappingSingleConfig

    def execute(self, db_client : Client = None):
        if db_client is None:
            raise ValueError("Synapse lookup and mapping requires a working db_client!")
        morph_entity = self.config.initialize.spiny_neuron.entity(db_client)
        
        # Prepare output location
        out_root = self.config.coordinate_output_root
        print(f"Preparing output at {out_root}...")
        os.makedirs(out_root / "morphologies/morphology", exist_ok=True)

        # Place and load morphologies
        print("Placing morphologies...")
        fn_morphology_out_h5 = os.path.join("morphologies", morph_entity.name + ".h5")
        fn_morphology_out_swc = os.path.join("morphologies/morphology", morph_entity.name + ".swc")
        self.config.initialize.spiny_neuron.write_spiny_neuron_h5(out_root / fn_morphology_out_h5,
                                                                  db_client=db_client)
        smooth_morph = self.config.initialize.spiny_neuron.neurom_morphology(db_client)
        smooth_morph.to_morphio().as_mutable().write(out_root / fn_morphology_out_swc)
        spiny_morph = load_morphology_with_spines(str(out_root / fn_morphology_out_h5))

        print("Resolving skeleton provenance...")
        pt_root_id, source_mesh_entity, source_dataset = self.resolve_provenance(db_client, morph_entity)

        cave_version=source_mesh_entity.release_version
        em_dataset = EMDataSetFromID(id_str=str(source_dataset.id),
                                     auth_token=self.config.cave_token)
        
        print("Reading data from source EM reconstruction...")
        syns, coll_pre, coll_post, lst_notices = self.synapses_and_nodes_dataframes_from_EM(em_dataset,
                                                                                            pt_root_id,
                                                                                            db_client,
                                                                                            cave_version)
        print("Mapping synapses onto morphology...")
        mapped_synapses_df, mesh_res = map_afferents_to_spiny_morphology(spiny_morph, syns, add_quality_info=True)

        pre_pt_root_to_sonata = syns["pre_pt_root_id"].drop_duplicates().reset_index(drop=True).reset_index().set_index("pre_pt_root_id")
        post_pt_root_to_sonata = syns["post_pt_root_id"].drop_duplicates().reset_index(drop=True).reset_index().set_index("post_pt_root_id")

        syn_pre_post_df = pre_pt_root_to_sonata.loc[syns["pre_pt_root_id"]].rename(columns={"index": _STR_PRE_NODE})
        syn_pre_post_df[_STR_POST_NODE] = 0
        syn_pre_post_df = syn_pre_post_df.reset_index(drop=True)

        print("Writing the results...")
        # Write the results
        # Mapping quality info
        plot_mapping_stats(mapped_synapses_df, mesh_res).savefig(out_root / "mapping_stats.png")
        # Edges h5 file
        fn_edges_out = "synaptome-edges.h5"
        edge_population_name = self.config.initialize.edge_population_name
        node_population_pre = self.config.initialize.node_population_pre
        node_population_post = self.config.initialize.node_population_post
        write_edges(out_root / fn_edges_out, edge_population_name, syn_pre_post_df,
                    mapped_synapses_df, node_population_pre, node_population_post)
        
        # Nodes h5 file
        coll_post.properties["morphology"] = f"morphology/{spiny_morph.name}"
        fn_nodes_out = "synaptome-nodes.h5"
        write_nodes(out_root / fn_nodes_out, node_population_pre, coll_pre, write_mode="w")
        write_nodes(out_root / fn_nodes_out, node_population_post, coll_post, write_mode="a")

        # Sonata config.json
        sonata_cfg = sonata_config_for(fn_edges_out, fn_nodes_out, edge_population_name,
                            node_population_pre, node_population_post,
                            fn_morphology_out_h5)
        with open(out_root / "circuit_config.json", "w") as fid:
            json.dump(sonata_cfg, fid, indent=2)

        # Register entity, if possible
        print("Registering the output...")
        file_paths = {
            "circuit_config.json": os.path.join(out_root, "circuit_config.json"),
            fn_nodes_out : os.path.join(out_root, fn_nodes_out),
            fn_edges_out: os.path.join(out_root, fn_edges_out),
            fn_morphology_out_h5: os.path.join(out_root, fn_morphology_out_h5),
            fn_morphology_out_swc: os.path.join(out_root, fn_morphology_out_swc)
        }
        compressed_path = self.compress_output()
        self.register_output(db_client, pt_root_id, mapped_synapses_df, syn_pre_post_df, source_dataset, file_paths, compressed_path)
        print("The following are the notices for the used data:")
        for notice in lst_notices:
            print(notice)
            print("\n")
        
    def synapses_and_nodes_dataframes_from_EM(self, em_dataset, pt_root_id, db_client, cave_version):
        # SYNAPSES
        syns, syns_notice = em_dataset.synapse_info_df(pt_root_id, cave_version,
                                                       col_location="post_pt_position",
                                                       db_client=db_client)
        # NODES
        pre_pt_root_to_sonata = syns["pre_pt_root_id"].drop_duplicates().reset_index(drop=True).reset_index().set_index("pre_pt_root_id")
        post_pt_root_to_sonata = syns["post_pt_root_id"].drop_duplicates().reset_index(drop=True).reset_index().set_index("post_pt_root_id")
        node_spec = default_node_spec_for(em_dataset, db_client)
        coll_pre, nodes_notice = assemble_collection_from_specs(em_dataset, db_client, cave_version, node_spec, pre_pt_root_to_sonata)
        coll_post, _ = assemble_collection_from_specs(em_dataset, db_client, cave_version, node_spec, post_pt_root_to_sonata)

        return syns, coll_pre, coll_post, [syns_notice] + nodes_notice


    def resolve_provenance(self, db_client, morph_entity):
        pt_root_id = int(morph_entity.name.split("-")[-1])
        source_mesh_entity = list(db_client.search_entity(entity_type=EMCellMesh, query={
                                    "dense_reconstruction_cell_id": pt_root_id
                                }))[0]
        source_dataset = db_client.get_entity(entity_id=source_mesh_entity.em_dense_reconstruction_dataset.id,
                                              entity_type=EMDenseReconstructionDataset)
        return pt_root_id, source_mesh_entity, source_dataset
    

    def compress_output(self):
        out_root = self.config.coordinate_output_root
        with open(out_root / "sonata.tar", "wb") as fid:
            fid.write(
                subprocess.check_output([
                    "tar",
                    "-c",
                    str(out_root)
                    ]
                )
            )
            subprocess.check_call([
                "gzip",
                "-1",
                str(out_root / "sonata.tar")
            ])
        return str(out_root / "sonata.tar.gz")
    

    def register_output(self, db_client, pt_root_id, mapped_synapses_df, syn_pre_post_df, source_dataset, file_paths, compressed_path):
        circ_entity = Circuit(
            name=f"Afferent-synaptome-{pt_root_id}",
            description=f"Morphology skeleton with isolated spines and afferent synapses (Synaptome) of the neuron with pt_root_id {pt_root_id} in dataset {source_dataset.name}",
            number_neurons=1,
            number_synapses=len(mapped_synapses_df),
            number_connections=len(syn_pre_post_df["pre_node_id"].drop_duplicates()),
            scale=CircuitScale.single,
            build_category=CircuitBuildCategory.em_reconstruction,
            subject=source_dataset.subject,
            has_morphologies=True,
            has_electrical_cell_models=False,
            has_spines=True,
            brain_region=source_dataset.brain_region,
            experiment_date=source_dataset.experiment_date
        )
        existing_circuit = db_client.register_entity(circ_entity)

        db_client.upload_directory(
            entity_id=existing_circuit.id,
            entity_type=Circuit,
            name="sonata_synaptome",
            paths=file_paths,
            label=AssetLabel.sonata_circuit
        )

        db_client.upload_file(entity_id=existing_circuit.id,
                   entity_type=Circuit,
                   file_path=compressed_path,
                   file_content_type=ContentType.application_gzip,
                   asset_label=AssetLabel.compressed_sonata_circuit)
        print(f"Output registered as: {existing_circuit.id}")





