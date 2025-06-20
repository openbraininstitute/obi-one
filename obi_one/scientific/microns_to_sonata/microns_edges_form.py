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
    def write_synapses_and_extrinsics(syns,
                                      extrinsic_node_pop, extrinsic_nodes_fn,
                                      intrinsic_name, intrinsic_edge_pop_name, intrinsic_ids, intrinsic_edges_fn,
                                      virtual_name, virtual_edge_pop_name, virtual_ids, virtual_edges_fn,
                                      extrinsic_name, extrinsic_edge_pop_name, extrinsic_ids, extrinsic_edges_fn):
        if len(syns) == 0:
            return collection_to_neuron_info(extrinsic_nodes_fn, must_exist=False)
        # Determine which synapases are intrinsic and which are extrinsic.
        # Also determine which new extrinsic pt_root_ids are references and must be created.
        intrinsic_syns, virtual_syns, extrinsic_syns, new_extrinsics =\
            pt_root_to_sonata_id(syns, intrinsic_ids, virtual_ids, extrinsic_ids)
        
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
        intrinsic_syn_map, intrinsic_syn_prop = format_for_edges_output(intrinsic_syns)
        virtual_syn_map, virtual_syn_prop = format_for_edges_output(virtual_syns)
        extrinsic_syn_map, extrinsic_syn_prop = format_for_edges_output(extrinsic_syns)

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
                morphologies_are_transformed=self.initialize.morphologies_are_transformed
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
        extrinsics, extrinsic_name = collection_to_neuron_info(extrinsics_fn,
                                                               must_exist=False)
        intrinsic_ids = intrinsics["pt_root_id"]
        extrinsic_ids = extrinsics["pt_root_id"]
        intrinsic_edge_pop_name = intrinsic_name + "__" + intrinsic_name + "__chemical"
        extrinsic_edge_pop_name = extrinsic_name + "__" + intrinsic_name + "__chemical"

        if self.initialize.virtual_nodes is not None:
            virtuals, virtual_name = collection_to_neuron_info(self.initialize.virtual_nodes,
                                                               must_exist=True)
        else:
            virtuals, virtual_name = collection_to_neuron_info(".", must_exist=False)
            virtual_name = "em_virtual"
        virtual_ids = virtuals["pt_root_id"]
        virtual_edge_pop_name = virtual_name + "__" + intrinsic_name + "__chemical"
        print(f"{len(intrinsics)} intrinsic neurons found!")

        pt_root_ids = find_edges_resume_point(intrinsics, extrinsic_edges_fn,
                                              extrinsic_edge_pop_name,
                                              with_morphologies=False)
        print(f"Iterating over {len(pt_root_ids)} neurons!")

        syns = []
        chunk_sz = 50
        chunk_splt = numpy.arange(0, len(pt_root_ids) + chunk_sz, chunk_sz)
        chunks = [pt_root_ids.iloc[a:b] for a, b in zip(chunk_splt[:-1], chunk_splt[1:])]
        for chunk in tqdm.tqdm(chunks):
            tmp_blck.prefetch(chunk["pt_root_id"].to_list())
            for _, pt_root_id in chunk.iterrows():
                try:
                    new_syns = tmp_blck.map_synapses_to_morphology(self.initialize.morphologies_dir,
                                                                    self.initialize.spines_dir,
                                                                    pt_root_id)
                    if len(new_syns) > 0:
                        syns.append(new_syns)
                    # print(f"Mapped {len(syns[-1])} synapses!")
                except Exception as e:
                    print("Problem with neuron {0}".format(pt_root_id["pt_root_id"]))
                    print(e)
                    # raise
                
            if len(syns) > 0:
                # print("Writing chunk to disk!")
                # print(len(syns))
                # print([len(_syns) for _syns in syns])
                extrinsics, extrinsic_name = self.write_synapses_and_extrinsics(
                    pandas.concat(syns, axis=0),
                    extrinsics, extrinsics_fn,
                    intrinsic_name, intrinsic_edge_pop_name, intrinsic_ids, intrinsic_edges_fn,
                    virtual_name, virtual_edge_pop_name, virtual_ids, virtual_edges_fn,
                    extrinsic_name, extrinsic_edge_pop_name, extrinsic_ids, extrinsic_edges_fn
                )
                extrinsic_ids = extrinsics["pt_root_id"]
                syns = []
            
        # syns = pandas.concat(syns, axis=0)
        # extrinsics, extrinsic_name = self.write_synapses_and_extrinsics(
        #     syns,
        #     extrinsics, extrinsics_fn,
        #     intrinsic_name, intrinsic_edge_pop_name, intrinsic_ids, intrinsic_edges_fn,
        #     virtual_name, virtual_edge_pop_name, virtual_ids, virtual_edges_fn,
        #     extrinsic_name, extrinsic_edge_pop_name, extrinsic_ids, extrinsic_edges_fn
        # )
        
        
        # syns = pandas.concat(syns, axis=0)

        # # Determine which synapases are intrinsic and which are extrinsic.
        # # Also determine which new extrinsic pt_root_ids are references and must be created.
        # intrinsic_syns, virtual_syns, extrinsic_syns, new_extrinsics =\
        #     pt_root_to_sonata_id(syns, intrinsic_ids, virtual_ids, extrinsic_ids)
        
        # # Overwrite exising extrinsics with concatenation of existing and new extrinsics
        # new_extrinsics["x"] = 0.0
        # new_extrinsics["y"] = 0.0
        # new_extrinsics["z"] = 0.0
        # comb_extrinsics = pandas.concat([extrinsics, new_extrinsics], axis=0)
        # comb_extrinsics.index = comb_extrinsics.index + 1

        # new_ext_coll = CellCollection.from_dataframe(comb_extrinsics)
        # new_ext_coll.population_name = extrinsic_name
        # new_ext_coll.save_sonata(extrinsics_fn)

        # # Bring DataFrame into output format. Mainly renames columns.
        # intrinsic_syn_map, intrinsic_syn_prop = format_for_edges_output(intrinsic_syns)
        # virtual_syn_map, virtual_syn_prop = format_for_edges_output(virtual_syns)
        # extrinsic_syn_map, extrinsic_syn_prop = format_for_edges_output(extrinsic_syns)

        # write_edges(intrinsic_edges_fn, intrinsic_edge_pop_name, 
        #             intrinsic_syn_map, intrinsic_syn_prop,
        #             intrinsic_name, intrinsic_name)
        # if len(virtual_syns) > 0:
        #     write_edges(virtual_edges_fn, virtual_edge_pop_name, 
        #                 virtual_syn_map, virtual_syn_prop,
        #                 virtual_name, intrinsic_name)
        # write_edges(extrinsic_edges_fn, extrinsic_edge_pop_name, 
        #             extrinsic_syn_map, extrinsic_syn_prop,
        #             extrinsic_name, intrinsic_name)


