import logging
from pathlib import Path

import entitysdk
from entitysdk import Client, models
from entitysdk.types import AssetLabel, ContentType

from obi_one.core.task import Task
from obi_one.scientific.tasks.skeletonization.config import SkeletonizationSingleConfig
from obi_one.scientific.tasks.skeletonization.constants import (
    CELL_MORPHOLOGY_PROTOCOL_DESCRIPTION,
    CELL_MORPHOLOGY_PROTOCOL_NAME,
)
from obi_one.scientific.tasks.skeletonization.process import run_process
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

    @property
    def work_dir(self) -> WorkDir:
        """Return the current working directory layout."""
        return create_work_dir(output_dir=self.config.coordinate_output_root)

    def _create_inputs(self, db_client: Client, output_dir: Path) -> SkeletonizationInputs:
        """Generate all inputs for skeletonization task."""
        L.info("Creating inputs...")
        em_cell_mesh = db_client.get_entity(
            entity_id=self.config.initialize.cell_mesh.id_str,  # ty:ignore[invalid-argument-type, unresolved-attribute]
            entity_type=models.EMCellMesh,
        )
        em_cell_mesh_asset = db_client.fetch_assets(
            entity_or_id=em_cell_mesh,
            selection={
                "label": AssetLabel.cell_surface_mesh,
                "content_type": ContentType.model_gltf_binary,
            },
            output_path=output_dir,
        ).one()
        # fetch the full dataset from the nested Entity
        em_dense_reconstruction_dataset = db_client.get_entity(
            em_cell_mesh.em_dense_reconstruction_dataset.id,  # ty:ignore[invalid-argument-type, unresolved-attribute]
            entity_type=models.EMDenseReconstructionDataset,
        )
        cell_id = em_cell_mesh.dense_reconstruction_cell_id
        return SkeletonizationInputs(
            metadata=Metadata(
                subject=em_cell_mesh.subject,  # ty:ignore[invalid-argument-type]
                brain_region=em_cell_mesh.brain_region,  # ty:ignore[invalid-argument-type]
                cell_morphology_protocol_name=CELL_MORPHOLOGY_PROTOCOL_NAME,
                cell_morphology_protocol_description=CELL_MORPHOLOGY_PROTOCOL_DESCRIPTION,
                cell_morphology_name=self.config.initialize.cell_mesh.id_str,  # ty:ignore[unresolved-attribute]
                cell_morphology_description=(
                    f"Reconstructed morphology and extracted spines of neuron {cell_id}"
                ),
                em_dense_reconstruction_dataset=em_dense_reconstruction_dataset,
            ),
            parameters=ProcessParameters(
                mesh_path=em_cell_mesh_asset.path,
                neuron_voxel_size=self.config.initialize.neuron_voxel_size,  # ty:ignore[invalid-argument-type]
                spines_voxel_size=self.config.initialize.spines_voxel_size,  # ty:ignore[invalid-argument-type]
                segment_spines=True,
                write_raw_spines=self.config.initialize.write_raw_spines,
            ),
        )

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client,
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None,
    ) -> None:
        """Execute the skeletonization task.

        This method prepares inputs, runs the skeletonization process,
        and optionally registers the outputs in the database.

        Args:
            db_client: Client used to interact with the database.
            entity_cache: Unused parameter
            execution_activity_id:
                The ID of the execution activity entity.

                If provided, the execution is considered *tracked*:
                the generated outputs are registered in the database and
                linked to the corresponding activity entity.

                If ``None``, the execution is considered *local*:
                the process runs and produces outputs on disk, but no data
                is registered in the database and no entities are updated.

        Note:
            When ``execution_activity_id`` is ``None``, the execution runs
            locally and does **not** register any generated resources in
            the database.
        """
        work_dir = self.work_dir
        msg = f"WorkDir: {work_dir}"
        L.info(msg)

        execution_activity = SkeletonizationTask._get_execution_activity(
            db_client=db_client, execution_activity_id=execution_activity_id
        )
        inputs = self._create_inputs(
            db_client=db_client,
            output_dir=work_dir.inputs,
        )
        outputs = run_process(
            work_dir=work_dir,
            parameters=inputs.parameters,
        )
        if execution_activity_id is not None:
            L.info("Registering entities...")
            generated_entity = register_output_resource(
                client=db_client,
                metadata=inputs.metadata,
                outputs=outputs,
            )

            SkeletonizationTask._update_execution_activity(
                db_client=db_client,
                execution_activity=execution_activity,
                generated=[str(generated_entity.id)],
            )

        L.info(
            f"Skeletonization completed. Output Morphology ID: "
            f"{generated_entity.id if generated_entity else None}"
        )
