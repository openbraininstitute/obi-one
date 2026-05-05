"""Task wrapper for the BluePyEModel optimisation step."""

import logging
from pathlib import Path
from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.tasks.emodel_optimization import _shared
from obi_one.scientific.tasks.emodel_optimization._02_emodel_optimization.config import (
    EModelOptimizationSingleConfig,
)

L = logging.getLogger(__name__)


class EModelOptimizationTask(Task):
    """Run ``pipeline.optimise(seed=...)`` in a fresh working directory.

    Steps performed in ``coordinate_output_root``:

    1. Copy the BluePyEModel working directory from
       ``initialize.previous_stage_output_path``.
    2. Recompile the mechanisms if a host arch directory wasn't carried over.
    3. Merge the optimisation-related ``pipeline_settings`` overrides into
       ``./config/recipes.json``.
    4. ``chdir`` into the working directory and run ``pipeline.optimise``.
    """

    name: ClassVar[str] = "EModel Optimization"
    description: ClassVar[str] = (
        "Run BluePyEModel parameter optimisation against extracted features."
    )

    config: EModelOptimizationSingleConfig

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

        # 1. Seed the working directory from the previous stage's output.
        _shared.seed_working_dir_from_previous(previous, coord_root)

        # 2. Make sure the mechanisms are compiled (the previous stage's output
        #    may have been produced on a different host arch).
        if (
            not (coord_root / "x86_64" / "special").exists()
            and not (coord_root / "arm64" / "special").exists()
        ):
            _shared.compile_mechanisms(coord_root / "mechanisms")

        # 3. Merge optimisation-related pipeline_settings overrides.
        recipes_path = coord_root / "config" / "recipes.json"
        recipes = _shared.load_recipes(recipes_path)
        recipes = _shared.update_pipeline_settings(
            recipes,
            emodel=init.emodel,
            overrides=self.config.optimization_settings.to_dict(
                self.config.optimization_params,
            ),
        )
        _shared.write_recipes(recipes, recipes_path)

        # 4. Run optimise.
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
            pipeline.optimise(seed=self.config.optimization_settings.seed)

        return coord_root
