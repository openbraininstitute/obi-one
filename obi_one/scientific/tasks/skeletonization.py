import abc
import json
import logging
import os
import time
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar
from urllib.parse import urlparse
from uuid import UUID

import entitysdk
import httpx
from pydantic import Field, PositiveFloat, PrivateAttr

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.from_id.em_cell_mesh_from_id import EMCellMeshFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import _COORDINATE_CONFIG_FILENAME, _SCAN_CONFIG_FILENAME
from obi_one.scientific.library.memodel_circuit import MEModelCircuit

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Authentication and authorization errors."""

    SETUP_BLOCK_GROUP = "Setup"


class SkeletonizationScanConfig(ScanConfig, abc.ABC):
    """Abstract base class for skeletonization scan configurations."""

    single_coord_class_name: ClassVar[str] = "SkeletonizationSingleConfig"
    name: ClassVar[str] = "Skeletonization Campaign"
    description: ClassVar[str] = "Skeletonization campaign"

    _campaign: entitysdk.models.SkeletonizationCampaign = None

    class Config:
        json_schema_extra: ClassVar[dict] = {
            "ui_enabled": True,
            "group_order": [
                BlockGroup.SETUP_BLOCK_GROUP,
            ],
        }

    class Initialize(Block):
        cell_mesh: EMCellMeshFromID | list[EMCellMeshFromID] = Field(
            ui_element="model_identifier",
            title="EM Cell Mesh",
            description="EM cell mesh to use for skeletonization.",
        )

        neuron_voxel_size: (
            Annotated[PositiveFloat, Field(ge=0.1, le=0.5)]
            | list[Annotated[PositiveFloat, Field(ge=0.1, le=0.5)]]
        ) = Field(
            ui_element="float_parameter_sweep",
            default=0.1,
            title="Neuron Voxel Size",
            description="Neuron reconstruction resolution in micrometers.",
            units="μm",
        )

        spines_voxel_size: (
            Annotated[PositiveFloat, Field(ge=0.1, le=0.5)]
            | list[Annotated[PositiveFloat, Field(ge=0.1, le=0.5)]]
        ) = Field(
            ui_element="float_parameter_sweep",
            default=0.1,
            title="Spine Voxel Size",
            description="Spine reconstruction resolution in micrometers.",
            units="μm",
        )

    info: Info = Field(
        ui_element="root_block",
        title="Info",
        description="Information about the skeletonization campaign.",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=0,
    )

    initialize: Initialize = Field(
        ui_element="root_block"
        title="Initialization",
        description="Parameters for initializing the skeletonization.",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=1,
    )

    def create_campaign_entity_with_config(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: entitysdk.client.Client = None,
    ) -> entitysdk.models.SkeletonizationCampaign:
        """Initializes the simulation campaign in the database."""
        L.info("1. Initializing simulation campaign in the database...")

        if multiple_value_parameters_dictionary is None:
            multiple_value_parameters_dictionary = {}

        L.info("-- Register SimulationCampaign Entity")
        if isinstance(
            self.initialize.cell_mesh,
            EMCellMeshFromID,
        ):
            input_meshes = [self.initialize.cell_mesh.entity(db_client)]

        elif isinstance(self.initialize.cell_mesh, list):
            if len(self.initialize.cell_mesh) > 0:
                input_meshes = [mesh.entity(db_client) for mesh in self.initialize.cell_mesh]
            else:
                msg = "No cell meshes provided for skeletonization campaign!"
                raise OBIONEError(msg)

        self._campaign = db_client.register_entity(
            entitysdk.models.SkeletonizationCampaign(
                name=self.info.campaign_name,
                description=self.info.campaign_description,
                input_meshes=input_meshes,
                scan_parameters=multiple_value_parameters_dictionary,
            )
        )

        L.info("-- Upload campaign_generation_config")
        _ = db_client.upload_file(
            entity_id=self._campaign.id,
            entity_type=entitysdk.models.SkeletonizationCampaign,
            file_path=output_root / _SCAN_CONFIG_FILENAME,
            file_content_type="application/json",
            asset_label="campaign_generation_config",
        )

        return self._campaign

    def create_campaign_generation_entity(
        self,
        skeletonization_configs: list[entitysdk.models.SkeletonizationConfig],
        db_client: entitysdk.client.Client,
    ) -> None:
        L.info("3. Saving completed simulation campaign generation")

        L.info("-- Register SimulationGeneration Entity")
        db_client.register_entity(
            entitysdk.models.SkeletonizationConfigGeneration(
                start_time=datetime.now(UTC),
                used=[self._campaign],
                generated=skeletonization_configs,
            )
        )


class SkeletonizationSingleConfig(SkeletonizationScanConfig, SingleConfigMixin):
    _single_entity: entitysdk.models.SkeletonizationConfig

    @property
    def single_entity(self) -> entitysdk.models.SkeletonizationConfig:
        return self._single_entity

    def set_single_entity(self, entity: entitysdk.models.SkeletonizationConfig) -> None:
        """Sets the single entity attribute to the given entity."""
        self._single_entity = entity

    def create_single_entity_with_config(
        self, campaign: entitysdk.models.SkeletonizationCampaign, db_client: entitysdk.client.Client
    ) -> entitysdk.models.SkeletonizationConfig:
        """Saves the SkeletonizationConfig to the database."""
        L.info(f"2.{self.idx} Saving SkeletonizationConfig {self.idx} to database...")

        L.info("-- Register SkeletonizationConfig Entity")
        self._single_entity = db_client.register_entity(
            entitysdk.models.SkeletonizationConfig(
                name=f"SkeletonizationConfig {self.idx}",
                description=f"SkeletonizationConfig {self.idx}",
                scan_parameters=self.single_coordinate_scan_params.dictionary_representaiton(),
                skeletonization_campaign_id=campaign.id,
                em_cell_mesh_id=self.initialize.cell_mesh.id_str,
            )
        )

        L.info("-- Upload skeltonization_config asset")
        L.info(Path(self.coordinate_output_root, _COORDINATE_CONFIG_FILENAME))
        L.info(self.single_entity)
        L.info(self.single_entity.id)
        _ = db_client.upload_file(
            entity_id=self.single_entity.id,
            entity_type=entitysdk.models.SkeletonizationConfig,
            file_path=Path(self.coordinate_output_root, _COORDINATE_CONFIG_FILENAME),
            file_content_type="application/json",
            asset_label="skeletonization_config",
        )


class SkeletonizationTask(Task):
    config: SkeletonizationSingleConfig

    CONFIG_FILE_NAME: ClassVar[str] = "simulation_config.json"
    NODE_SETS_FILE_NAME: ClassVar[str] = "node_sets.json"

    _sonata_config: dict = PrivateAttr(default={})
    _circuit: Circuit | MEModelCircuit | None = PrivateAttr(default=None)
    _entity_cache: bool = PrivateAttr(default=False)

    # Segment Spines, Segment dendritic spines from the neuron morphology.
    _segment_spines: bool = PrivateAttr(
        default=True,
    )

    def _setup_input_task_params(self, db_client: entitysdk.client.Client) -> None:
        self._input_params = {
            "name": self.config.initialize.cell_mesh.id_str,
            "description": f"Reconstructed morphology and extracted spines of neuron \
                {self.config.initialize.cell_mesh.entity(db_client).dense_reconstruction_cell_id}.",
        }

        self._skeletonization_params = {
            "em_cell_mesh_id": self.config.initialize.cell_mesh.id_str,
            "neuron_voxel_size": self.config.initialize.neuron_voxel_size,
            "spines_voxel_size": self.config.initialize.spines_voxel_size,
            "segment_spines": self._segment_spines,
        }

    def _setup_clients(self, db_client: entitysdk.client.Client) -> None:
        # Initialize the client and search for EMCellMesh entities

        entitycore_api_url = urlparse(db_client.api_url)
        platform_base_url = f"{entitycore_api_url.scheme}://{entitycore_api_url.netloc}"
        self._mesh_api_base_url = (
            f"{platform_base_url}/api/small-scale-simulator/mesh/skeletonization"
        )

        self._http_client = httpx.Client()

        token = os.getenv("OBI_AUTHENTICATION_TOKEN")
        project_context = db_client.project_context

        self._mesh_api_headers = httpx.Headers(
            {
                "Authorization": f"Bearer {token}",
                "virtual-lab-id": str(project_context.virtual_lab_id),
                "project-id": str(project_context.project_id),
            }
        )

    def _submit_skeletonization_task(self) -> UUID:
        start_res = self._http_client.post(
            f"{self._mesh_api_base_url}/run",
            params=self._skeletonization_params,
            headers=self._mesh_api_headers,
            json=self._input_params,
        )

        job_id = None
        if start_res.is_success:
            job_id = start_res.json().get("id")
        else:
            L.error(start_res.text)
            msg = "Failed to start mesh skeletonization task"
            raise RuntimeError(msg)

        return UUID(job_id)

    def _wait_for_skeletonization_task_completion(self, job_id: UUID) -> UUID:
        output_morphology_id = None
        prev_status = None

        while True:
            status_res = self._http_client.get(
                f"{self._mesh_api_base_url}/jobs/{job_id}", headers=self._mesh_api_headers
            )

            if not status_res.is_success:
                L.error(status_res.text)
                msg = "Failed to get job status"
                raise RuntimeError(msg)

            job = status_res.json()
            status = job.get("status")

            if status != prev_status:
                L.info(f"{time.strftime('%H:%M:%S', time.localtime())}  Status: {status}")
                prev_status = status

            if status == "finished":
                output_morphology_id = UUID(job.get("output").get("morphology").get("id"))
                return output_morphology_id
            if status == "failed":
                L.error(json.dumps(job, indent=2))
                msg = "Skeletonization failed"
                raise RuntimeError(msg)

            time.sleep(15)

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,
        entity_cache: bool = False,  # noqa: ARG002
    ) -> None:
        self._setup_input_task_params(db_client)

        self._setup_clients(db_client)

        job_id = self._submit_skeletonization_task()

        output_morphology_id = self._wait_for_skeletonization_task_completion(job_id)

        L.info(f"Skeletonization completed. Output Morphology ID: {output_morphology_id}")
