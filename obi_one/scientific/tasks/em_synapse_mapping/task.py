import json
import logging
import shutil
from pathlib import Path

import numpy  # NOQA: ICN001
from entitysdk import Client
from entitysdk.downloaders.memodel import download_memodel
from morph_spines import load_morphology_with_spines

from obi_one.core.task import Task
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.em_dataset_from_id import EMDataSetFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.map_em_synapses import (
    map_afferents_to_spiny_morphology,
    write_edges,
    write_nodes,
)
from obi_one.scientific.library.map_em_synapses._defaults import (
    sonata_config_for,
)
from obi_one.scientific.library.map_em_synapses.write_sonata_edge_file import (
    _STR_POST_NODE,
    _STR_PRE_NODE,
)
from obi_one.scientific.tasks.em_synapse_mapping.config import EMSynapseMappingSingleConfig
from obi_one.scientific.tasks.em_synapse_mapping.plot import plot_mapping_stats
from obi_one.scientific.tasks.em_synapse_mapping.provenance import (
    resolve_provenance,
)
from obi_one.scientific.tasks.em_synapse_mapping.util import compress_output

L = logging.getLogger(__name__)


class EMSynapseMappingTask(Task):
    config: EMSynapseMappingSingleConfig

    def execute(  # NOQA: PLR0914, PLR0915
        self,
        *,
        db_client: Client = None,
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,
    ) -> None:
        if db_client is None:
            err_str = "Synapse lookup and mapping requires a working db_client!"
            raise ValueError(err_str)

        # NEW
        execution_activity = EMSynapseMappingTask._get_execution_activity(
            db_client=db_client, execution_activity_id=execution_activity_id
        )

        use_me_model = isinstance(self.config.initialize.spiny_neuron, MEModelFromID)
        if use_me_model:
            me_model_entity = self.config.initialize.spiny_neuron.entity(db_client)
            morph_entity = me_model_entity.morphology
            id_str = str(morph_entity.id)
            morph_from_id = CellMorphologyFromID(id_str=id_str)
        else:
            morph_entity = self.config.initialize.spiny_neuron.entity(db_client)
            morph_from_id = self.config.initialize.spiny_neuron

        # Prepare output location
        out_root = self.config.coordinate_output_root
        L.info(f"Preparing output at {out_root}...")
        (out_root / "morphologies/morphology").mkdir(parents=True)

        # Place and load morphologies
        L.info("Placing morphologies...")
        fn_morphology_out_h5 = Path("morphologies") / (morph_entity.name + ".h5")
        fn_morphology_out_swc = Path("morphologies/morphology") / (morph_entity.name + ".swc")
        morph_from_id.write_spiny_neuron_h5(out_root / fn_morphology_out_h5, db_client=db_client)
        smooth_morph = morph_from_id.neurom_morphology(db_client)
        smooth_morph.to_morphio().as_mutable().write(out_root / fn_morphology_out_swc)
        spiny_morph = load_morphology_with_spines(str(out_root / fn_morphology_out_h5))

        phys_node_props = {}
        if use_me_model:
            L.info("Placing mechanisms and .hoc file...")
            tmp_staging = out_root / "temp_staging"
            memdl_paths = download_memodel(db_client, me_model_entity, tmp_staging)
            shutil.move(memdl_paths.mechanisms_dir, out_root / "mechanisms")
            (out_root / "hoc").mkdir(parents=True)
            shutil.move(memdl_paths.hoc_path, out_root / "hoc")
            shutil.rmtree(tmp_staging)
            phys_node_props["model_template"] = numpy.array([f"hoc:{memdl_paths.hoc_path.stem}"])
            phys_node_props["model_type"] = numpy.array([0], dtype=numpy.int32)
            phys_node_props["morph_class"] = numpy.array([0], dtype=numpy.int32)
            if me_model_entity.calibration_result is not None:
                phys_node_props["threshold_current"] = numpy.array(
                    [me_model_entity.calibration_result.threshold_current], dtype=numpy.float32
                )
                phys_node_props["holding_current"] = numpy.array(
                    [me_model_entity.calibration_result.holding_current], dtype=numpy.float32
                )

        L.info("Resolving skeleton provenance...")
        pt_root_id, source_mesh_entity, source_dataset = resolve_provenance(
            db_client, morph_from_id
        )

        cave_version = source_mesh_entity.release_version

        em_dataset = EMDataSetFromID(
            id_str=str(source_dataset.id), auth_token=self.config.cave_token
        )

        L.info("Reading data from source EM reconstruction...")
        syns, coll_pre, coll_post, lst_notices = self.synapses_and_nodes_dataframes_from_EM(
            em_dataset, pt_root_id, db_client, cave_version
        )
        L.info("Mapping synapses onto morphology...")
        mapped_synapses_df, mesh_res = map_afferents_to_spiny_morphology(
            spiny_morph, syns, add_quality_info=True
        )

        pre_pt_root_to_sonata = (
            syns["pre_pt_root_id"]
            .drop_duplicates()
            .reset_index(drop=True)
            .reset_index()
            .set_index("pre_pt_root_id")
        )
        post_pt_root_to_sonata = (  # NOQA: F841
            syns["post_pt_root_id"]
            .drop_duplicates()
            .reset_index(drop=True)
            .reset_index()
            .set_index("post_pt_root_id")
        )

        syn_pre_post_df = pre_pt_root_to_sonata.loc[syns["pre_pt_root_id"]].rename(
            columns={"index": _STR_PRE_NODE}
        )
        syn_pre_post_df[_STR_POST_NODE] = 0
        syn_pre_post_df = syn_pre_post_df.reset_index(drop=True)

        L.info("Writing the results...")
        # Write the results
        # Mapping quality info
        plot_mapping_stats(mapped_synapses_df, mesh_res).savefig(out_root / "mapping_stats.png")
        # Edges h5 file
        fn_edges_out = "synaptome-edges.h5"
        edge_population_name = self.config.initialize.edge_population_name
        node_population_pre = self.config.initialize.node_population_pre
        node_population_post = self.config.initialize.node_population_post
        write_edges(
            out_root / fn_edges_out,
            edge_population_name,
            syn_pre_post_df,
            mapped_synapses_df,
            node_population_pre,
            node_population_post,
        )

        # Nodes h5 file
        coll_post.properties["morphology"] = f"morphology/{spiny_morph.morphology.name}"
        if use_me_model:
            for col, vals in phys_node_props.items():
                coll_post.properties[col] = vals
        fn_nodes_out = "synaptome-nodes.h5"
        write_nodes(out_root / fn_nodes_out, node_population_pre, coll_pre, write_mode="w")
        write_nodes(out_root / fn_nodes_out, node_population_post, coll_post, write_mode="a")

        # Sonata config.json
        sonata_cfg = sonata_config_for(
            fn_edges_out,
            fn_nodes_out,
            edge_population_name,
            node_population_pre,
            node_population_post,
            str(fn_morphology_out_h5),
        )
        with (out_root / "circuit_config.json").open("w") as fid:
            json.dump(sonata_cfg, fid, indent=2)

        # Register entity, if possible
        L.info("Registering the output...")
        file_paths = {
            "circuit_config.json": str(out_root / "circuit_config.json"),
            fn_nodes_out: str(out_root / fn_nodes_out),
            fn_edges_out: str(out_root / fn_edges_out),
            fn_morphology_out_h5: str(out_root / fn_morphology_out_h5),
            fn_morphology_out_swc: str(out_root / fn_morphology_out_swc),
        }
        compressed_path = compress_output(self.config.coordinate_output_root)

        registered_circuit_id = self.register_output(
            db_client,
            pt_root_id,
            mapped_synapses_df,
            syn_pre_post_df,
            source_dataset,
            em_dataset.entity(db_client),
            lst_notices,
            file_paths,
            compressed_path,
        )

        # Update execution activity (if any)
        EMSynapseMappingTask._update_execution_activity(
            db_client=db_client,
            execution_activity=execution_activity,
            generated=[registered_circuit_id],
        )
