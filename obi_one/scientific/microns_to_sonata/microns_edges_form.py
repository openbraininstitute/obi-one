import abc
import pandas
import numpy
import glob
import os.path
import tqdm
from typing import Self
from typing import ClassVar

from pydantic import Field, model_validator
from voxcell import CellCollection

from obi_one.core.form import Form
from obi_one.core.block import Block
from obi_one.core.single import SingleCoordinateMixin

from .utils_nodes import collection_to_neuron_info, _STR_MORPH, _STR_NONE
from .utils_edges import pt_root_to_sonata_id, format_for_edges_output, find_edges_resume_point
from .sonata_edges_write import write_edges
from .utils_edges import L


class EMSonataEdgesFiles(Form, abc.ABC):

    single_coord_class_name: ClassVar[str] = "EMSonataEdgesFile"
    name: ClassVar[str] = "Electron microscopic synaptic connections as SONATA nodes file"
    description: ClassVar[str] = (
        "Converts the synaptic connection information from an EM release to a SONATA edges file."
    )
    cave_client_token: str | None = Field(
        name="CAVE client acces token",
        description="CAVE client access token",
        default=None
    )

    class Initialize(Block):
        client_server: str | None = Field(
            default=None,
            name="Server name",
            description="Name of data release server. If None, the default of CAVE client is used."
        )
        client_name: str = Field(
            default='minnie65_public', name="Release name", description="Name of the data release CAVE client"
        )
        client_version: int = Field(
            name="Release version", description="Version of the data release CAVE client"
        )
        intrinsic_nodes: str | list[str] = Field(
            name="Intrinsic nodes file", description="Path to sonata nodes file for intrinsic neurons"
        )
        virtual_nodes: str | list[str] | None = Field(
            name="Virtual nodes file", description="Path to sonata nodes file for virtual neurons",
            default=None
        )
        extrinsic_nodes: str | list[str] = Field(
            name="extrinsic nodes file", description="Path to sonata nodes file for extrinsic neurons. Will be created if it does not exists, otherwise appended."
        )
        morphologies_dir: str | list[str] = Field(
            name="Morphologies directory",
            description="Location where the skeletonized morphologies are found"
        )
        morphologies_are_transformed: bool | list[bool] = Field(
            name="Morphologies are transformed",
            default=True,
            description="If False transformations from the nodes file are not applied to loaded morphologies"
        )
        spines_dir: str | list[str] = Field(
            name="Spines directory",
            description="Location where the spine information is found"
        )
        naming_patterns: tuple[str, str] = Field(
            default=("{pt_root_id}.swc", "{pt_root_id}-spines.json"),
            name="Morphology naming patterns",
            description="File name scheme for morphologies and spines info files"
        )
        synapse_preloaded_h5_file: str | None = Field(
            description="A local h5 file that holds all synapse info. With the data for each postsynaptic neuron in a separate table.",
            name="Preloaded synapses hdf5 file",
            default=None
        )
        source_columns_to_keep: tuple[str, ...] = Field(
            description="Names of columns in the original source table of synapses that are to be kept and written to the output",
            name="Source columns to keep",
            default=("id", "size")
        )

    initialize: Initialize

    @staticmethod
    def _scan_for_morphology_root_ids(root, ext=".swc"):
        fns = glob.glob(os.path.join(root, "[0-9]*" + ext))
        pt_root_ids = [int(os.path.splitext(os.path.split(_x)[1])[0])
                        for _x in fns]
        return pt_root_ids


from obi_one.scientific.microns_to_sonata.microns_edges_block import EMEdgesMappingBlock

