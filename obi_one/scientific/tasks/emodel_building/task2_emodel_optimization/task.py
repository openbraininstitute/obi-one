"""Task wrapper for the BluePyEModel optimisation step.

Registered ``TaskConfig``s produced from this stage are normally executed by a
remote launch-system worker, not by calling :meth:`EModelOptimizationTask.execute`
locally: the worker stages entity assets, builds the versioned params/recipe
artifacts via this module's compiler, runs BluePyEModel/NEURON, and registers the
draft result. ``execute()`` remains available as an optional, lowest-priority local
diagnostic (see the Task 2 living plan) and performs the full local pipeline:
downloads extraction features and entity assets, builds and stages the
params/recipe artifact bundle, compiles mechanisms, runs the full BluePyEModel
pipeline, registers output entities, and runs MEModel calibration + bluecellulab
validation in isolated subprocesses.

The BluePyEModel optimisation/plot/export steps live in
:func:`run_optimization_pipeline` so remote workers can reuse them after their own
staging without going through :class:`EModelOptimizationTask`.
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
    calibration_validation,
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


def tag_local_mechanisms(
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


def fresh_morph_modifiers(pipeline_settings: Any) -> list[str] | None:
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


def run_optimization_pipeline(
    *,
    config: EModelOptimizationSingleConfig,
    coord_root: Path,
    normalized_models: dict[str, NormalizedIonChannelModel],
    mtype: str | None,
    etype: str,
    species: str,
    brain_region: str,
) -> None:
    """Run BluePyEModel optimisation, plot, and SONATA export.

    Expects ``coord_root`` to already contain staged features, morphology, compiled
    mechanisms, and the params/recipe artifact bundle. Does not compile mechanisms,
    stage assets, or register entities.
    """
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
    from bluepyemodel.tools.checkpoint_hdf5 import (  # ruff: ignore[import-outside-top-level]
        convert_checkpoint,
    )

    emodel = config.initialize.emodel

    class EntityCoreLocalAccessPoint(LocalAccessPoint):
        """Use downloaded mechanisms and EntityCore metadata without Nexus lookup."""

        def get_available_mechanisms(self) -> list[Any] | None:
            mechanisms = super().get_available_mechanisms()
            return tag_local_mechanisms(mechanisms, normalized_models)

        def get_model_configuration(self, *args: Any, **kwargs: Any) -> Any:
            """Hand every evaluator build its own morphology-modifier list."""
            configuration = super().get_model_configuration(*args, **kwargs)
            configuration.morph_modifiers = fresh_morph_modifiers(self.pipeline_settings)
            return configuration

    with chdir(coord_root):
        access_point = EntityCoreLocalAccessPoint(
            emodel=emodel,
            etype=etype,
            mtype=mtype,
            ttype=None,
            species=species,
            brain_region=brain_region,
            iteration_tag=None,
            recipes_path="./config/recipes.json",
        )

        mapper = map
        seeds = [config.optimization_settings.seed]
        for seed in seeds:
            setup_and_run_optimisation(
                access_point,
                seed=seed,
                mapper=mapper,
                terminator=None,
            )
            store_best_model(access_point=access_point, seed=seed)

        # Convert pkl checkpoints to HDF5 for storage and registration.
        # BluePyOpt always writes .pkl; we convert after each seed so that
        # the .h5 files are present even if a later seed fails.
        checkpoint_dir = coord_root / "checkpoints"
        if checkpoint_dir.exists():
            for pkl_path in sorted(checkpoint_dir.rglob("*.pkl")):
                h5_path = pkl_path.with_suffix(".h5")
                if not h5_path.exists():
                    L.info("Converting checkpoint %s → %s", pkl_path.name, h5_path.name)
                    convert_checkpoint(str(pkl_path), str(h5_path))

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

    L.info("Completed optimisation pipeline for emodel=%s.", emodel)


def run_calibration_and_validation(
    *,
    config: EModelOptimizationSingleConfig,
    coord_root: Path,
    db_client: entitysdk.Client,
    outputs: registration.RegisteredOptimizationOutputs,
    execution_activity_id: str | None,
) -> None:
    """Compute MEModel calibration and run bluecellulab validations in subprocesses.

    Runs against the local SONATA HOC + already-compiled mechanisms; the
    morphology's ASC asset is downloaded via entitysdk (optimisation stages
    SWC, but calibration/validation cells are built from ASC). Results are
    registered against the registered MEModel (``outputs.memodel_id``), so this
    must run after :func:`registration.register_output_entities`.

    Non-fatal by design: any failure is logged as a warning and leaves the
    registered entities untouched (``validation_status`` stays ``created``).
    """
    try:  # ruff: ignore[too-many-statements-in-try-clause]
        seed = int(config.optimization_settings.seed)  # ty:ignore[invalid-argument-type]
        asc_morphology_path = calibration_validation.download_asc_morphology(
            db_client,
            config.initialize.morphology,
            coord_root / "morphologies",
        )
        hoc_path, morphology_path = calibration_validation.locate_hoc_and_morphology(
            coord_root, seed, asc_morphology_path
        )
        em_metrics = registration.parse_final_json(
            coord_root / "final.json", config.initialize.emodel
        )
        new_ids: list[str] = []

        # --- Calibration ---
        calibration_dict = calibration_validation.compute_calibration_in_subprocess(
            coord_root,
            hoc_path,
            morphology_path,
            holding_current=em_metrics["holding_current"] or 0.0,
            threshold_current=em_metrics["threshold_current"] or 0.0,
        )
        calibration_id = registration.register_calibration_result(
            db_client,
            outputs.memodel_id,
            calibration_dict,
            authorized_public=outputs.authorized_public,
        )
        if calibration_id is not None:
            new_ids.append(calibration_id)

        # --- Validation (uses calibrated values for cell init, falls back to BPEM) ---
        validation_dict = calibration_validation.run_validations_in_subprocess(
            coord_root,
            hoc_path,
            morphology_path,
            outputs.memodel_id,
            holding_current=calibration_dict["holding_current"],
            threshold_current=calibration_dict["rheobase"],
            output_dir=coord_root / "figures",
        )
        new_ids.extend(
            registration.register_memodel_validation_results(
                db_client,
                outputs.memodel_id,
                validation_dict,
                authorized_public=outputs.authorized_public,
                details_dir=coord_root / "validation_details" / outputs.memodel_id,
            )
        )
        registration.mark_memodel_validated(db_client, outputs.memodel_id)

        # --- Extend TaskActivity generated_ids (update replaces the whole list) ---
        registration.update_activity_generated_ids(
            db_client,
            execution_activity_id,
            outputs.generated_ids + new_ids,
        )
    except Exception:  # ruff: ignore[blind-except]
        L.warning(
            "MEModel calibration/validation failed for memodel=%s; "
            "registered entities are kept (validation_status remains 'created').",
            outputs.memodel_id,
            exc_info=True,
        )


class EModelOptimizationTask(Task):
    """Run optimisation + analysis + export in a fresh working directory.

    Steps performed in ``coordinate_output_root``:

    1. Download extracted features from the extraction ``TaskResult``.
    2. Download morphology SWC from ``CellMorphology`` entity.
    3. Download ion channel model ``.mod`` files.
    4. Fetch trace IDs via the derivation chain without downloading raw traces.
    5. Reconstruct the optimisation recipe and merge optimisation settings.
    6. Compile mechanisms via ``nrnivmodl``.
    7. Run optimisation / plot / SONATA export via :func:`run_optimization_pipeline`.
    8. Register ``TaskResult`` + draft ``EModel`` + draft ``MEModel`` +
       ``Derivation`` links.
    9. Compute MEModel calibration and run bluecellulab validations in spawned
       subprocesses; register ``MEModelCalibrationResult`` + ``ValidationResult``
       entities against the MEModel (non-fatal on failure) via
       :func:`run_calibration_and_validation`.
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

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: str | None = None,
    ) -> Path:
        init = self.config.initialize
        coord_root = Path(self.config.coordinate_output_root).resolve()
        mtype = staging.derive_mtype(self.config, db_client)

        # --- 1. Download extracted features ---
        extraction_tr = self.config.initialize.target_efeatures
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

        # --- 7. Run optimisation / plot / export ---
        etype_entity = init.etype.entity(db_client=db_client)
        species_entity, brain_region_entity = self.config.initialize.morphology.metadata_entities(
            db_client=db_client
        )
        run_optimization_pipeline(
            config=self.config,
            coord_root=coord_root,
            normalized_models=normalized_models,
            mtype=mtype,
            etype=etype_entity.pref_label,  # ty:ignore[unresolved-attribute]
            species=species_entity.name,
            brain_region=brain_region_entity.name,
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

            # --- 9. MEModel calibration + validation (non-fatal) ---
            run_calibration_and_validation(
                config=self.config,
                coord_root=coord_root,
                db_client=db_client,
                outputs=outputs,
                execution_activity_id=execution_activity_id,
            )

        return coord_root
