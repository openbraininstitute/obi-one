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
from .utils_nodes import source_resolution


class EMEdgesMappingBlock(Block, abc.ABC):
    client_name: str = Field(
            default='minnie65_public', name="Release name", description="Name of the data release CAVE client"
        )
    client_version: int = Field(
        name="Release version", description="Version of the data release CAVE client"
    )
    pt_root_id: int | list[int] = Field(
        name="Point root id",
        description="Value of the 'pt_root_id' property of the neuron to map afferent synapses for"
    )

    @model_validator(mode="after")
    def check_parameter_values(self) -> Self:
        return self

    def map_synapses_to_morphology(self, morph_root, strict=False):
        try:
            from caveclient import CAVEclient
        except ImportError:
            raise RuntimeError("Optional dependency 'caveclient' not installed!")
        
        self.enforce_no_lists()
        fn_spines = os.path.join(morph_root, "{0}-spines.json".format(self.pt_root_id))
        fn_morph = os.path.join(morph_root, "{0}.swc".format(self.pt_root_id))

        with open(fn_spines, "r") as fid:
            spines = json.load(fid)
        srf_pos = numpy.vstack([_spine["surface_sample_position"] for _spine in spines])
        dend_pos = numpy.vstack([_spine["dendritic_sample_position"] for _spine in spines])
        orient = numpy.vstack([_spine["orientation_vector"] for _spine in spines])
        morph = neurom.io.utils.load_morphology(fn_morph)

        client = CAVEclient(self.client_name)
        client.version = self.client_version

        resolutions = source_resolution(client)
        syns = synapse_info_df(client, self.pt_root_id, resolutions)

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
    