class EMSonataEdgesFile(EMSonataEdgesFiles, SingleCoordinateMixin):

    @staticmethod
    def write_synapses_and_extrinsics(syns, columns_to_keep,
                                      extrinsic_node_pop, extrinsic_nodes_fn,
                                      morphology_ids,
                                      intrinsic_name, intrinsic_edge_pop_name, intrinsic_ids, intrinsic_edges_fn,
                                      virtual_name, virtual_edge_pop_name, virtual_ids, virtual_edges_fn,
                                      extrinsic_name, extrinsic_edge_pop_name, extrinsic_ids, extrinsic_edges_fn):
        if len(syns) == 0:
            L.warning("Empty chunk!")
            return collection_to_neuron_info(extrinsic_nodes_fn, must_exist=False)
        # Determine which synapases are intrinsic and which are extrinsic.
        # Also determine which new extrinsic pt_root_ids are references and must be created.
        intrinsic_syns, virtual_syns, extrinsic_syns, new_extrinsics =\
            pt_root_to_sonata_id(syns, morphology_ids, intrinsic_ids, virtual_ids, extrinsic_ids)
        L.info(f"Writing {len(intrinsic_syns)}, {len(virtual_syns)}, {len(extrinsic_syns)} synapses")
        L.info(f"Creating {len(new_extrinsics)} new extrinsic nodes")

        # Overwrite exising extrinsics with concatenation of existing and new extrinsics
        new_extrinsics["x"] = 0.0
        new_extrinsics["y"] = 0.0
        new_extrinsics["z"] = 0.0
        comb_extrinsics = pandas.concat([extrinsic_node_pop, new_extrinsics], axis=0)
        comb_extrinsics.index = comb_extrinsics.index + 1

        new_ext_coll = CellCollection.from_dataframe(comb_extrinsics)
        new_ext_coll.population_name = extrinsic_name
        new_ext_coll.save_sonata(extrinsic_nodes_fn)

        # Bring DataFrame into output format. Mainly renames columns.
        intrinsic_syn_map, intrinsic_syn_prop = format_for_edges_output(intrinsic_syns, columns_to_keep)
        virtual_syn_map, virtual_syn_prop = format_for_edges_output(virtual_syns, columns_to_keep)
        extrinsic_syn_map, extrinsic_syn_prop = format_for_edges_output(extrinsic_syns, columns_to_keep)

        write_edges(intrinsic_edges_fn, intrinsic_edge_pop_name, 
                    intrinsic_syn_map, intrinsic_syn_prop,
                    intrinsic_name, intrinsic_name)
        if len(virtual_syns) > 0:
            write_edges(virtual_edges_fn, virtual_edge_pop_name, 
                        virtual_syn_map, virtual_syn_prop,
                        virtual_name, intrinsic_name)
        write_edges(extrinsic_edges_fn, extrinsic_edge_pop_name, 
                    extrinsic_syn_map, extrinsic_syn_prop,
                    extrinsic_name, intrinsic_name)
        
        return collection_to_neuron_info(extrinsic_nodes_fn, must_exist=True)

    def run(self) -> str:
        
        tmp_blck = EMEdgesMappingBlock(
                client_server=self.initialize.client_server,
                client_name=self.initialize.client_name,
                cave_client_token=self.cave_client_token,
                client_version=self.initialize.client_version,
                naming_patterns=self.initialize.naming_patterns,
                morphologies_are_transformed=self.initialize.morphologies_are_transformed,
                synapse_preloaded_h5_file=self.initialize.synapse_preloaded_h5_file
            )
        
        if os.path.isabs(self.initialize.extrinsic_nodes):
            extrinsics_fn = self.initialize.extrinsic_nodes
        else:
            extrinsics_fn = os.path.join(self.coordinate_output_root, self.initialize.extrinsic_nodes)
        intrinsic_edges_fn = os.path.join(self.coordinate_output_root, "intrinsic_edges.h5")
        virtual_edges_fn = os.path.join(self.coordinate_output_root, "virtual_edges.h5")
        extrinsic_edges_fn = os.path.join(self.coordinate_output_root, "extrinsic_edges.h5")

        # Load intrinsic and currently exisint extrinsic nodes
        intrinsics, intrinsic_name = collection_to_neuron_info(self.initialize.intrinsic_nodes,
                                                               must_exist=True)
        L.info(f"Loaded {len(intrinsics)} intrinsic nodes.")
        extrinsics, extrinsic_name = collection_to_neuron_info(extrinsics_fn,
                                                               must_exist=False)
        L.info(f"Loaded {len(extrinsics)} extrinsic nodes.")
        intrinsic_ids = intrinsics["pt_root_id"]
        morphology_ids = intrinsics.loc[intrinsics[_STR_MORPH] != _STR_NONE, "pt_root_id"]
        L.info(f"{len(morphology_ids)} intrinsic nodes have morphologies.")
        extrinsic_ids = extrinsics["pt_root_id"]
        intrinsic_edge_pop_name = intrinsic_name + "__" + intrinsic_name + "__chemical"
        extrinsic_edge_pop_name = extrinsic_name + "__" + intrinsic_name + "__chemical"

        if self.initialize.virtual_nodes is not None:
            virtuals, virtual_name = collection_to_neuron_info(self.initialize.virtual_nodes,
                                                               must_exist=True)
            L.info(f"Loaded {len(virtuals)} virtual nodes.")
        else:
            virtuals, virtual_name = collection_to_neuron_info(".", must_exist=False)
            virtual_name = "em_virtual"
            L.info(f"No virtual nodes found.")
        virtual_ids = virtuals["pt_root_id"]
        virtual_edge_pop_name = virtual_name + "__" + intrinsic_name + "__chemical"

        pt_root_ids = find_edges_resume_point(intrinsics, intrinsic_edges_fn,
                                              intrinsic_edge_pop_name,
                                              with_morphologies=False)
        L.info(f"Iterating over {len(pt_root_ids)} neurons!")

        syns = []
        chunk_sz = 50
        chunk_splt = numpy.arange(0, len(pt_root_ids) + chunk_sz, chunk_sz)
        chunks = [pt_root_ids.iloc[a:b] for a, b in zip(chunk_splt[:-1], chunk_splt[1:])]
        for chunk in tqdm.tqdm(chunks):
            tmp_blck.prefetch(chunk["pt_root_id"].to_list())
            for _, pt_root_id in chunk.iterrows():
                L.debug(f'--> neuron {pt_root_id["pt_root_id"]}')
                try:
                    new_syns = tmp_blck.map_synapses_to_morphology(self.initialize.morphologies_dir,
                                                                    self.initialize.spines_dir,
                                                                    pt_root_id)
                    if len(new_syns) > 0:
                        syns.append(new_syns)
                    L.debug(f"Mapped {len(syns[-1])} synapses!")
                except Exception as e:
                    L.warning(f'Problem with neuron {pt_root_id["pt_root_id"]}')
                    L.warning(str(e))
                    # raise
                
            if len(syns) > 0:
                L.info("Writing chunk to disk...")
                extrinsics, extrinsic_name = self.write_synapses_and_extrinsics(
                    pandas.concat(syns, axis=0), self.initialize.source_columns_to_keep,
                    extrinsics, extrinsics_fn, morphology_ids,
                    intrinsic_name, intrinsic_edge_pop_name, intrinsic_ids, intrinsic_edges_fn,
                    virtual_name, virtual_edge_pop_name, virtual_ids, virtual_edges_fn,
                    extrinsic_name, extrinsic_edge_pop_name, extrinsic_ids, extrinsic_edges_fn
                )
                extrinsic_ids = extrinsics["pt_root_id"]
                syns = []
            