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
    synapse_info_df, map_synapses_onto_spiny_morphology, 
    dummy_mapping_without_morphology, synapse_info_df_from_local_file,
    _STR_SEC_ID, L
)
from .utils_nodes import (
    source_resolution,
    translate,
    rotate,
    _SPINES_H5_FILE
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
    morphologies_are_transformed: bool = Field(
        description="Whether the morphology skeletons have been moved to the origin and rotated upwards or remain at their global coordinates",
        name="Morphologies are transformed"
    ),
    naming_patterns: tuple[str, str] = Field(
            default=("{pt_root_id}.swc", "{pt_root_id}-spines.json"),
            name="Morphology naming patterns",
            description="File name scheme for morphologies and spines info files"
        ),
    synapse_preloaded_h5_file: str | None = Field(
        description="A local h5 file that holds all synapse info. With the data for each postsynaptic neuron in a separate table.",
        name="Preloaded synapses hdf5 file",
        default=None
    )
    

    @model_validator(mode="after")
    def check_parameter_values(self) -> Self:
        return self
    
    def _setup_client(self):
        try:
            from caveclient import CAVEclient
        except ImportError:
            raise RuntimeError("Optional dependency 'caveclient' not installed!")
        self._client = CAVEclient(server_address=self.client_server,
                            datastack_name=self.client_name,
                            auth_token=self.cave_client_token)
        self._client.version = self.client_version
        self._resolutions = source_resolution(self._client)
        if self.synapse_preloaded_h5_file is not None:
            import h5py
            with h5py.File(self.synapse_preloaded_h5_file, "r") as h5:
                self._h5_dset_names = tuple(list(h5.keys()))
    
    def prefetch(self, lst_pt_root_ids):
        if not hasattr(self, "_client"):
            L.info("Creating client...")
            self._setup_client()
        if self.synapse_preloaded_h5_file is not None:
            naming_pat = "post_pt_root_id_{0}"
            use_pt_root_ids = [_id for _id in lst_pt_root_ids if
                               naming_pat.format(_id) in self._h5_dset_names]
            self._buf_df = synapse_info_df_from_local_file(use_pt_root_ids, self._resolutions,
                                                           self.synapse_preloaded_h5_file,
                                                           dset_name_pat=naming_pat)
        else:        
            self._buf_df = synapse_info_df(self._client,
                                        lst_pt_root_ids,
                                        self._resolutions)
        self._buffered_ids = tuple(lst_pt_root_ids)
        L.info(f"Prefetched {len(self._buf_df)} synapses for {len(lst_pt_root_ids)} neurons!")

    def map_synapses_to_morphology(self, morph_root, spine_root, node_info, 
                                   strict=False):
        morphologies_are_transformed = self.morphologies_are_transformed
        naming_morph, naming_spine = self.naming_patterns
        
        assert node_info["pt_root_id"] in self._buffered_ids
        syns = self._buf_df[self._buf_df["post_pt_root_id"] == node_info["pt_root_id"]].reset_index(drop=True)
        L.debug(f"Mapping {len(syns)} synapses...")
        if len(syns) == 0:
            L.warning(f"No synapses to be mapped for {node_info['pt_root_id']}!")
        
        self.enforce_no_lists()
        # fn_spines = os.path.join(spine_root, naming_spine.format(**node_info.to_dict()))
        # fn_spines = os.path.join(spine_root, node_info["spine_info"] + ".json")
        fn_spines = os.path.join(spine_root, _SPINES_H5_FILE)
        fn_morph = os.path.join(morph_root, naming_morph.format(**node_info.to_dict()))
        fn_morph = os.path.join(morph_root, node_info["morphology"] + ".swc")

        try:
            spines = pandas.read_hdf(fn_spines, node_info["spine_info"])
            L.info(f"{len(spines)} spines loaded!")
            dend_pos = numpy.vstack(spines["dendritic_sample_position"])
            srf_pos = numpy.vstack(spines["surface_sample_position"])
            orient = numpy.vstack(spines["orientation_vector"])
            # srf_pos = numpy.vstack([_spine["surface_sample_position"] for _spine in spines])
            # dend_pos = numpy.vstack([_spine["dendritic_sample_position"] for _spine in spines])
            # orient = numpy.vstack([_spine["orientation_vector"] for _spine in spines])
        except:
            if os.path.isfile(fn_morph):
                L.warning(f"No spine file at {fn_spines}, although morphology exists!")
            srf_pos = numpy.empty((0, 3), dtype=float)
            dend_pos = numpy.empty((0, 3), dtype=float)
            orient = numpy.empty((0, 3), dtype=float)


        # if os.path.isfile(fn_spines):
        #     with open(fn_spines, "r") as fid:
        #         spines = json.load(fid)
        #     L.info(f"{len(spines)} spines loaded!")
        #     srf_pos = numpy.vstack([_spine["surface_sample_position"] for _spine in spines])
        #     dend_pos = numpy.vstack([_spine["dendritic_sample_position"] for _spine in spines])
        #     orient = numpy.vstack([_spine["orientation_vector"] for _spine in spines])
        # else:
        #     if os.path.isfile(fn_morph):
        #         L.warning(f"No spine file at {fn_spines}, although morphology exists!")
        #     srf_pos = numpy.empty((0, 3), dtype=float)
        #     dend_pos = numpy.empty((0, 3), dtype=float)
        #     orient = numpy.empty((0, 3), dtype=float)

        if os.path.isfile(fn_morph):
            if morphologies_are_transformed:
                morph = neurom.io.utils.load_morphology(fn_morph, mutable=True)
                morph = translate(node_info, rotate(node_info, morph))
                morph = neurom.core.Morphology(morph.to_morphio().as_immutable())
            else:
                morph = neurom.io.utils.load_morphology(fn_morph)

            ret = map_synapses_onto_spiny_morphology(
                syns, morph, dend_pos, srf_pos, orient
            )
            unmapped = ret[_STR_SEC_ID] == -1
            if unmapped.any():
                if strict:
                    raise RuntimeError("{0} synapses could not be mapped to the morphology!".format(unmapped.sum()))
                else:
                    L.warning("Warning: {0} synapses could not be mapped to the morphology!".format(unmapped.sum()))
            return ret[~unmapped]
        L.debug("No morphology found at {fn_morph}")
        return dummy_mapping_without_morphology(syns)
    