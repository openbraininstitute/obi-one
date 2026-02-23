import logging
from pathlib import Path
from typing import ClassVar

import entitysdk
from entitysdk import Client, models
from entitysdk.models.activity import Activity
from entitysdk.types import AssetLabel

from obi_one.core.task import Task
from obi_one.scientific.tasks.skeletonization.config import SkeletonizationSingleConfig
from obi_one.scientific.tasks.skeletonization.constants import (
    CELL_MORPHOLOGY_PROTOCOL_DESCRIPTION,
    CELL_MORPHOLOGY_PROTOCOL_NAME,
)
from obi_one.scientific.tasks.skeletonization.process import create_process_outputs, run_process
from obi_one.scientific.tasks.skeletonization.registration import register_output_resource
from obi_one.scientific.tasks.skeletonization.schemas import (
    Metadata,
    ProcessParameters,
    SkeletonizationInputs,
    WorkDir,
)
from obi_one.scientific.tasks.skeletonization.utils import create_work_dir

L = logging.getLogger(__name__)


class SkeletonizationTask(Task):
    config: SkeletonizationSingleConfig
    activity_type: ClassVar[type[Activity]] = models.SkeletonizationExecution

    @property
    def work_dir(self) -> WorkDir:
        """Return the current working directory layout."""
        return create_work_dir(output_dir=self.config.coordinate_output_root)

    def _create_inputs(self, db_client: Client, output_dir: Path) -> SkeletonizationInputs:
        """Generate all inputs for skeletonization task."""
        em_cell_mesh = db_client.get_entity(
            entity_id=self.config.initialize.cell_mesh.id_str,
            entity_type=models.EMCellMesh,
        )
        em_cell_mesh_asset = db_client.download_assets(
            entity_or_id=em_cell_mesh,
            selection={"label": AssetLabel.cell_surface_mesh},
            output_path=output_dir,
        ).one()
        em_dense_reconstruction_dataset = None
        if entity := em_cell_mesh.em_dense_reconstruction_dataset:
            em_dense_reconstruction_dataset = db_client.get_entity(
                entity.id,
                entity_type=models.EMDenseReconstructionDataset,
            )
        cell_id = em_cell_mesh.dense_reconstruction_cell_id
        return SkeletonizationInputs(
            metadata=Metadata(
                subject=em_cell_mesh.subject,
                brain_region=em_cell_mesh.brain_region,
                cell_morphology_protocol_name=CELL_MORPHOLOGY_PROTOCOL_NAME,
                cell_morphology_protocol_description=CELL_MORPHOLOGY_PROTOCOL_DESCRIPTION,
                cell_morphology_name=self.config.initialize.cell_mesh.id_str,
                cell_morphology_description=(
                    f"Reconstructed morphology and extracted spines of neuron {cell_id}"
                ),
                em_dense_reconstruction_dataset=em_dense_reconstruction_dataset,
            ),
            parameters=ProcessParameters(
                mesh_path=em_cell_mesh_asset.path,
                neuron_voxel_size=self.config.initialize.neuron_voxel_size,
                spines_voxel_size=self.config.initialize.spines_voxel_size,
                segment_spines=True,
            ),
        )

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client,
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str,
    ) -> None:
        """Execute skeletonization task."""
        work_dir = self.work_dir
        execution_activity = db_client.get_entity(
            entity_id=execution_activity_id,
            entity_type=self.activity_type,
        )
        inputs = self._create_inputs(
            db_client=db_client,
            output_dir=work_dir.inputs,
        )
        run_process(
            parameters=inputs.parameters,
            output_dir=work_dir.outputs,
        )
        outputs = create_process_outputs(output_dir=work_dir.outputs)
        generated_entity = register_output_resource(
            client=db_client,
            metadata=inputs.metadata,
            outputs=outputs,
        )
        db_client.update_entity(
            entity_id=execution_activity.id,
            entity_type=self.activity_type,
            attrs_or_entity={"generated_ids": [str(generated_entity.id)]},
        )
        L.info(f"Skeletonization completed. Output Morphology ID: {generated_entity.id}")
