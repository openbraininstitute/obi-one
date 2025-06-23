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
    neuron_info_from_somas_file,
    apply_filters,
    split_into_intrinsic_and_virtual,
    post_process_neuron_info,
    get_node_prop_post_processors,
    _STR_MORPH,
    _STR_ORIENT,
    _STR_SPINE_INFO
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
        somas_file: str | None = Field(
            name="External somas file",
            description="Path to a .csv file with additional info about neuron somas in the volume (soma.csv)",
            default=None
        )
        table_cols: tuple[str, ...] = Field(
            name="Table columns",
            description="Names of neuron properties to keep from the sources."
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
        naming_patterns: tuple[str, str] = Field(
            default=("{pt_root_id}.swc", "{pt_root_id}-spines.json"),
            name="Morphology naming patterns",
            description="File name scheme for morphologies and spines info files"
        )
        transform_morphology: bool = Field(
            name="Transform morphology to local coordinates",
            description="Whether to rotate the morphology according to local orientation and translate to the origin",
            default=True
        )
        intrinsic_population_parameter: float = Field(
            name="Parameter defining which neurons will be part of the intrinsic node population",
            description="This parameter determines which neurons will be part of the intrinsic node population.\
                Afferent synapses will be extracted only for the intrinsic population. For other neurons,\
                only efferent synapses onto the intrinsic population will be extracted.\
                If the value is below 0, then only neurons with available skeletonized morphologies will be\
                considered intrinsic. If the value is above or equal to 0, then an axis aligned bounding box around\
                all neurons with morphologies will be considered. The box is then expanded along all dimensions by\
                a factor that is equal to the value of this parameter. All somata within the resulting box are\
                then considered intrinsic.",
            default=-1.0
        )
        specific_column_rename_profile: str = Field(
            name="name",
            description="description",
            default="none"
        )

    initialize: Initialize


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
        
        nrns = neuron_info_df(client, self.initialize.table_names[0],
                              filters={}, # self.initialize.nodes_filters,
                              add_position=True)
        assert len(nrns) > 0, "No neurons found!"
        for _tbl in self.initialize.table_names[1:]:
            nrn = neuron_info_df(client, _tbl,
                                 filters={"pt_root_id": list(nrns.index.values)},
                                 add_position=False)
            nrn = nrn[[_col for _col in nrn.columns if _col not in nrns.columns]]
            nrns = pandas.concat([nrns, nrn], axis=1)
        
        if self.initialize.somas_file is not None:
            nrn = neuron_info_from_somas_file(
                client,
                self.initialize.somas_file,
                nrns
            )
            # nrn.to_csv("_somas.csv")
            nrn = nrn[[_col for _col in nrn.columns if _col not in nrns.columns]]
            nrns = pandas.concat([nrns, nrn], axis=1)
        # lst_column_pp = get_node_prop_post_processors(self.initialize.property_post_processors)
        # nrns = post_process_neuron_info(nrns, lst_column_pp)
        nrns = apply_filters(nrns, self.initialize.nodes_filters)

        # More of a place holder. We estimate a global rotation of the entire volume
        volume_rot = estimate_volume_rotation(nrns, volume_vertical=self.initialize.volume_vertical).as_matrix()
        nrns["orientation"] = [volume_rot for _ in range(len(nrns))]

        transform_and_copy_morphologies(nrns, self.initialize.morphology_root,
                                        os.path.join(self.coordinate_output_root,
                                                     "morphologies"),
                                        naming_patters=self.initialize.naming_patterns,
                                        out_formats=("h5", "swc"),
                                        do_transform=self.initialize.transform_morphology)

        use_bounding_box = self.initialize.intrinsic_population_parameter >= 0
        nrn_i, nrn_v = split_into_intrinsic_and_virtual(nrns, use_bounding_box,
                                                        self.initialize.intrinsic_population_parameter)
        coll_i = neuron_info_to_collection(nrn_i, self.initialize.population_name,
                                  list(self.initialize.table_cols),
                                  ["x", "y", "z", _STR_ORIENT, _STR_MORPH, _STR_SPINE_INFO],
                                  self.initialize.specific_column_rename_profile)
        coll_i.save_sonata(os.path.join(self.coordinate_output_root, "intrinsic_nodes.h5"))
        if len(nrn_v) == 0: return
        coll_v = neuron_info_to_collection(nrn_v, "virtual_" + self.initialize.population_name,
                                  list(self.initialize.table_cols),
                                  ["x", "y", "z", _STR_ORIENT],
                                  self.initialize.specific_column_rename_profile)
        coll_v.save_sonata(os.path.join(self.coordinate_output_root, "virtual_nodes.h5"))
