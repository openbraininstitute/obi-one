from typing import ClassVar

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID

from enum import StrEnum

class BlockGroup(StrEnum):
    """Authentication and authorization errors."""

    SETUP_BLOCK_GROUP = "Setup"

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

    json_schema_extra_additions: ClassVar[dict] = {
        "ui_enabled": True,
        "group_order": [
            BlockGroup.SETUP_BLOCK_GROUP,
        ],
    }

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

    info: Info = Field(  # type: ignore[]
        title="Info",
        description="Information about ...",
        json_schema_extra={
            "ui_element": "block_single",
            "group": BlockGroup.SETUP_BLOCK_GROUP,
            "group_order": 0,
        },
    )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing...",
        json_schema_extra={
            "ui_element": "block_single",
            "group": BlockGroup.SETUP_BLOCK_GROUP,
            "group_order": 1,
        },
    )


    def create_campaign_entity_with_config(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: entitysdk.client.Client = None,
    ) -> Config:

        self._campaign = db_client.register_entity(
            entitysdk.models.SimulationCampaign(
                name=self.info.campaign_name,
                description=self.info.campaign_description,
                entity_id=entity_id,
                scan_parameters=multiple_value_parameters_dictionary,
            )
        )

        L.info("-- Upload campaign_generation_config")
        _ = db_client.upload_file(
            entity_id=self._campaign.id,
            entity_type=entitysdk.models.SimulationCampaign,
            file_path=output_root / _SCAN_CONFIG_FILENAME,
            file_content_type="application/json",
            asset_label="campaign_generation_config",
        )

        return self._campaign

    def create_campaign_generation_entity(
        self, simulations: list[entitysdk.models.Simulation], db_client: entitysdk.client.Client
    ) -> None:
        L.info("3. Saving completed simulation campaign generation")

        L.info("-- Register SimulationGeneration Entity")
        db_client.register_entity(
            entitysdk.models.SimulationGeneration(
                start_time=datetime.now(UTC),
                used=[self._campaign],
                generated=simulations,
            )
        )


class EMSynapseMappingSingleConfig(EMSynapseMappingScanConfig, SingleConfigMixin):
    pass
