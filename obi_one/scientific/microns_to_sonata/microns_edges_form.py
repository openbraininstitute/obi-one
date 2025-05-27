import abc
import pandas
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
        extrinsic_nodes: str | list[str] = Field(
            name="extrinsic nodes file", description="Path to sonata nodes file for extrinsic neurons. Will be created if it does not exists, otherwise appended."
        )
        morphologies_dir: str | list[str] = Field(
            name="Morphologies directory",
            description="Location where the skeletonized morphologies are found"
        ),
        morphologies_are_transformed: bool | list[bool] = Field(
            name="Morphologies are transformed",
            default=True,
            description="If False transformations from the nodes file are not applied to loaded morphologies"
        )
        spines_dir: str | list[str] = Field(
            name="Spines directory",
            description="Location where the spine information is found"
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

    def run(self) -> str:
        # try:
        #     from caveclient import CAVEclient
        # except ImportError:
        #     raise RuntimeError("Optional dependency 'cavelient' not installed!")
        # client = CAVEclient(server_address=self.initialize.client_server,
        #                     datastack_name=self.initialize.client_name,
        #                     auth_token=self.cave_client_token)
        # client.version = self.initialize.client_version

        tmp_blck = EMEdgesMappingBlock(
                client_server=self.initialize.client_server,
                client_name=self.initialize.client_name,
                cave_client_token=self.cave_client_token,
                client_version=self.initialize.client_version
            )
        
        if os.path.isabs(self.initialize.extrinsic_nodes):
            extrinsics_fn = self.initialize.extrinsic_nodes
        else:
            extrinsics_fn = os.path.join(self.coordinate_output_root, self.initialize.extrinsic_nodes)
        intrinsic_edges_fn = os.path.join(self.coordinate_output_root, "intrinsic_edges.h5")
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

        pt_root_ids = find_edges_resume_point(intrinsics, intrinsic_edges_fn,
                                              intrinsic_edge_pop_name, with_morphologies=True)

        syns = []
        for _, pt_root_id in tqdm.tqdm(pt_root_ids.iterrows()):
            #tmp_blck.pt_root_id = pt_root_id
            syns.append(tmp_blck.map_synapses_to_morphology(self.initialize.morphologies_dir,
                                                            self.initialize.spines_dir,
                                                            pt_root_id,
                                                            morphologies_are_transformed=self.initialize.morphologies_are_transformed))
        syns = pandas.concat(syns, axis=0)

        # Determine which synapases are intrinsic and which are extrinsic.
        # Also determine which new extrinsic pt_root_ids are references and must be created.
        intrinsic_syns, extrinsic_syns, new_extrinsics = pt_root_to_sonata_id(syns, intrinsic_ids, extrinsic_ids)
        
        # Overwrite exising extrinsics with concatenation of existing and new extrinsics
        new_extrinsics["x"] = 0.0
        new_extrinsics["y"] = 0.0
        new_extrinsics["z"] = 0.0
        comb_extrinsics = pandas.concat([extrinsics, new_extrinsics], axis=0)
        comb_extrinsics.index = comb_extrinsics.index + 1

        new_ext_coll = CellCollection.from_dataframe(comb_extrinsics)
        new_ext_coll.population_name = extrinsic_name
        new_ext_coll.save_sonata(extrinsics_fn)

        # Bring DataFrame into output format. Mainly renames columns.
        intrinsic_syn_map, intrinsic_syn_prop = format_for_edges_output(intrinsic_syns)
        extrinsic_syn_map, extrinsic_syn_prop = format_for_edges_output(extrinsic_syns)

        write_edges(intrinsic_edges_fn, intrinsic_edge_pop_name, 
                    intrinsic_syn_map, intrinsic_syn_prop,
                    intrinsic_name, intrinsic_name)
        write_edges(extrinsic_edges_fn, extrinsic_edge_pop_name, 
                    extrinsic_syn_map, extrinsic_syn_prop,
                    extrinsic_name, intrinsic_name)


