"""Task wrapper for the BluePyEModel optimisation step."""

import logging
from pathlib import Path
from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.tasks.emodel_optimization import _shared
from obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.task import (
    EXTRACTED_FEATURES_FILENAME,
)
from obi_one.scientific.tasks.emodel_optimization._02_emodel_optimization.config import (
    EModelOptimizationSingleConfig,
)

L = logging.getLogger(__name__)


class EModelOptimizationTask(Task):
    """Run ``pipeline.optimise(seed=...)`` in a fresh working directory.

    Steps performed in ``coordinate_output_root``:

    1. Seed ``ephys_data/`` and ``extracted_features.json`` from
       ``initialize.previous_stage_output_path``.
    2. Copy the morphologies, mechanisms, and params from the user-provided
       paths and compile the mod files via ``nrnivmodl``.
    3. Copy the user's ``recipes.json``, merge the optimisation-related
       ``pipeline_settings`` overrides, and write to ``./config/recipes.json``.
    4. Move the extracted features into the path referenced by
       ``recipes[<emodel>]['features']`` so ``EModel_pipeline`` can read them.
    5. ``chdir`` into the working directory and run ``pipeline.optimise``.
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

        # 1. Seed the ephys data + extracted features from the previous stage.
        _shared.seed_working_dir_from_previous(previous, coord_root)

        # 2. Copy the model assets (morphologies, mechanisms, params) and
        #    compile the mechanisms.
        _shared.copy_tree(Path(init.morphology_path).resolve(), coord_root / "morphologies")
        _shared.copy_tree(Path(init.mechanisms_path).resolve(), coord_root / "mechanisms")
        params_target = coord_root / "config" / "params" / Path(init.params_path).name
        _shared.copy_tree(Path(init.params_path).resolve(), params_target)
        if (
            not (coord_root / "x86_64" / "special").exists()
            and not (coord_root / "arm64" / "special").exists()
        ):
            _shared.compile_mechanisms(coord_root / "mechanisms")

        # 3. Copy the user's recipes and merge optimisation pipeline_settings.
        recipes = _shared.load_recipes(Path(init.recipes_path).resolve())
        recipes = _shared.update_pipeline_settings(
            recipes,
            emodel=init.emodel,
            overrides=self.config.optimization_settings.to_dict(
                self.config.optimization_params,
            ),
        )
        recipes_target = coord_root / "config" / "recipes.json"
        _shared.write_recipes(recipes, recipes_target)

        # 4. Place the extracted features where the recipe expects them.
        extracted_features = coord_root / EXTRACTED_FEATURES_FILENAME
        if not extracted_features.exists():
            msg = (
                f"Expected {extracted_features} to be carried over from the previous"
                " stage. Did the extraction stage complete successfully?"
            )
            raise FileNotFoundError(msg)
        features_target = coord_root / recipes[init.emodel]["features"]
        features_target.parent.mkdir(parents=True, exist_ok=True)
        _shared.copy_tree(extracted_features, features_target)

        # 5. Run optimise.
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
