import abc
import pandas
import os.path
from typing import Self
from typing import ClassVar

from pydantic import Field, model_validator

from obi_one.core.form import Form
from obi_one.core.block import Block
from obi_one.core.single import SingleCoordinateMixin

from .utils_nodes import neuron_info_df, neuron_info_to_collection


class EMSonataNodesFiles(Form, abc.ABC):

    single_coord_class_name: ClassVar[str] = "EMSonataNodesFile"
    name: ClassVar[str] = "Electron microscopic neurons as SONATA nodes file"
    description: ClassVar[str] = (
        "Converts the neuron information from an EM release to a SONATA nodes file."
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
        table_names: tuple[str, ...] = Field(
            name="Neuron info tables", description="Names of the data tables to collect neuron info from"
        )
        table_cols: tuple[str, ...] = Field(
            name="Table columns",
            description="Names of neuron properties to keep from the source."
        )
        population_name: str = Field(
            name="Population name",
            description="Name of the SONATA node population"
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
        client = CAVEclient(self.initialize.client_name)
        client.version = self.initialize.client_version
        client.auth.token = self.cave_client_token
        filters = {
            "classification_system": "aibs_neuronal"
        }
        nrns = [
            neuron_info_df(client, self.initialize.table_names[0],
                           filters=filters,
                           add_position=True)
        ]
        for _tbl in self.initialize.table_names[1:]:
            nrn = neuron_info_df(client, _tbl,
                                 filters=filters,
                                 add_position=False)
            nrns.append(nrn)
        nrns = pandas.concat(nrns, axis=1)

        coll = neuron_info_to_collection(nrns, self.initialize.population_name,
                                  list(self.initialize.table_cols),
                                  ["x", "y", "z"])
        coll.save_sonata(os.path.join(self.coordinate_output_root, "intrinsic_nodes.h5"))
