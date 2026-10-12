"""Task wrapper for the BluePyEModel e-model re-validation step (Task 3).

Task 2 already validates the optimised model against its held-out protocols. Task 3
re-validates a registered EModel against other targets (e.g. a fresh extraction),
another morphology or other settings: it rebuilds the working directory of the
optimisation that produced the EModel (see :mod:`.staging`), scores the optimised model
with :mod:`..validation_scoring` and registers the results (see :mod:`.registration`).
"""

import json
import logging
from pathlib import Path
from typing import Any, ClassVar

import entitysdk
from pydantic import PrivateAttr

from obi_one.core.task import Task
from obi_one.scientific.tasks.emodel_building import utils as emodel_building_utils
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.task import (
    create_entitycore_access_point,
)
from obi_one.scientific.tasks.emodel_building.task3_emodel_validation import (
    registration,
    staging,
)
from obi_one.scientific.tasks.emodel_building.task3_emodel_validation.config import (
    EModelValidationSingleConfig,
)
from obi_one.scientific.tasks.emodel_building.validation_scoring import score_model_isolated
from obi_one.utils.filesystem import chdir

L = logging.getLogger(__name__)

FIGURES_DIRNAME = "figures"
RESULTS_FILENAME = "validation_results.json"


def run_validation_pipeline(
    *,
    coord_root: Path,
    staged: staging.StagedValidation,
    mapper: Any = map,
) -> dict:
    """Score the staged optimised model and plot its scores and traces."""
    from bluepyemodel.emodel_pipeline import plotting  # ruff: ignore[import-outside-top-level]

    entry = staged.final_entry
    emodel_name = entry["emodel"]
    seed = int(entry["seed"])
    access_point_kwargs: dict[str, Any] = {
        "normalized_models": staged.normalized_models,
        "emodel": emodel_name,
        "etype": entry.get("etype"),
        "mtype": entry.get("mtype"),
        "species": entry.get("species"),
        "brain_region": entry.get("brain_region"),
        "iteration_tag": entry.get("iteration"),
    }
    summary = score_model_isolated(
        access_point_factory=create_entitycore_access_point,
        access_point_kwargs=access_point_kwargs,
        working_dir=coord_root,
        seed=seed,
        settings=staged.settings,
    )
    with chdir(coord_root):
        access_point = create_entitycore_access_point(**access_point_kwargs)
        plotting.plot_models(
            access_point=access_point,
            mapper=mapper,
            seeds=[seed],
            figures_dir=Path(FIGURES_DIRNAME) / emodel_name,
            plot_optimisation_progress=False,
            plot_parameter_evolution=False,
            plot_distributions=False,
            plot_scores=True,
            plot_traces=True,
            plot_thumbnail=False,
            plot_dendritic_ISI_CV=False,
            plot_dendritic_rheobase=False,
        )

    (coord_root / RESULTS_FILENAME).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


class EModelValidationTask(Task):
    """Re-validate an optimised EModel with BluePyEModel in a fresh working directory.

    Steps performed in ``coordinate_output_root``:

    1. Resolve the optimisation activity, TaskConfig and TaskResult of the EModel.
    2. Stage targets (optimisation or other extraction), morphology (exemplar or other),
       mechanisms, the params/recipe bundle and the optimised ``final.json`` entry.
    3. Compile mechanisms via ``nrnivmodl``.
    4. Score the model and plot scores/traces via :func:`run_validation_pipeline`.
    5. Register a ``TaskResult`` and ``ValidationResult`` entities on the EModel.
    """

    name: ClassVar[str] = "EModel Validation"
    description: ClassVar[str] = (
        "Score an optimised e-model against held-out or freshly extracted e-features"
        " with BluePyEModel."
    )

    config: EModelValidationSingleConfig

    _summary: dict | None = PrivateAttr(default=None)

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: str | None = None,
    ) -> Path:
        coord_root = Path(self.config.coordinate_output_root).resolve()
        staged = staging.stage_working_directory(self.config, coord_root, db_client)
        emodel_building_utils.compile_mechanisms(coord_root / "mechanisms")
        self._summary = run_validation_pipeline(coord_root=coord_root, staged=staged)
        registration.register_output_entities(
            self.config,
            coord_root,
            db_client,
            staged=staged,
            summary=self._summary,
            figures_dir=coord_root / FIGURES_DIRNAME,
            execution_activity_id=execution_activity_id,
        )
        return coord_root
