import logging
import os
from pathlib import Path
from typing import ClassVar

import entitysdk
from entitysdk.downloaders.memodel import download_memodel
from entitysdk.models import MEModel, TaskActivity
from entitysdk.registration.memodel import register_memodel_calibration_result
from entitysdk.registration.validation_result import register_memodel_validation_results
from entitysdk.schemas.memodel import DownloadedMEModel
from entitysdk.types import ID, ValidationStatus

from obi_one.core.task import Task
from obi_one.scientific.library.memodel_calibration_validation import (
    compute_calibration_in_subprocess,
    run_validations_in_subprocess,
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
# Launch-system jobs validate on the CPUs they were given (JOB_CPUS); other runs, such as
# Bluenaas, on as many as the former Bluenaas validation job.
DEFAULT_VALIDATION_PROCESSES = 4
VALIDATION_FIGURES_DIRNAME = "validation_figures"


def stage_memodel(
    db_client: entitysdk.Client, memodel_id: ID, coord_root: Path
) -> DownloadedMEModel:
    """Download the ME-model's hoc, morphology and mechanisms.

    The first morphology path is the one to use: asc over swc over h5.
    """
    memodel = db_client.get_entity(entity_id=memodel_id, entity_type=MEModel)
    return download_memodel(
        db_client, memodel=memodel, output_dir=coord_root, max_concurrent=DOWNLOAD_CONCURRENCY
    )


def calibrate_and_validate(
    db_client: entitysdk.Client,
    memodel_id: ID,
    coord_root: Path,
    staged: DownloadedMEModel,
    *,
    authorized_public: bool,
) -> None:
    hoc_path, morphology_path = staged.hoc_path, staged.morphology_paths[0]
    calibration = compute_calibration_in_subprocess(
        coord_root,
        hoc_path,
        morphology_path,
        holding_current=INITIAL_HOLDING_CURRENT,
        threshold_current=INITIAL_THRESHOLD_CURRENT,
    )
    # registered before validating, so the ME-model can be simulated while validation runs
    register_memodel_calibration_result(
        client=db_client,
        calibrated_entity_id=memodel_id,
        holding_current=calibration["holding_current"],
        threshold_current=calibration["rheobase"],
        rin=calibration.get("rin"),
        authorized_public=authorized_public,
    )
    validation = run_validations_in_subprocess(
        coord_root,
        hoc_path,
        morphology_path,
        cell_name=str(memodel_id),
        holding_current=calibration["holding_current"],
        threshold_current=calibration["rheobase"],
        output_dir=coord_root / VALIDATION_FIGURES_DIRNAME,
        n_processes=int(os.environ.get("JOB_CPUS") or DEFAULT_VALIDATION_PROCESSES),
    )
    register_memodel_validation_results(
        client=db_client,
        memodel_id=memodel_id,
        validation_dict=validation,
        authorized_public=authorized_public,
    )


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

        try:
            self._build(
                db_client,
                memodel,
                execution_activity,
                coord_root,
                authorized_public=authorized_public,
            )
        except Exception:
            try:
                registration.set_validation_status(
                    db_client, memodel_id=memodel.id, validation_status=ValidationStatus.error
                )
            except Exception:  # ruff: ignore[blind-except]
                L.exception("Could not set validation_status=error on MEModel %s", memodel.id)
            raise

        L.info("ME-model build completed: %s", memodel.id)
        return str(memodel.id)

    def _build(
        self,
        db_client: entitysdk.Client,
        memodel: MEModel,
        execution_activity: TaskActivity | None,
        coord_root: Path,
        *,
        authorized_public: bool,
    ) -> None:
        self._update_execution_activity(
            db_client=db_client,
            execution_activity=execution_activity,
            generated=[str(memodel.id)],
        )
        registration.register_creator_and_classifications(self.config, db_client, memodel)
        staged = stage_memodel(db_client, memodel.id, coord_root)
        compile_mechanisms(
            output_dir=coord_root,
            mechanisms_dirs=[staged.mechanisms_dir],
            simulation_backend=SimulationBackend.bluecellulab,
        )
        calibrate_and_validate(
            db_client, memodel.id, coord_root, staged, authorized_public=authorized_public
        )
        registration.set_validation_status(
            db_client, memodel_id=memodel.id, validation_status=ValidationStatus.done
        )
