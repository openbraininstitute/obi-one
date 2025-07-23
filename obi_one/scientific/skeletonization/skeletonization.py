import json
import os
from typing import ClassVar, Literal, Self, Annotated

from pydantic import Field, PrivateAttr, model_validator, NonNegativeInt, NonNegativeFloat, PositiveInt, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.form import Form
from obi_one.core.single import SingleCoordinateMixin
from obi_one.core.info import Info
from obi_one.core.exception import OBIONE_Error

from obi_one.database.circuit_from_id import CircuitFromID

import entitysdk
from collections import OrderedDict

from datetime import UTC, datetime

from pathlib import Path

import logging
L = logging.getLogger(__name__)


class SkelotonizationForm(Form):
    """Skelotonization Form."""

    single_coord_class_name: ClassVar[str] = "Skelotonization"
    name: ClassVar[str] = "Skelotonization Campaign"
    description: ClassVar[str] = "Marwan's awesome skelotonization campaign."

    class Config:
        json_schema_extra = {
            "block_block_group_order": []
        }

    class Initialize(Block):
        mesh_path: Annotated[Path, Field(description="Path to the mesh file to be used for skelotonization.")]
        
        
        # _spike_location: Literal["AIS", "soma"] | list[Literal["AIS", "soma"]] = PrivateAttr(default="soma")


    initialize: Initialize = Field(title="Initialization", description="Parameters for initializing the skelotonization.", group=BlockGroup.SETUP_BLOCK_GROUP, group_order=1)
    info: Info = Field(title="Info", description="Information about the simulation campaign.", group=BlockGroup.SETUP_BLOCK_GROUP, group_order=0)


    def initialize_db_campaign(self, output_root: Path, multiple_value_parameters_dictionary={}, db_client: entitysdk.client.Client=None):

        """Initializes the simulation campaign in the database."""
        L.info("1. Initializing simulation campaign in the database...")

        L.info(f"-- Register SimulationCampaign Entity")
        self._campaign = db_client.register_entity(
            entitysdk.models.SimulationCampaign(
                name=self.info.campaign_name,
                description=self.info.campaign_description,
                entity_id=self.initialize.circuit.id_str if isinstance(self.initialize.circuit, CircuitFromID) else self.initialize.circuit[0].id_str,
                scan_parameters=multiple_value_parameters_dictionary,
            )
        )

        L.info(f"-- Upload campaign_generation_config")
        _ = db_client.upload_file(
            entity_id=self._campaign.id,
            entity_type=entitysdk.models.SimulationCampaign,
            file_path=output_root / "run_scan_config.json",
            file_content_type="application/json",
            asset_label='campaign_generation_config'
        )

        # L.info(f"-- Upload campaign_summary")
        # _ = db_client.upload_file(
        #     entity_id=self._campaign.id,
        #     entity_type=entitysdk.models.SimulationCampaign,
        #     file_path=Path(output_root, "bbp_workflow_campaign_config.json"),
        #     file_content_type="application/json",
        #     asset_label='campaign_summary'
        # )

        return self._campaign
    
    def save(self, simulations, db_client: entitysdk.client.Client) -> None:

        L.info("3. Saving completed simulation campaign generation")

        L.info(f"-- Register SimulationGeneration Entity")
        db_client.register_entity(
            entitysdk.models.SimulationGeneration(
                start_time=datetime.now(UTC),
                used=[self._campaign],
                generated=simulations,
            )
        )

        return None

   
class Skelotonization(SkelotonizationForm, SingleCoordinateMixin):
    """Only allows single values and ensures nested attributes follow the same rule."""

    CONFIG_FILE_NAME: ClassVar[str] = "simulation_config.json"
    NODE_SETS_FILE_NAME: ClassVar[str] = "node_sets.json"

    _sonata_config: dict = PrivateAttr(default={})

    def generate(self, db_client: entitysdk.client.Client = None):
        """Generates SONATA simulation config .json file."""



        command = ""
        command += str(self.pixels) + str(self.mesh_path)
        

        # # Write simulation config file (.json)
        # simulation_config_path = os.path.join(self.coordinate_output_root, self.CONFIG_FILE_NAME)
        # with open(simulation_config_path, "w") as f:
        #     json.dump(self._sonata_config, f, indent=2)


    def save(self, campaign: entitysdk.models.SimulationCampaign, db_client: entitysdk.client.Client) -> None:
        """Saves the simulation to the database."""
        
        L.info(f"2.{self.idx} Saving simulation {self.idx} to database...")
        
        L.info(f"-- Register Simulation Entity")
        simulation = db_client.register_entity(
            entitysdk.models.Simulation(
                name=f"Simulation {self.idx}",
                description=f"Simulation {self.idx}",
                scan_parameters=self.single_coordinate_scan_params.dictionary_representaiton(),
                entity_id=self._circuit_id,
                simulation_campaign_id=campaign.id,
                
            )
        )

        L.info(f"-- Upload simulation_generation_config")
        _ = db_client.upload_file(
            entity_id=simulation.id,
            entity_type=entitysdk.models.Simulation,
            file_path=Path(self.coordinate_output_root, "run_coordinate_instance.json"),
            file_content_type="application/json",
            asset_label='simulation_generation_config'
        )

        L.info(f"-- Upload sonata_simulation_config")
        _ = db_client.upload_file(
            entity_id=simulation.id,
            entity_type=entitysdk.models.Simulation,
            file_path=Path(self.coordinate_output_root, "simulation_config.json"),
            file_content_type="application/json",
            asset_label='sonata_simulation_config'
        )
        
        L.info(f"-- Upload custom_node_sets")
        _ = db_client.upload_file(
            entity_id=simulation.id,
            entity_type=entitysdk.models.Simulation,
            file_path=Path(self.coordinate_output_root, "node_sets.json"),
            file_content_type="application/json",
            asset_label='custom_node_sets'
        )

        L.info(f"-- Upload spike replay files")
        for input in self._sonata_config["inputs"]:
            if "spike_file" in list(self._sonata_config["inputs"][input]):
                spike_file = self._sonata_config["inputs"][input]["spike_file"]
                if spike_file is not None:
                    _ = db_client.upload_file(
                        entity_id=simulation.id,
                        entity_type=entitysdk.models.Simulation,
                        file_path=Path(self.coordinate_output_root, spike_file),
                        file_content_type="application/x-hdf5",
                        asset_label='replay_spikes'
                    )

        return simulation