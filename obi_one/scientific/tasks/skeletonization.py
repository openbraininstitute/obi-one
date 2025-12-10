import abc
import logging
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar, Literal

import entitysdk
from pydantic import Field, PositiveFloat, PrivateAttr

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig

import logging
from pathlib import Path
from typing import ClassVar

import entitysdk
from pydantic import PrivateAttr

from obi_one.core.block import Block
from obi_one.core.task import Task
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.memodel_circuit import MEModelCircuit
from obi_one.scientific.from_id.em_cell_mesh_from_id import EMCellMeshFromID

from obi_one.scientific.tasks.generate_simulation_configs import (
    CircuitSimulationSingleConfig,
    MEModelSimulationSingleConfig,
    MEModelWithSynapsesCircuitSimulationSingleConfig,
)

import httpx
import os
import time 
import json 
import pathlib
from uuid import UUID
from urllib.parse import urlparse
from IPython.display import display, HTML
from obi_auth import get_token
from obi_notebook import get_projects, get_entities
from entitysdk.client import Client
from entitysdk.models import CellMorphology
from entitysdk.models.asset import AssetLabel


L = logging.getLogger(__name__)


class SkeletonizationScanConfig(ScanConfig, abc.ABC):
    """Abstract base class for skeletonization scan configurations."""

    single_coord_class_name: ClassVar[str]
    name: ClassVar[str] = "Skeletonization Campaign"
    description: ClassVar[str] = "Skeletonization campaign"

    # _campaign: entitysdk.models.SimulationCampaign = None

    class Initialize(Block):
        cell_mesh: EMCellMeshFromID

        neuron_voxel_size: Annotated[PositiveFloat, Field(ge=0.001, le=1.0)] | list[Annotated[PositiveFloat, Field(ge=0.001, le=1.0)]] = Field(
            default=0.1,
            title="Neuron Voxel Size",
            description="Neuron reconstruction resolution in micrometers.",
            units="μm",
        )

        spines_voxel_size: Annotated[PositiveFloat, Field(ge=0.001, le=0.1)] | list[Annotated[PositiveFloat, Field(ge=0.001, le=0.1)]] = Field(
            default=0.05,
            title="Spine Voxel Size",
            description="Spine reconstruction resolution in micrometers.",
            units="μm",
        )

        segment_spines: bool = Field(
            default=True,
            title="Segment Spines",
            description="Segment dendritic spines from the neuron morphology."
        )
        

    info: Info = Field(
        title="Info",
        description="Information about the skeletonization campaign.",
        # group=BlockGroup.SETUP_BLOCK_GROUP,
        # group_order=0,
    )

    def create_campaign_entity_with_config(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: entitysdk.client.Client = None,
    ) -> entitysdk.models.SimulationCampaign:
        # """Initializes the simulation campaign in the database."""
        # L.info("1. Initializing simulation campaign in the database...")
        # if multiple_value_parameters_dictionary is None:
        #     multiple_value_parameters_dictionary = {}

        # L.info("-- Register SimulationCampaign Entity")
        # if isinstance(
        #     self.initialize.circuit,
        #     (CircuitFromID, MEModelFromID, MEModelWithSynapsesCircuitFromID),
        # ):
        #     entity_id = self.initialize.circuit.id_str
        # elif isinstance(self.initialize.circuit, list):
        #     if len(self.initialize.circuit) != 1:
        #         msg = "Only single circuit/MEModel currently supported for \
        #             simulation campaign database persistence."
        #         raise OBIONEError(msg)
        #     entity_id = self.initialize.circuit[0].id_str

        # self._campaign = db_client.register_entity(
        #     entitysdk.models.SimulationCampaign(
        #         name=self.info.campaign_name,
        #         description=self.info.campaign_description,
        #         entity_id=entity_id,
        #         scan_parameters=multiple_value_parameters_dictionary,
        #     )
        # )

        # L.info("-- Upload campaign_generation_config")
        # _ = db_client.upload_file(
        #     entity_id=self._campaign.id,
        #     entity_type=entitysdk.models.SimulationCampaign,
        #     file_path=output_root / "run_scan_config.json",
        #     file_content_type="application/json",
        #     asset_label="campaign_generation_config",
        # )

        return self._campaign

    def create_campaign_generation_entity(
        self, simulations: list[entitysdk.models.Simulation], db_client: entitysdk.client.Client
    ) -> None:
        L.info("3. Saving completed simulation campaign generation")

        # L.info("-- Register SimulationGeneration Entity")
        # db_client.register_entity(
        #     entitysdk.models.SimulationGeneration(
        #         start_time=datetime.now(UTC),
        #         used=[self._campaign],
        #         generated=simulations,
        #     )
        # )



