import json
import logging
import os

import numpy  # NOQA: ICN001
import pandas  # NOQA: ICN001
from entitysdk import Client
from matplotlib import pyplot as plt

from obi_one.config import settings
from obi_one.core.task import Task
from obi_one.scientific.from_id.em_dataset_from_id import EMDataSetFromID
from obi_one.scientific.library.map_em_synapses._defaults import (
    default_node_spec_for,
    sonata_config_for,
)
from obi_one.scientific.library.map_em_synapses.map_synapse_locations import (
    map_afferents_to_spiny_morphology,
)
from obi_one.scientific.library.map_em_synapses.write_sonata_edge_file import (
    _STR_POST_NODE,
    _STR_PRE_NODE,
    write_edges,
)
from obi_one.scientific.library.map_em_synapses.write_sonata_nodes_file import (
    assemble_collection_from_specs,
    write_nodes,
)
from obi_one.scientific.tasks.em_synapse_mapping.config import EMSynapseMappingSingleConfig
from obi_one.scientific.tasks.em_synapse_mapping.dataframes_from_em import (
    synapses_and_nodes_dataframes_from_EM,
)
from obi_one.scientific.tasks.em_synapse_mapping.plot import (
    plot_mapping_stats,
)
from obi_one.scientific.tasks.em_synapse_mapping.register import (
    register_output,
)
from obi_one.scientific.tasks.em_synapse_mapping.resolve_neuron import (
    resolve_neuron,
)
from obi_one.scientific.tasks.em_synapse_mapping.util import (
    compress_output,
    merge_spiny_morphologies,
)

L = logging.getLogger(__name__)


