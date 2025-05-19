import abc
import pandas
import glob
import os.path
from typing import Self
from typing import ClassVar

from pydantic import Field, model_validator
from voxcell import CellCollection

from obi_one.core.form import Form
from obi_one.core.block import Block
from obi_one.core.single import SingleCoordinateMixin

from .utils_nodes import collection_to_neuron_info
from .utils_edges import pt_root_to_sonata_id, format_for_edges_output
from .sonata_edges_write import write_edges


class EMSonataEdgesFiles(Form, abc.ABC):

    single_coord_class_name: ClassVar[str] = "EMSonataEdgesFile"
    name: ClassVar[str] = "Electron microscopic synaptic connections as SONATA nodes file"
    description: ClassVar[str] = (
        "Converts the synaptic connection information from an EM release to a SONATA edges file."
    )
    cave_client_token: str = Field(
        name="CAVE client acces token",
        description="CAVE client access token"
    )

    class Initialize(Block):
        client_name: str = Field(
            default='minnie65_public', name="Release name", description="Name of the data release CAVE client"
        )
        client_version: int = Field(
            name="Release version", description="Version of the data release CAVE client"
        )
        intrinsic_nodes: str = Field(
            name="Intrinsic nodes file", description="Path to sonata nodes file for intrinsic neurons"
        )
        extrinsic_nodes: str = Field(
            name="extrinsic nodes file", description="Path to sonata nodes file for extrinsic neurons. Will be created if it does not exists, otherwise appended."
        )
        morphologies_dir: str = Field(
            name="Morphologies directory",
            description="Location where the skeletonized morphologies and spines are found"
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
        try:
            from caveclient import CAVEclient
        except ImportError:
            raise RuntimeError("Optional dependency 'cavelient' not installed!")
        client = CAVEclient(self.initialize.client_name)
        client.version = self.initialize.client_version
        client.auth.token = self.cave_client_token

        tmp_blck = EMEdgesMappingBlock(
                client_name=self.initialize.client_name,
                client_version=self.initialize.client_version,
                pt_root_id=-1
            )
        
        if os.path.isabs(self.initialize.extrinsic_nodes):
            extrinsics_fn = self.initialize.extrinsic_nodes
        else:
            extrinsics_fn = os.path.join(self.coordinate_output_root, self.initialize.extrinsic_nodes)
        intrinsics, intrinsic_name = collection_to_neuron_info(self.initialize.intrinsic_nodes,
                                                               must_exist=True)
        extrinsics, extrinsic_name = collection_to_neuron_info(extrinsics_fn,
                                                               must_exist=False)
        intrinsic_ids = intrinsics["pt_root_id"]
        extrinsic_ids = extrinsics["pt_root_id"]
        intrinsic_edge_pop_name = intrinsic_name + "__" + intrinsic_name + "__chemical"
        extrinsic_edge_pop_name = extrinsic_name + "__" + intrinsic_name + "__chemical"

        pt_root_ids = self._scan_for_morphology_root_ids(self.initialize.morphologies_dir)
        syns = []
        for pt_root_id in pt_root_ids:
            tmp_blck.pt_root_id = pt_root_id
            syns.append(tmp_blck.map_synapses_to_morphology(self.initialize.morphologies_dir))
        syns = pandas.concat(syns, axis=0)

        intrinsic_syns, extrinsic_syns, new_extrinsics = pt_root_to_sonata_id(syns, intrinsic_ids, extrinsic_ids)
        
        new_extrinsics["x"] = 0.0
        new_extrinsics["y"] = 0.0
        new_extrinsics["z"] = 0.0
        comb_extrinsics = pandas.concat([extrinsics, new_extrinsics], axis=0)
        comb_extrinsics.index = comb_extrinsics.index + 1

        new_ext_coll = CellCollection.from_dataframe(comb_extrinsics)
        new_ext_coll.population_name = extrinsic_name
        new_ext_coll.save_sonata(extrinsics_fn)

        intrinsic_syn_map, intrinsic_syn_prop = format_for_edges_output(intrinsic_syns)
        extrinsic_syn_map, extrinsic_syn_prop = format_for_edges_output(extrinsic_syns)
        intrinsic_edges_fn = os.path.join(self.coordinate_output_root, "intrinsic_edges.h5")
        extrinsic_edges_fn = os.path.join(self.coordinate_output_root, "extrinsic_edges.h5")

        write_edges(intrinsic_edges_fn, intrinsic_edge_pop_name, 
                    intrinsic_syn_map, intrinsic_syn_prop)
        write_edges(extrinsic_edges_fn, extrinsic_edge_pop_name, 
                    extrinsic_syn_map, extrinsic_syn_prop)