class SkeletonizationSingleConfig(
    SkeletonizationScanConfig, SingleConfigMixin
):
    _single_entity: entitysdk.models.Simulation

    @property
    def single_entity(self) -> entitysdk.models.Simulation:
        return self._single_entity

    def create_single_entity_with_config(
        self, campaign: entitysdk.models.SimulationCampaign, db_client: entitysdk.client.Client
    ) -> entitysdk.models.Simulation:
        """Saves the simulation to the database."""
        L.info(f"2.{self.idx} Saving simulation {self.idx} to database...")


        # L.info("-- Register Simulation Entity")
        # self._single_entity = db_client.register_entity(
        #     entitysdk.models.Simulation(
        #         name=f"Simulation {self.idx}",
        #         description=f"Simulation {self.idx}",
        #         scan_parameters=self.single_coordinate_scan_params.dictionary_representaiton(),
        #         entity_id=self.initialize.circuit.id_str,
        #         simulation_campaign_id=campaign.id,
        #     )
        # )

        # L.info("-- Upload simulation_generation_config")
        # _ = db_client.upload_file(
        #     entity_id=self.single_entity.id,
        #     entity_type=entitysdk.models.Simulation,
        #     file_path=Path(self.coordinate_output_root, "run_coordinate_instance.json"),
        #     file_content_type="application/json",
        #     asset_label="simulation_generation_config",
        # )





class GenerateSimulationTask(Task):
    config: (
        CircuitSimulationSingleConfig
        | MEModelSimulationSingleConfig
        | MEModelWithSynapsesCircuitSimulationSingleConfig
    )

    CONFIG_FILE_NAME: ClassVar[str] = "simulation_config.json"
    NODE_SETS_FILE_NAME: ClassVar[str] = "node_sets.json"

    _sonata_config: dict = PrivateAttr(default={})
    _circuit: Circuit | MEModelCircuit | None = PrivateAttr(default=None)
    _entity_cache: bool = PrivateAttr(default=False)


    def _setup_input_task_params(self):
        input_params = {
            "name": mesh_id,
            "description": f"Reconstructed morphology and extracted spines of neuron {input_entity.dense_reconstruction_cell_id}."
        }


    # def _setup_clients(
    #     self, db_client: entitysdk.client.Client
    # ) -> None:
        
    #     # Initialize the client and search for EMCellMesh entities
    #     client = Client(environment=environment, token_manager=token, project_context=project_context)
    #     entitycore_api_url = urlparse(client.api_url)
    #     platform_base_url = f"{entitycore_api_url.scheme}://{entitycore_api_url.netloc}"
    #     mesh_api_base_url = f"{platform_base_url}/api/small-scale-simulator/mesh/skeletonization"

    #     http_client = httpx.Client()

        # token = os.getenv("OBI_AUTHENTICATION_TOKEN")
        # project_context = db_client.project_context

    #     mesh_api_headers = httpx.Headers({
    #         "Authorization": f"Bearer {token}",
    #         "virtual-lab-id": str(project_context.virtual_lab_id),
    #         "project-id": str(project_context.project_id)
    #     })

    # def _submit_skeletonization_task(
    #     self, db_client: entitysdk.client.Client
    # ) -> UUID:
        
    #     start_res = http_client.post(
    #     f"{mesh_api_base_url}/run",
    #         params=skeletonization_params,
    #         headers=mesh_api_headers,
    #         json=input_params
    #     )

    #     job_id = None
    #     if start_res.is_success:
    #         job_id = start_res.json().get("id")
    #     else:
    #         print(start_res.text)
    #         raise RuntimeError("Failed to submit mesh skeletonization task")

    # def _wait_for_skeletonization_task_completion(
    #     self, db_client: entitysdk.client.Client, job_id: UUID
    # ) -> UUID:
    #     output_morphology_id = None
    #     prev_status = None

    #     while True:
    #     status_res = http_client.get(
    #         f"{mesh_api_base_url}/jobs/{job_id}",
    #         headers=mesh_api_headers
    #     )

    #     if not status_res.is_success:
    #         print(status_res.text)
    #         raise RuntimeError("Failed to get job status")

    #     job = status_res.json()
    #     status = job.get('status')

    #     if status != prev_status:
    #         print(f"{time.strftime("%H:%M:%S", time.localtime())}  Status: {status}")
    #         prev_status = status

    #     if status == 'finished':
    #         output_morphology_id = UUID(job.get('output').get('morphology').get('id'))
    #         break
    #     elif status == 'failed':
    #         print(json.dumps(job, indent=2))
    #         raise RuntimeError("Skeletonization failed")

    #     time.sleep(15)

    # def _get_new_morphology(db_client: entitysdk.client.Client, morphology_id: UUID) -> CellMorphology:
    #     cell_morphology = db_client.get_entity(output_morphology_id, entity_type=CellMorphology)
    #     asset = next((asset for asset in cell_morphology.assets if asset.label == AssetLabel.morphology_with_spines), None)

    #     # Download the file
    #     db_client.download_assets(cell_morphology,selection={"label": AssetLabel.morphology_with_spines}, output_path=pathlib.Path(os.getcwd())).one()




    def execute(
        self, *, db_client: entitysdk.client.Client = None, entity_cache: bool = False
    ) -> None:
        
        
        # self._setup_input_task_params(db_client)

        # self._setup_clients(db_client)

        # job_id = self._submit_skeletonization_task(db_client)

        # output_morphology_id = self._wait_for_skeletonization_task_completion(
        #     db_client, job_id
        # )

        # L.info(f"Skeletonization completed. Output Morphology ID: {output_morphology_id}")

        # self._get_new_morphology(db_client, output_morphology_id)