class EMSynapseMappingTask(Task):
    """EM synapse mapping task for one or more neurons.

    Produces a SONATA circuit with:
    - A biophysical node population containing all N neurons
    - A virtual node population for presynaptic neurons not in the set
    - When N >= 2: internal edges (biophysical -> biophysical) for connections within the set
    - External edges (virtual -> biophysical) for inputs from outside the set
    """

    config: EMSynapseMappingSingleConfig

    def execute(  # NOQA: PLR0914, PLR0915, C901, PLR0912
        self,
        *,
        db_client: Client = None,
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,
    ) -> None:
        if db_client is None:
            err_str = "Synapse lookup and mapping requires a working db_client"
            raise ValueError(err_str)

        execution_activity = EMSynapseMappingTask._get_execution_activity(
            db_client=db_client, execution_activity_id=execution_activity_id
        )

        cfg = self.config
        init = cfg.initialize
        advanced = cfg.advanced_options

        if custom_virtual_edge_population_name != "":
            advanced.custom_virtual_edge_population_name = custom_virtual_edge_population_name
        if custom_physical_edge_population_name != "":
            advanced.custom_physical_edge_population_name = custom_physical_edge_population_name
        if custom_biophysical_node_population != "":
            advanced.custom_biophysical_node_population = custom_biophysical_node_population
        if custom_virtual_node_population != "":
            advanced.custom_virtual_node_population = custom_virtual_node_population

        # Prepare output location
        out_root = cfg.coordinate_output_root
        L.info(f"Preparing output at {out_root}...")
        morph_dir = out_root / "morphologies"
        swc_morph_subdir = morph_dir / "morphology"
        swc_morph_subdir.mkdir(parents=True, exist_ok=True)

        # Resolve all neurons: morphology, provenance, ME model
        L.info("Resolving neurons...")
        resolved_neurons = []
        all_pt_root_ids = set()

        for neuron_entry in init.neurons:
            resolved_neuron = resolve_neuron(
                neuron_entry,
                db_client,
                out_root,
            )
            resolved_neurons.append(resolved_neuron)
            all_pt_root_ids.add(resolved_neuron.pt_root_id)

        n_neurons = len(resolved_neurons)
        is_multi = n_neurons > 1

        # All neurons must come from the same EM dataset
        dataset_ids = {rn.source_dataset.id for rn in resolved_neurons}
        if len(dataset_ids) != 1:
            err_str = "All neurons must originate from the same EM dense reconstruction dataset."
            raise ValueError(err_str)

        source_dataset = resolved_neurons[0].source_dataset
        cave_version = resolved_neurons[0].cave_version
        em_dataset = EMDataSetFromID(
            id_str=str(source_dataset.id),
            auth_token=os.environ[settings.cave_client_config.microns_api_key],
        )

        # Merge spiny morphologies into a single file (for multi-neuron)
        fn_merged_h5 = "morphologies/merged_spiny_morphologies.h5" if is_multi else None
        if is_multi:
            L.info("Merging spiny morphologies into combined file...")
            merge_spiny_morphologies(
                source_files=[out_root / rn.fn_morph_h5 for rn in resolved_neurons],
                output_path=out_root / fn_merged_h5,
                include_meshes=False,
            )

        L.info("Reading data from source EM reconstructions...")
        pt_root_to_bio_id = {rn.pt_root_id: idx for idx, rn in enumerate(resolved_neurons)}
        all_internal_edges = []
        all_internal_pre_post = []
        all_external_edges = []
        all_external_pre_post = []
        all_external_pre_pt_roots = set()
        all_notices = []

        for bio_node_id, rn in enumerate(resolved_neurons):
            pt_root_id = rn.pt_root_id
            L.info(f"Mapping synapses onto morphology {bio_node_id}...")

            syns, _coll_pre, _coll_post, notices = synapses_and_nodes_dataframes_from_EM(
                em_dataset, pt_root_id, db_client, cave_version
            )

            all_notices.extend(notices)

            mapped_synapses_df, mesh_res = map_afferents_to_spiny_morphology(
                rn.spiny_morph, syns, add_quality_info=True
            )

            stats_name = (
                f"mapping_stats_neuron_{bio_node_id}.png" if is_multi else "mapping_stats.png"
            )
            plot_mapping_stats(mapped_synapses_df, mesh_res).savefig(out_root / stats_name)
            plt.close("all")

            # Split synapses: internal (pre is in the set) vs external
            is_internal = syns["pre_pt_root_id"].isin(all_pt_root_ids)

            for is_int, edge_list, pre_post_list in [
                (True, all_internal_edges, all_internal_pre_post),
                (False, all_external_edges, all_external_pre_post),
            ]:
                mask = is_internal if is_int else ~is_internal
                if mask.sum() == 0:
                    continue

                syn_subset = syns.loc[mask]
                mapped_subset = mapped_synapses_df.loc[mask]

                pre_post = pandas.DataFrame(index=syn_subset.index)
                pre_post[_STR_POST_NODE] = bio_node_id

                if is_int:
                    pre_post[_STR_PRE_NODE] = (
                        syn_subset["pre_pt_root_id"].map(pt_root_to_bio_id).to_numpy()
                    )
                else:
                    pre_post["pre_pt_root_id"] = syn_subset["pre_pt_root_id"].to_numpy()
                    all_external_pre_pt_roots.update(syn_subset["pre_pt_root_id"].unique())

                edge_list.append(mapped_subset)
                pre_post_list.append(pre_post.reset_index(drop=True))

        # Build virtual node ID mapping for external neurons
        external_pt_roots_sorted = sorted(all_external_pre_pt_roots)
        ext_pt_root_to_virtual_id = {pt: idx for idx, pt in enumerate(external_pt_roots_sorted)}

        for idx, pp_df in enumerate(all_external_pre_post):
            if "pre_pt_root_id" in pp_df.columns:
                pp_df[_STR_PRE_NODE] = (
                    pp_df["pre_pt_root_id"].map(ext_pt_root_to_virtual_id).to_numpy()
                )
                all_external_pre_post[idx] = pp_df.drop(columns=["pre_pt_root_id"])

        # Build node collections
        L.info("Building node collections...")
        node_spec = default_node_spec_for(em_dataset, db_client)

        bio_pt_root_mapping = pandas.DataFrame(
            {"index": range(n_neurons)},
            index=pandas.Index([rn.pt_root_id for rn in resolved_neurons], name="pre_pt_root_id"),
        )
        coll_bio, _ = assemble_collection_from_specs(
            em_dataset, db_client, cave_version, node_spec, bio_pt_root_mapping
        )

        morph_names = [f"morphology/{rn.morph_entity.name}" for rn in resolved_neurons]
        coll_bio.properties["morphology"] = numpy.array(morph_names)

        for bio_idx, rn in enumerate(resolved_neurons):
            if rn.phys_node_props:
                for col, vals in rn.phys_node_props.items():
                    if col not in coll_bio.properties:
                        if vals.dtype.kind == "f":
                            coll_bio.properties[col] = numpy.full(
                                n_neurons, numpy.nan, dtype=vals.dtype
                            )
                        elif vals.dtype.kind in {"i", "u"}:
                            coll_bio.properties[col] = numpy.full(n_neurons, -1, dtype=vals.dtype)
                        else:
                            coll_bio.properties[col] = numpy.full(n_neurons, "", dtype=vals.dtype)
                    coll_bio.properties[col][bio_idx] = vals[0]

        if external_pt_roots_sorted:
            virt_pt_root_mapping = pandas.DataFrame(
                {"index": range(len(external_pt_roots_sorted))},
                index=pandas.Index(external_pt_roots_sorted, name="pre_pt_root_id"),
            )
            coll_virtual, _ = assemble_collection_from_specs(
                em_dataset, db_client, cave_version, node_spec, virt_pt_root_mapping
            )
        else:
            coll_virtual = None

        # Write SONATA circuit files
        L.info("Writing the results...")
        fn_edges_out = "synaptome-edges.h5"
        fn_nodes_out = "synaptome-nodes.h5"
        pop_bio = init.biophysical_node_population
        pop_virt = init.virtual_node_population
        pop_edge_int = init.physical_edge_population_name
        pop_edge_ext = init.virtual_edge_population_name

        write_nodes(out_root / fn_nodes_out, pop_bio, coll_bio, write_mode="w")
        if coll_virtual is not None:
            write_nodes(out_root / fn_nodes_out, pop_virt, coll_virtual, write_mode="a")

        edges_path = out_root / fn_edges_out
        if edges_path.exists():
            edges_path.unlink()

        if all_internal_edges:
            int_edges_df = pandas.concat(all_internal_edges, axis=0, ignore_index=True)
            int_pre_post_df = pandas.concat(all_internal_pre_post, axis=0, ignore_index=True)
            write_edges(
                out_root / fn_edges_out,
                pop_edge_int,
                int_pre_post_df,
                int_edges_df,
                pop_bio,
                pop_bio,
            )

        if all_external_edges:
            ext_edges_df = pandas.concat(all_external_edges, axis=0, ignore_index=True)
            ext_pre_post_df = pandas.concat(all_external_pre_post, axis=0, ignore_index=True)
            write_edges(
                out_root / fn_edges_out,
                pop_edge_ext,
                ext_pre_post_df,
                ext_edges_df,
                pop_virt,
                pop_bio,
            )

        # Write circuit config
        edge_populations = {}
        if all_internal_edges:
            edge_populations[pop_edge_int] = {"type": "chemical"}
        if all_external_edges:
            edge_populations[pop_edge_ext] = {"type": "chemical"}

        sonata_cfg = sonata_config_for(
            fn_edges_out,
            fn_nodes_out,
            edge_populations=edge_populations,
            biophysical_population=pop_bio,
            virtual_population=pop_virt if coll_virtual is not None else None,
            morphologies_dir="morphologies",
            alternate_morphologies_h5=(
                str(resolved_neurons[0].fn_morph_h5) if not is_multi else None
            ),
        )
        with (out_root / "circuit_config.json").open("w") as fid:
            json.dump(sonata_cfg, fid, indent=2)

        # Register entity, if possible
        L.info("Registering the output...")
        total_synapses = sum(len(df) for df in all_internal_edges + all_external_edges)
        total_connections = sum(
            len(df.drop_duplicates()) for df in all_internal_pre_post + all_external_pre_post
        )
        total_internal = sum(len(df) for df in all_internal_pre_post)
        total_external = sum(len(df) for df in all_external_pre_post)

        file_paths = {
            "circuit_config.json": str(out_root / "circuit_config.json"),
            fn_nodes_out: str(out_root / fn_nodes_out),
            fn_edges_out: str(out_root / fn_edges_out),
        }
        if fn_merged_h5 is not None:
            file_paths[fn_merged_h5] = str(out_root / fn_merged_h5)

        for bio_idx in range(n_neurons):
            stats_name = f"mapping_stats_neuron_{bio_idx}.png" if is_multi else "mapping_stats.png"
            stats_path = out_root / stats_name
            if stats_path.exists():
                file_paths[stats_name] = str(stats_path)
        for rn in resolved_neurons:
            for rel in (rn.fn_morph_h5, rn.fn_morph_swc):
                file_paths[str(rel)] = str(out_root / rel)

        compress_files = [
            str(out_root / "circuit_config.json"),
            str(out_root / fn_nodes_out),
            str(out_root / fn_edges_out),
        ]
        if fn_merged_h5 is not None:
            compress_files.append(str(out_root / fn_merged_h5))
        for rn in resolved_neurons:
            swc_path = out_root / rn.fn_morph_swc
            if swc_path.exists():
                compress_files.append(str(swc_path))
        compressed_path = compress_output(out_root, compress_files)

        registered_circuit_id = register_output(
            db_client=db_client,
            resolved_neurons=resolved_neurons,
            source_dataset=source_dataset,
            em_dataset=em_dataset,
            all_notices=all_notices,
            total_synapses=total_synapses,
            total_connections=total_connections,
            total_internal=total_internal,
            total_external=total_external,
            file_paths=file_paths,
            compressed_path=compressed_path,
        )

        # Update execution activity (if any)
        EMSynapseMappingTask._update_execution_activity(
            db_client=db_client,
            execution_activity=execution_activity,
            generated=[registered_circuit_id],
        )
