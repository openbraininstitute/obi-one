"""Task wrapper for the BluePyEModel analysis & validation step."""

import logging
from pathlib import Path
from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.tasks.emodel_optimization import _shared
from obi_one.scientific.tasks.emodel_optimization._03_analysis_and_validation.config import (
    EModelAnalysisAndValidationSingleConfig,
)

L = logging.getLogger(__name__)


class EModelAnalysisAndValidationTask(Task):
    """Run ``store_optimisation_results``, ``validation``, ``plot`` for one config."""

    name: ClassVar[str] = "EModel Analysis and Validation"
    description: ClassVar[str] = (
        "Run BluePyEModel analysis, validation, and plotting on optimisation results."
    )

    config: EModelAnalysisAndValidationSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> Path:
        from bluepyemodel.emodel_pipeline.emodel_pipeline import (  # noqa: PLC0415
            EModel_pipeline,
        )

        init = self.config.initialize
        coord_root = Path(self.config.coordinate_output_root).resolve()
        previous = Path(init.previous_stage_output_path).resolve()

        _shared.seed_working_dir_from_previous(previous, coord_root)

        if (
            not (coord_root / "x86_64" / "special").exists()
            and not (coord_root / "arm64" / "special").exists()
        ):
            _shared.compile_mechanisms(coord_root / "mechanisms")

        recipes_path = coord_root / "config" / "recipes.json"
        recipes = _shared.load_recipes(recipes_path)
        recipes = _shared.update_pipeline_settings(
            recipes,
            emodel=init.emodel,
            overrides=self.config.analysis_settings.to_dict(self.config.currentscape_config),
        )
        _shared.write_recipes(recipes, recipes_path)

        with _shared.chdir(coord_root):
            pipeline = EModel_pipeline(
                emodel=init.emodel,
                etype=init.etype,
                mtype=init.mtype,
                ttype=init.ttype,
                species=init.species,
                brain_region=init.brain_region,
                recipes_path="./config/recipes.json",
                iteration_tag=init.iteration_tag,
                use_ipyparallel=init.use_ipyparallel,
                use_multiprocessing=init.use_multiprocessing,
            )
            pipeline.store_optimisation_results()
            pipeline.validation()
            pipeline.plot(only_validated=self.config.analysis_settings.only_validated_plots)

        return coord_root
