import abc
import pandas
import os.path
from typing import Self
from typing import ClassVar

from pydantic import Field, model_validator

from obi_one.core.form import Form
from obi_one.core.block import Block
from obi_one.core.single import SingleCoordinateMixin

from .utils_nodes import (
    neuron_info_df, 
    neuron_info_to_collection, 
    estimate_volume_rotation,
    transform_and_copy_morphologies,
    _STR_MORPH,
    _STR_ORIENT
)


class EMSonataNodesFiles(Form, abc.ABC):

    single_coord_class_name: ClassVar[str] = "EMSonataNodesFile"
    name: ClassVar[str] = "Electron microscopic neurons as SONATA nodes file"
    description: ClassVar[str] = (
        "Converts the neuron information from an EM release to a SONATA nodes file."
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
        table_names: tuple[str, ...] = Field(
            name="Neuron info tables", description="Names of the data tables to collect neuron info from"
        )
        table_cols: tuple[str, ...] = Field(
            name="Table columns",
            description="Names of neuron properties to keep from the source."
        )
        nodes_filters: dict = Field(
            name="Node population filters",
            description="Key/value filters to apply to the tables of the data release to generate the node population."
        )
        population_name: str = Field(
            name="Population name",
            description="Name of the SONATA node population"
        )
        volume_vertical: tuple[float, float, float] | None = Field(
            default=None,
            name="Volume vertical vector",
            description="A vector of len 3 that defines the vertical of the data volume. Used to assign a \
                single global rotation to all morphologies. If not provided, instead it will trye to  \
                    estimate an orientation field based on neuron layers."
        )
        morphology_root: str = Field(
            name="Morphology locations",
            description="Folder in which the skeletonized morphologies and spine infos are found"
        )
        transform_morphology: bool = Field(
            name="Transform morphology to local coordinates",
            description="Whether to rotate the morphology according to local orientation and translate to the origin",
            default=True
        )

    initialize: Initialize

    # def intrinsic_node_population(self, morphology):
    #     self.enforce_no_lists()
    #     return self._make_points(morphology)


class EMSonataNodesFile(EMSonataNodesFiles, SingleCoordinateMixin):

    def run(self) -> str:
        try:
            from caveclient import CAVEclient
        except ImportError:
            raise RuntimeError("Optional dependency 'cavelient' not installed!")
        client = CAVEclient(server_address=self.initialize.client_server,
                            datastack_name=self.initialize.client_name,
                            auth_token=self.cave_client_token)
        client.version = self.initialize.client_version
        # if self.cave_client_token is not None:
        #     client.auth.token = self.cave_client_token
        
        nrns = neuron_info_df(client, self.initialize.table_names[0],
                              filters=self.initialize.nodes_filters,
                              add_position=True)
        for _tbl in self.initialize.table_names[1:]:
            nrn = neuron_info_df(client, _tbl,
                                 filters={"pt_root_id": list(nrns.index.values)},
                                 add_position=False)
            nrn = nrn[[_col for _col in nrn.columns if _col not in nrns.columns]]
            nrns = pandas.concat([nrns, nrn], axis=1)
        
        # More of a place holder. We estimate a global rotation of the entire volume
        volume_rot = estimate_volume_rotation(nrns, volume_vertical=self.initialize.volume_vertical).as_matrix()
        nrns["orientation"] = [volume_rot for _ in range(len(nrns))]
        transform_and_copy_morphologies(nrns, self.initialize.morphology_root,
                                        os.path.join(self.coordinate_output_root,
                                                     "morphologies"),
                                        out_formats=(".h5", ".swc"),
                                        do_transform=self.initialize.transform_morphology)


        coll = neuron_info_to_collection(nrns, self.initialize.population_name,
                                  list(self.initialize.table_cols),
                                  ["x", "y", "z", _STR_ORIENT, _STR_MORPH])
        coll.save_sonata(os.path.join(self.coordinate_output_root, "intrinsic_nodes.h5"))
