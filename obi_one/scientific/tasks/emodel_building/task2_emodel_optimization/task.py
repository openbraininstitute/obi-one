"""Task wrapper for the BluePyEModel optimisation step.

Registered ``TaskConfig``s produced from this stage are normally executed by a
remote launch-system worker, not by calling :meth:`EModelOptimizationTask.execute`
locally: the worker stages entity assets, builds the versioned params/recipe
artifacts via this module's compiler, runs BluePyEModel/NEURON, and registers the
draft result. ``execute()`` remains available as an optional, lowest-priority local
diagnostic (see the Task 2 living plan) and performs the full local pipeline:
downloads extraction features and entity assets, builds and stages the
params/recipe artifact bundle, compiles mechanisms, runs the full BluePyEModel
pipeline, and registers output entities.
"""

import logging
from pathlib import Path
from typing import Any, ClassVar

import entitysdk
from bluepyemodel.preprocessing import (
    NormalizedIonChannelModel,
    preflight_morphology,
)
from pydantic import PrivateAttr

from obi_one.core.task import Task
from obi_one.scientific.tasks.emodel_building import utils as emodel_building_utils
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization import (
    registration,
    staging,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.config import (
    EModelOptimizationSingleConfig,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.utils import (
    resolve_ion_channel_models,
)
from obi_one.utils.filesystem import chdir

L = logging.getLogger(__name__)


def _tag_local_mechanisms(
    available_mechanisms: list[Any] | None,
    normalized_models: dict[str, NormalizedIonChannelModel],
) -> list[Any] | None:
    """Attach EntityCore metadata to mechanisms discovered from local ``.mod`` files."""
    if available_mechanisms is None:
        return None

    models_by_suffix = {model.nmodl_suffix: model for model in normalized_models.values()}
    for mechanism in available_mechanisms:
        model = models_by_suffix.get(mechanism.name)
        if model is None:
            continue
        mechanism.temperature = model.temperature_celsius
        mechanism.ljp_corrected = model.is_ljp_corrected
        mechanism.id = model.entity_id
    return available_mechanisms


def _fresh_morph_modifiers(pipeline_settings: Any) -> list[str] | None:
    """Return a new morphology-modifier list for a single evaluator build.

    ``bluepyemodel.model.model.define_morphology`` rewrites the list it receives in
    place, replacing each modifier name with its resolved callable. Task 2 builds
    several evaluators from one access point (optimisation, model storage, plotting and
    SONATA export), so a shared list keeps only callables after the first build. The branch
    that also resolves the matching HOC snippet is then skipped, leaving
    ``morph_modifiers_hoc = [None]`` and breaking the HOC generation inside
    ``export_emodels_sonata`` with
    ``TypeError: can only concatenate str (not "NoneType") to str``.

    ``None`` is passed through unchanged so BluePyEModel keeps applying its own
    default modifier, which it resolves into freshly created lists.
    """
    configured = pipeline_settings.morph_modifiers
    if configured is None:
        return None
    return list(configured)


class EModelOptimizationTask(Task):
    """Run optimisation + analysis + export in a fresh working directory.

    Steps performed in ``coordinate_output_root``:

    1. Download extracted features from the extraction ``TaskResult``.
    2. Download morphology SWC from ``CellMorphology`` entity.
    3. Download ion channel model ``.mod`` files.
    4. Fetch trace IDs via the derivation chain without downloading raw traces.
    5. Reconstruct the optimisation recipe and merge optimisation settings.
    6. Compile mechanisms via ``nrnivmodl``.
    7. Run ``setup_and_run_optimisation()`` → ``store_best_model()`` →
       ``plot_models()`` → ``export_emodels_sonata()`` using a ``LocalAccessPoint``
       with metadata (emodel, etype, mtype, etc.).
    8. Register ``TaskResult`` + draft ``EModel`` + draft ``MEModel`` +
       ``Derivation`` links.
    """

    name: ClassVar[str] = "EModel Optimization"
    description: ClassVar[str] = (
        "Run BluePyEModel parameter optimisation against extracted features,"
        " followed by analysis and draft emodel export."
    )

    config: EModelOptimizationSingleConfig

    _registered_task_result_id: str | None = PrivateAttr(default=None)
    _registered_emodel_id: str | None = PrivateAttr(default=None)
    _registered_memodel_id: str | None = PrivateAttr(default=None)

    def execute(  # ruff: ignore[too-many-locals]
        self,
        *,
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: str | None = None,
    ) -> Path:
        from bluepyemodel.access_point.local import (  # ruff: ignore[import-outside-top-level]
            LocalAccessPoint,
        )
        from bluepyemodel.export_emodel.export_emodel import (  # ruff: ignore[import-outside-top-level]
            export_emodels_sonata,
        )
        from bluepyemodel.optimisation import (  # ruff: ignore[import-outside-top-level]
            setup_and_run_optimisation,
            store_best_model,
        )

        init = self.config.initialize
        coord_root = Path(self.config.coordinate_output_root).resolve()
        emodel = init.emodel
        mtype = staging.derive_mtype(self.config, db_client)

        # --- 1. Download extracted features ---
        extraction_tr = self.config.inputs.target_efeatures
        staging.download_extraction_features(self.config, extraction_tr, coord_root, db_client)

        # --- 2. Download and preflight morphology ---
        morph_filename = staging.stage_morphology(self.config, coord_root, db_client)
        morphology_capabilities = preflight_morphology(
            coord_root / "morphologies" / morph_filename,
            self.config.morphology_settings.axon_modifier,
        )

        # --- 3. Download ion channel models (.mod files) ---
        staging.stage_mechanisms(self.config, coord_root, db_client)

        # --- 4. Fetch traces via derivation chain ---
        trace_ids = staging.stage_traces(extraction_tr, db_client)

        # --- 5. Build and stage the versioned params/recipe artifact bundle ---
        normalized_models = resolve_ion_channel_models(
            self.config.parameters_selection.ion_channel_model_references,
            db_client,
        )
        artifacts = staging.build_artifacts(
            self.config,
            db_client=db_client,
            mtype=mtype,
            morph_filename=morph_filename,
            morphology_capabilities=morphology_capabilities,
            normalized_models=normalized_models,
        )
        artifacts.write(coord_root)

        # --- 6. Compile mechanisms ---
        emodel_building_utils.compile_mechanisms(coord_root / "mechanisms")

        # --- 7. Run optimisation + store + plot + export ---
        # Species and brain region are taken from the morphology entity.
        etype_entity = init.etype.entity(db_client=db_client)
        morphology_metadata = self.config.inputs.morphology.metadata_entities(db_client=db_client)

        class EntityCoreLocalAccessPoint(LocalAccessPoint):
            """Use downloaded mechanisms and EntityCore metadata without Nexus lookup."""

            def get_available_mechanisms(self) -> list[Any] | None:
                mechanisms = super().get_available_mechanisms()
                return _tag_local_mechanisms(mechanisms, normalized_models)

            def get_model_configuration(self, *args: Any, **kwargs: Any) -> Any:
                """Hand every evaluator build its own morphology-modifier list."""
                configuration = super().get_model_configuration(*args, **kwargs)
                configuration.morph_modifiers = _fresh_morph_modifiers(self.pipeline_settings)
                return configuration

        with chdir(coord_root):
            access_point = EntityCoreLocalAccessPoint(
                emodel=emodel,
                etype=etype_entity.pref_label,  # ty:ignore[unresolved-attribute]
                mtype=mtype,
                ttype=None,
                species=morphology_metadata[0].name,
                brain_region=morphology_metadata[1].name,
                iteration_tag=None,
                recipes_path="./config/recipes.json",
            )

            mapper = map

            # Optimise
            seeds = [self.config.optimization_settings.seed]
            for seed in seeds:
                setup_and_run_optimisation(
                    access_point,
                    seed=seed,
                    mapper=mapper,
                    terminator=None,
                )
                store_best_model(access_point=access_point, seed=seed)

            emodel_building_utils.run_plot_models(
                access_point=access_point,
                mapper=mapper,
                seeds=seeds,  # ty:ignore[invalid-argument-type]
                figures_dir=Path("./figures") / emodel,
                only_validated=False,
            )

            # Export the SONATA package. It contains the model HOC required by SONATA,
            # but no standalone export_emodels_hoc output is produced.
            export_emodels_sonata(
                access_point=access_point,
                only_best=False,
                seeds=seeds,
                map_function=mapper,
            )

        # --- 8. Register output entities ---
        if db_client is not None:
            outputs = registration.register_output_entities(
                self.config,
                coord_root,
                db_client,
                trace_ids=trace_ids,
                execution_activity_id=execution_activity_id,
            )
            self._registered_task_result_id = outputs.task_result_id
            self._registered_emodel_id = outputs.emodel_id
            self._registered_memodel_id = outputs.memodel_id

        return coord_root
