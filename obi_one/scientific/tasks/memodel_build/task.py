import logging
from pathlib import Path
from typing import ClassVar

import entitysdk
from entitysdk.downloaders.memodel import download_memodel
from entitysdk.models import MEModel
from entitysdk.types import ValidationStatus

from obi_one.core.task import Task
from obi_one.scientific.library.memodel_calibration_validation import (
    compute_calibration_and_validation,
)
from obi_one.scientific.library.simulation.neuron.process import compile_mechanisms
from obi_one.scientific.tasks.memodel_build import registration
from obi_one.scientific.tasks.memodel_build.config import MEModelBuildSingleConfig
from obi_one.types import SimulationBackend

L = logging.getLogger(__name__)

# Starting currents for calibration, before the ME-model's own are known.
INITIAL_HOLDING_CURRENT = 0.0
INITIAL_THRESHOLD_CURRENT = 0.1
DOWNLOAD_CONCURRENCY = 8
# Matches the 4 cores of the launch definition and the former Bluenaas validation job.
VALIDATION_PROCESSES = 4
VALIDATION_FIGURES_DIRNAME = "validation_figures"


def stage_memodel(
    db_client: entitysdk.Client, memodel: MEModel, coord_root: Path
) -> tuple[Path, Path]:
    """Download the ME-model's hoc, morphology and mechanisms and compile the mechanisms.

    Returns:
        The hoc path and the morphology path, preferring asc over swc over h5.
    """
    downloaded = download_memodel(
        db_client, memodel=memodel, output_dir=coord_root, max_concurrent=DOWNLOAD_CONCURRENCY
    )
    compile_mechanisms(
        output_dir=coord_root,
        mechanisms_dirs=[downloaded.mechanisms_dir],
        simulation_backend=SimulationBackend.bluecellulab,
    )
    return downloaded.hoc_path, downloaded.morphology_paths[0]


class MEModelBuildTask(Task):
    """See docs/memodel-build.md. A failure after registration sets ``validation_status=error``."""

    name: ClassVar[str] = "ME-model Build"
    description: ClassVar[str] = (
        "Combine a morphology and an e-model into an ME-model, then calibrate and validate it."
    )

    config: MEModelBuildSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: str | None = None,
    ) -> str:
        coord_root = Path(self.config.coordinate_output_root).resolve()
        execution_activity = self._get_execution_activity(
            db_client=db_client, execution_activity_id=execution_activity_id
        )
        authorized_public = bool(execution_activity and execution_activity.authorized_public)

        memodel = registration.register_memodel(
            self.config, db_client, authorized_public=authorized_public
        )
        self._update_execution_activity(
            db_client=db_client,
            execution_activity=execution_activity,
            generated=[str(memodel.id)],
        )

        try:
            hoc_path, morphology_path = stage_memodel(db_client, memodel, coord_root)
            results = compute_calibration_and_validation(
                coord_root,
                hoc_path,
                morphology_path,
                cell_name=self.config.info.campaign_name,
                holding_current=INITIAL_HOLDING_CURRENT,
                threshold_current=INITIAL_THRESHOLD_CURRENT,
                output_dir=coord_root / VALIDATION_FIGURES_DIRNAME,
                n_processes=VALIDATION_PROCESSES,
            )
            registration.register_calibration_and_validation(
                db_client,
                memodel_id=memodel.id,
                calibration=results["calibration"],
                validation=results["validation"],
                authorized_public=authorized_public,
            )
        except Exception:
            registration.set_validation_status(
                db_client, memodel_id=memodel.id, validation_status=ValidationStatus.error
            )
            raise

        registration.set_validation_status(
            db_client, memodel_id=memodel.id, validation_status=ValidationStatus.done
        )
        L.info("ME-model build completed: %s", memodel.id)
        return str(memodel.id)
