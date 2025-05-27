import abc
import json
import numpy
import pandas
import neurom
import os.path
from typing import Self
from voxcell import CellCollection

from pydantic import Field, model_validator

from obi_one.core.block import Block

from .utils_edges import (
    synapse_info_df, map_synapses_onto_spiny_morphology, _STR_SEC_ID
)
from .utils_nodes import (
    source_resolution,
    translate,
    rotate
)


class EMEdgesMappingBlock(Block, abc.ABC):
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
    cave_client_token: str | None = Field(
        name="CAVE client acces token",
        description="CAVE client access token",
        default=None
    )
    

    @model_validator(mode="after")
    def check_parameter_values(self) -> Self:
        return self

    def map_synapses_to_morphology(self, morph_root, spine_root, node_info, 
                                   morphologies_are_transformed=True, strict=False):
        try:
            from caveclient import CAVEclient
        except ImportError:
            raise RuntimeError("Optional dependency 'caveclient' not installed!")
        client = CAVEclient(server_address=self.client_server,
                            datastack_name=self.client_name,
                            auth_token=self.cave_client_token)
        client.version = self.client_version
        
        self.enforce_no_lists()
        # fn_spines = os.path.join(morph_root, "{0}-spines.json".format(self.pt_root_id))
        # fn_morph = os.path.join(morph_root, "{0}.swc".format(self.pt_root_id))
        fn_spines = os.path.join(spine_root, "{0}-spines.json".format(node_info["morphology"]))
        fn_morph = os.path.join(morph_root, "{0}.swc".format(node_info["morphology"]))

        if os.path.isfile(fn_spines):
            with open(fn_spines, "r") as fid:
                spines = json.load(fid)
            srf_pos = numpy.vstack([_spine["surface_sample_position"] for _spine in spines])
            dend_pos = numpy.vstack([_spine["dendritic_sample_position"] for _spine in spines])
            orient = numpy.vstack([_spine["orientation_vector"] for _spine in spines])
        else:
            print("Warning: No spines for {0}".format(node_info["morphology"]))
            srf_pos = numpy.empty((0, 3), dtype=float)
            dend_pos = numpy.empty((0, 3), dtype=float)
            orient = numpy.empty((0, 3), dtype=float)
        
        if morphologies_are_transformed:
            morph = neurom.io.utils.load_morphology(fn_morph, mutable=True)
            morph = translate(node_info, rotate(node_info, morph))
            morph = neurom.core.Morphology(morph.to_morphio().as_immutable())
        else:
            morph = neurom.io.utils.load_morphology(fn_morph)

        resolutions = source_resolution(client)
        # syns = synapse_info_df(client, self.pt_root_id, resolutions)
        syns = synapse_info_df(client, node_info["pt_root_id"], resolutions)
        print("{0} synapses to be mapped...".format(len(syns)))

        ret = map_synapses_onto_spiny_morphology(
            syns, morph, dend_pos, srf_pos, orient
        )
        unmapped = ret[_STR_SEC_ID] == -1
        if unmapped.any():
            if strict:
                raise RuntimeError("{0} synapses could not be mapped to the morphology!".format(unmapped.sum()))
            else:
                print("Warning: {0} synapses could not be mapped to the morphology!".format(unmapped.sum()))
        return ret[~unmapped]
    