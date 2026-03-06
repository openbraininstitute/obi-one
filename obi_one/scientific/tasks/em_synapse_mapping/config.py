from typing import ClassVar

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID


class EMSynapseMappingScanConfig(ScanConfig):
    name: ClassVar[str] = "Map synapse locations"
    description: ClassVar[str] = "Map location of afferent synapses from EM onto a spiny morphology"
    # _cave_token: str | None = Field(
    #     default=None,
    #     title="CAVEclient access token",
    #     description="""Token to authenticate access to the EM dataset with.
    #     If a token is stored in a secrets file, this does not need to be provided.
    #     See: https://caveclient.readthedocs.io/en/latest/guide/authentication.html""",
    # )

    class Initialize(Block):
        spiny_neuron: CellMorphologyFromID | MEModelFromID = Field(
            title="EM skeletonized morphology",
            description="""A neuron morphology with spines obtained from an electron-microscopy
            datasets through the skeletonization task.""",
        )
        pt_root_id: int | None = Field(
            title="Neuron identifier within the EM dense reconstruction dataset.",
            description="""Neurons in an EM dataset are uniquely identified by a number,
            often called 'pt_root_id'. Please provide that identifier.
            Otherwise, it will be inferred from the provenance of the `spiny_neuron` entity.""",
            default=None,
        )
        edge_population_name: str = Field(
            title="Edge population name",
            description="Name of the edge population to write the synapse information into",
            default="synaptome_afferents",
        )
        node_population_pre: str = Field(
            title="Presynaptic node population name",
            description="""Name of the node population to write the information about the
            innervating neurons into""",
            default="synaptome_afferent_neurons",
        )
        node_population_post: str = Field(
            title="Postsynaptic node population name",
            description="""Name of the node population to write the information about the
            synaptome neuron into""",
            default="biophysical_neuron",
        )

    initialize: Initialize


class EMSynapseMappingSingleConfig(EMSynapseMappingScanConfig, SingleConfigMixin):
    pass
