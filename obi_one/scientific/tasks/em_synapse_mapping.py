import json
import logging
import os
import shutil
import subprocess  # NOQA: S404
from pathlib import Path
from typing import ClassVar

import numpy  # NOQA: ICN001
import pandas  # NOQA: ICN001
from entitysdk import Client
from entitysdk._server_schemas import (
    AssetLabel,  # NOQA: PLC2701
    CircuitBuildCategory,  # NOQA: PLC2701
    CircuitScale,  # NOQA: PLC2701
    ContentType,  # NOQA: PLC2701
    PublicationType,  # NOQA: PLC2701
)
from entitysdk.downloaders.memodel import download_memodel
from entitysdk.models import (
    CellMorphology,
    Circuit,
    EMCellMesh,
    EMDenseReconstructionDataset,
    Publication,
    ScientificArtifactPublicationLink,
)
from matplotlib import pyplot as plt
from morph_spines import load_morphology_with_spines
from pydantic import Field
from voxcell import CellCollection

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.single import SingleConfigMixin
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
    default_node_spec_for,
    sonata_config_for,
)
from obi_one.scientific.library.map_em_synapses.write_sonata_edge_file import (
    _STR_POST_NODE,
    _STR_PRE_NODE,
)
from obi_one.scientific.library.map_em_synapses.write_sonata_nodes_file import (
    assemble_collection_from_specs,
)

L = logging.getLogger(__name__)


def plot_mapping_stats(
    mapped_synapses_df: pandas.DataFrame,
    mesh_res: float,
    plt_max_dist: float = 3.0,
    nbins: int = 99,
) -> plt.Figure:
    dbins = numpy.linspace(0, plt_max_dist, nbins)
    w = numpy.mean(numpy.diff(dbins))

    frst_dist = numpy.maximum(mapped_synapses_df["distance"], 0.0)
    sec_dist = mapped_synapses_df["competing_distance"]

    fig = plt.figure(figsize=(2.5, 4))
    ax = fig.add_subplot(2, 1, 1)

    ax.bar(
        dbins[1:],
        numpy.histogram(frst_dist, bins=dbins)[0],
        width=w,
        label="Dist.: Nearest structure",
    )
    ax.bar(
        dbins[1:],
        numpy.histogram(sec_dist, bins=dbins)[0],
        width=w,
        label="Dist.: Second nearest structure",
    )
    ymx = ax.get_ylim()[1] * 0.85
    ax.plot([mesh_res, mesh_res], [0, ymx], color="black", label="Mesh resolution")
    ax.set_ylabel("Synapse count")
    ax.set_frame_on(False)
    plt.legend()
    return fig


def assemble_publication_links(
    db_client: Client,
    em_dataset: EMDenseReconstructionDataset,
    lst_notices: list[str],  # NOQA: ARG001
) -> list[Publication]:
    src_links = db_client.search_entity(
        entity_type=ScientificArtifactPublicationLink,
        query={"scientific_artifact__id": em_dataset.id},
    ).all()
    src_pubs = [
        _x.publication for _x in src_links if _x.publication_type != PublicationType.application
    ]
    # TODO: Parse DOIs out of the lst_notices. Create publications for them.
    return src_pubs


class EMSynapseMappingSingleConfig(OBIBaseModel, SingleConfigMixin):
    name: ClassVar[str] = "Map synapse locations"
    description: ClassVar[str] = "Map location of afferent synapses from EM onto a spiny morphology"
    cave_token: str | None = Field(
        default=None,
        title="CAVEclient access token",
        description="""Token to authenticate access to the EM dataset with.
        If a token is stored in a secrets file, this does not need to be provided.
        See: https://caveclient.readthedocs.io/en/latest/guide/authentication.html""",
    )

    class Initialize(Block):
        spiny_neuron: CellMorphologyFromID | MEModelFromID = Field(
            title="EM skeletonized morphology",
            description="""A neuron morphology with spines obtained from an electron-microscopy
            datasets through the skeletonization task.""",
        )
        edge_population_name: str = Field(
            title="Edge population name",
            description="Name of the edge population to write the synapse information into",
            default="synaptome_afferents",
        )
        node_population_pre: str = Field(
            title="Presynaptic node population name",
            description="""Name of the node population to write the information about the
            innervating neurons into""",
            default="synaptome_afferent_neurons",
        )
        node_population_post: str = Field(
            title="Postsynaptic node population name",
            description="""Name of the node population to write the information about the
            synaptome neuron into""",
            default="biophysical_neuron",
        )

    initialize: Initialize


# class EMSynapseMappingSingleConfig(EMSynapseMappingScanConfig, SingleConfigMixin):
#     pass


class EMSynapseMappingTask(Task):
    config: EMSynapseMappingSingleConfig

    def execute(  # NOQA: PLR0914, PLR0915
        self, db_client: Client = None
    ) -> None:
        if db_client is None:
            err_str = "Synapse lookup and mapping requires a working db_client!"
            raise ValueError(err_str)

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
        pt_root_id, source_mesh_entity, source_dataset = self.resolve_provenance(
            db_client, morph_entity
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
        compressed_path = self.compress_output()

        self.register_output(
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

    @staticmethod
    def synapses_and_nodes_dataframes_from_EM(
        em_dataset: EMDataSetFromID, pt_root_id: int, db_client: Client, cave_version: int
    ) -> tuple[pandas.DataFrame, CellCollection, CellCollection, list]:
        # SYNAPSES
        syns, syns_notice = em_dataset.synapse_info_df(
            pt_root_id, cave_version, col_location="post_pt_position", db_client=db_client
        )
        # NODES
        pre_pt_root_to_sonata = (
            syns["pre_pt_root_id"]
            .drop_duplicates()
            .reset_index(drop=True)
            .reset_index()
            .set_index("pre_pt_root_id")
        )
        post_pt_root_to_sonata = (
            syns["post_pt_root_id"]
            .drop_duplicates()
            .reset_index(drop=True)
            .reset_index()
            .set_index("post_pt_root_id")
        )
        node_spec = default_node_spec_for(em_dataset, db_client)
        coll_pre, nodes_notice = assemble_collection_from_specs(
            em_dataset, db_client, cave_version, node_spec, pre_pt_root_to_sonata
        )
        coll_post, _ = assemble_collection_from_specs(
            em_dataset, db_client, cave_version, node_spec, post_pt_root_to_sonata
        )

        return syns, coll_pre, coll_post, [syns_notice, *nodes_notice]

    @staticmethod
    def resolve_provenance(
        db_client: Client, morph_entity: CellMorphology
    ) -> tuple[int, EMCellMesh, EMDenseReconstructionDataset]:
        pt_root_id = int(morph_entity.description.split()[-1][:-1])
        source_mesh_entity = db_client.search_entity(
            entity_type=EMCellMesh, query={"dense_reconstruction_cell_id": pt_root_id}
        ).first()
        source_dataset = db_client.get_entity(
            entity_id=source_mesh_entity.em_dense_reconstruction_dataset.id,
            entity_type=EMDenseReconstructionDataset,
        )
        return pt_root_id, source_mesh_entity, source_dataset

    def compress_output(self) -> os.PathLike:
        out_root = self.config.coordinate_output_root
        Path(out_root / "sonata.tar").write_bytes(
            subprocess.check_output(["tar", "-c", str(out_root)])  # NOQA: S607, S603
        )
        subprocess.check_call(["gzip", "-1", str(out_root / "sonata.tar")])  # NOQA: S607, S603
        return str(out_root / "sonata.tar.gz")

    @staticmethod
    def register_output(
        db_client: Client,
        pt_root_id: int,
        mapped_synapses_df: pandas.DataFrame,
        syn_pre_post_df: pandas.DataFrame,
        source_dataset: EMCellMesh,
        em_dataset: EMDenseReconstructionDataset,
        lst_notices: list[str],
        file_paths: dict[os.PathLike, os.PathLike],
        compressed_path: os.PathLike,
    ) -> None:
        license = em_dataset.license
        description = f"""Morphology skeleton with isolated spines and afferent synapses
        (Synaptome) of the neuron with pt_root_id {pt_root_id}
        in dataset {source_dataset.name}.\n"""
        description += "Used tables with the following notice texts:\n"
        for notice in lst_notices:
            description += str(notice) + "\n"

        circ_entity = Circuit(
            name=f"Afferent-synaptome-{pt_root_id}",
            description=description,
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
            experiment_date=source_dataset.experiment_date,
            license=license,
        )
        existing_circuit = db_client.register_entity(circ_entity)

        db_client.upload_directory(
            entity_id=existing_circuit.id,
            entity_type=Circuit,
            name="sonata_synaptome",
            paths=file_paths,
            label=AssetLabel.sonata_circuit,
        )

        db_client.upload_file(
            entity_id=existing_circuit.id,
            entity_type=Circuit,
            file_path=compressed_path,
            file_content_type=ContentType.application_gzip,
            asset_label=AssetLabel.compressed_sonata_circuit,
        )

        for publication in assemble_publication_links(db_client, em_dataset, lst_notices):
            new_link = ScientificArtifactPublicationLink(
                scientific_artifact=existing_circuit,
                publication=publication,
                publication_type=PublicationType.component_source,
            )
            db_client.register_entity(new_link)
        L.info(f"Output registered as: {existing_circuit.id}")
