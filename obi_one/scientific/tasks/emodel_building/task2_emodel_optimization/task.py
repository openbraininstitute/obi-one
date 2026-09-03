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

import inspect
import json
import logging
from pathlib import Path
from typing import Any, ClassVar

import entitysdk
from pydantic import PrivateAttr

from obi_one.core.task import Task
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID
from obi_one.scientific.tasks.emodel_building import _shared
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.artifacts import (
    OptimizationArtifacts,
    build_optimization_artifacts,
    build_optimization_recipe,  # ruff: ignore[unused-import]
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.config import (
    EModelOptimizationSingleConfig,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.parameter_builder import (
    NormalizedIonChannelModel,
    resolve_ion_channel_models,
)

from .morphology_preflight import MorphologyCapabilities, preflight_morphology

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


def _validation_status_keyword(register_emodel: Any) -> str:
    """Select the validation-status keyword supported by an EntitySDK helper."""
    try:
        parameters = inspect.signature(register_emodel).parameters
    except (TypeError, ValueError):
        return "validation_result_status"
    if "validation_result_status" in parameters:
        return "validation_result_status"
    if "validateion_result_status" in parameters:
        return "validateion_result_status"
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
        return "validation_result_status"
    msg = (
        "EntitySDK register_emodel does not expose validation_result_status or "
        "validateion_result_status."
    )
    raise TypeError(msg)


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

    def execute(
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
        mtype = self._derive_mtype(db_client)

        # --- 1. Download extracted features ---
        extraction_tr = self.config.inputs.target_efeatures
        self._download_extraction_features(extraction_tr, coord_root, db_client)

        # --- 2. Download and preflight morphology ---
        morph_filename = self._stage_morphology(coord_root, db_client)
        morphology_capabilities = preflight_morphology(
            coord_root / "morphologies" / morph_filename,
            self.config.morphology_settings.axon_modifier,
        )

        # --- 3. Download ion channel models (.mod files) ---
        self._stage_mechanisms(coord_root, db_client)

        # --- 4. Fetch traces via derivation chain ---
        trace_ids = self._stage_traces(extraction_tr, coord_root, db_client)

        # --- 5. Build and stage the versioned params/recipe artifact bundle ---
        normalized_models = resolve_ion_channel_models(
            self.config.parameters_selection.ion_channel_model_references,
            db_client,
        )
        artifacts = self._build_artifacts(
            db_client=db_client,
            mtype=mtype,
            morph_filename=morph_filename,
            morphology_capabilities=morphology_capabilities,
            normalized_models=normalized_models,
        )
        artifacts.write(coord_root)

        # --- 6. Compile mechanisms ---
        _shared.compile_mechanisms(coord_root / "mechanisms")

        # --- 7. Run optimisation + store + plot + export ---
        # Species and brain region are taken from the morphology entity (cached
        # by the from-id wrapper, so this does not re-fetch).
        etype_entity = init.etype.entity(db_client=db_client)
        morphology_entity = self.config.inputs.morphology.entity(db_client=db_client)

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

        with _shared.chdir(coord_root):
            access_point = EntityCoreLocalAccessPoint(
                emodel=emodel,
                etype=etype_entity.pref_label,  # ty:ignore[unresolved-attribute]
                mtype=mtype,
                ttype=None,
                species=morphology_entity.subject.species.name,  # ty:ignore[unresolved-attribute]
                brain_region=morphology_entity.brain_region.name,  # ty:ignore[unresolved-attribute]
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

            _shared.run_plot_models(
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
            self.register_output_entities(
                coord_root,
                db_client,
                trace_ids=trace_ids,
                execution_activity_id=execution_activity_id,
            )

        return coord_root

    # --- Staging helpers ---

    def _download_extraction_features(
        self,
        extraction_tr: TaskResultFromID,
        coord_root: Path,
        db_client: entitysdk.client.Client,
    ) -> Path:
        """Download extracted features JSON from extraction TaskResult."""
        from entitysdk.types import AssetLabel  # ruff: ignore[import-outside-top-level]

        features_dir = coord_root / "config" / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        path = extraction_tr.download_asset_by_label(
            AssetLabel.efeature_extraction_features,
            dest_dir=features_dir,
            db_client=db_client,
        )
        # Rename to <emodel>.json if needed
        target = features_dir / f"{self.config.initialize.emodel}.json"
        if path != target:
            path.rename(target)
        L.info("Staged extracted features: %s", target)
        return target

    def _stage_morphology(self, coord_root: Path, db_client: entitysdk.client.Client) -> str:
        """Download morphology SWC and return the filename."""
        morph_dir = coord_root / "morphologies"
        morph_dir.mkdir(parents=True, exist_ok=True)
        morph_entity = self.config.inputs.morphology
        swc_content = morph_entity.swc_file_content(db_client=db_client)
        # Use entity ID as filename base
        morph_id = morph_entity.id_str
        morph_filename = f"{morph_id}.swc"
        (morph_dir / morph_filename).write_text(
            swc_content,
            encoding="utf-8",
        )
        L.info("Staged morphology: %s", morph_filename)
        return morph_filename

    def _stage_mechanisms(self, coord_root: Path, db_client: entitysdk.client.Client) -> None:
        """Download .mod files from all referenced ion channel model entities."""
        mech_dir = coord_root / "mechanisms"
        mech_dir.mkdir(parents=True, exist_ok=True)
        references = self.config.parameters_selection.ion_channel_model_references
        for reference in references:
            reference.download_asset(dest_dir=mech_dir, db_client=db_client)
        L.info("Staged %d ion channel models.", len(references))

    def _build_artifacts(
        self,
        *,
        db_client: entitysdk.client.Client,
        mtype: str | None,
        morph_filename: str,
        morphology_capabilities: MorphologyCapabilities,
        normalized_models: dict[str, NormalizedIonChannelModel] | None = None,
    ) -> OptimizationArtifacts:
        """Build artifacts from EntityCore metadata resolved by entity IDs."""
        if normalized_models is None:
            references = self.config.parameters_selection.ion_channel_model_references
            normalized_models = resolve_ion_channel_models(references, db_client)
        return build_optimization_artifacts(
            self.config,
            normalized_models,
            mtype=mtype,
            morphology_filename=morph_filename,
            morphology_capabilities=morphology_capabilities,
        )

    def _stage_traces(  # ruff: ignore[no-self-use]
        self,
        extraction_tr: TaskResultFromID,
        coord_root: Path,  # ruff: ignore[unused-method-argument]
        db_client: entitysdk.client.Client,
    ) -> list[str]:
        """Fetch trace IDs via derivation chain from extraction TaskResult.

        Returns a list of trace (ElectricalCellRecording) IDs. The actual NWB
        assets are not downloaded because the optimisation stage only needs
        the extracted features and protocols, not the raw traces.
        """
        from entitysdk.models import Derivation  # ruff: ignore[import-outside-top-level]

        tr_entity = extraction_tr.entity(db_client=db_client)
        derivations = db_client.search_entity(
            entity_type=Derivation,
            query={"generated__id": tr_entity.id},
        )

        trace_ids: list[str] = [
            str(deriv.used.id) for deriv in derivations if deriv.used and deriv.used.id
        ]
        L.info("Found %d trace IDs via derivation chain (assets not downloaded).", len(trace_ids))
        return trace_ids

    def _derive_mtype(self, db_client: entitysdk.client.Client) -> str | None:
        """Derive mtype from the selected morphology entity.

        Uses the first m-type if multiple are available. Returns None when
        the morphology has no m-types, which is acceptable for optimisation.
        """
        morph_entity = self.config.inputs.morphology
        entity = morph_entity.entity(db_client=db_client)
        if hasattr(entity, "mtypes") and entity.mtypes:
            return str(entity.mtypes[0].pref_label)  # ty:ignore[not-subscriptable]
        return None

    @staticmethod
    def _parse_final_json(final_path: Path, emodel_name: str) -> dict:
        """Parse final.json (written by store_best_model) for score, calibration, iteration.

        BluePyEModel's ``store_best_model`` writes ``final.json`` at the
        coordinate output root. Its structure is::

            {emodel_name: [{fitness, holding_current, threshold_current, ...}]}

        Returns a dict with keys: name, total_score, holding_current,
        threshold_current, iteration.
        """
        defaults = {
            "name": emodel_name,
            "total_score": 0.0,
            "holding_current": None,
            "threshold_current": None,
            "iteration": "0",
        }
        if not final_path.exists():
            L.warning("final.json not found at %s; using defaults for registration.", final_path)
            return defaults

        data = json.loads(final_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return defaults

        models = data.get(emodel_name, [])
        if not models:
            # Try the placeholder key "emodel" that extraction stage writes
            models = data.get("emodel", [])
        if not models:
            return defaults

        best = models[0] if isinstance(models, list) else models
        total_score = float(best.get("fitness", best.get("score", 0.0)))
        holding_current = best.get("holding_current")
        threshold_current = best.get("threshold_current")

        # Iteration from the model dict or filename convention
        iteration = str(best.get("iteration", "0"))

        return {
            "name": emodel_name,
            "total_score": total_score,
            "holding_current": holding_current,
            "threshold_current": threshold_current,
            "iteration": iteration,
        }

    # --- Entity registration ---

    @staticmethod
    def _upload_optimization_assets(
        coord_root: Path,
        db_client: entitysdk.Client,
        task_result_id: str,
    ) -> None:
        """Upload recipes, params, and the SONATA export to the TaskResult."""
        from entitysdk.models import TaskResult  # ruff: ignore[import-outside-top-level]
        from entitysdk.types import (  # ruff: ignore[import-outside-top-level]
            AssetLabel,
            ContentType,
        )

        # Recipes.json — needed by task3 to reconstruct pipeline settings
        recipes_path = coord_root / "config" / "recipes.json"
        if recipes_path.exists():
            db_client.upload_file(
                entity_id=task_result_id,  # ty:ignore[invalid-argument-type]
                entity_type=TaskResult,
                file_path=recipes_path,
                file_content_type=ContentType.application_json,
                asset_label=AssetLabel.task_result,
            )
            L.info("Uploaded recipes.json to TaskResult.")

        # Params file — needed by task3 for mechanism parameters
        params_path = coord_root / "config" / "params" / "params.json"
        if params_path.exists():
            db_client.upload_file(
                entity_id=task_result_id,  # ty:ignore[invalid-argument-type]
                entity_type=TaskResult,
                file_path=params_path,
                file_content_type=ContentType.application_json,
                asset_label=AssetLabel.neuron_mechanisms,
            )
            L.info("Uploaded params.json to TaskResult.")

        # SONATA directory — needed by task3 for final export
        sonata_dir = coord_root / "export_emodels_sonata"
        if sonata_dir.exists() and any(sonata_dir.rglob("*")):
            db_client.upload_directory(
                entity_id=task_result_id,  # ty:ignore[invalid-argument-type]
                entity_type=TaskResult,
                paths={p.relative_to(sonata_dir): p for p in sonata_dir.rglob("*") if p.is_file()},
                name=AssetLabel.emodel_optimization_output,
                label=AssetLabel.emodel_optimization_output,
            )
            L.info("Uploaded SONATA to TaskResult.")

    def register_output_entities(  # ruff: ignore[too-many-locals, too-many-statements]
        self,
        coord_root: Path,
        db_client: entitysdk.Client,
        *,
        trace_ids: list | None = None,
        execution_activity_id: str | None = None,
    ) -> None:
        """Register TaskResult, draft EModel, draft MEModel using entitysdk helpers.

        Uses the shared ``entitysdk.registration`` helper package so this local path and
        the remote launch-system worker register output entities identically. Raises
        ``RuntimeError`` if the installed EntitySDK release does not provide that package.
        """
        from entitysdk.models import (  # ruff: ignore[import-outside-top-level]
            License,
            TaskActivity,
        )

        try:
            from entitysdk.registration.emodel import (  # ruff: ignore[import-outside-top-level]  # ty:ignore[unresolved-import]
                register_emodel,
            )
            from entitysdk.registration.memodel import (  # ruff: ignore[import-outside-top-level]  # ty:ignore[unresolved-import]
                register_memodel,
            )
            from entitysdk.registration.task_result.emodel_optimization import (  # ruff: ignore[import-outside-top-level]  # ty:ignore[unresolved-import]
                register_emodel_optimization_result,
            )
        except ModuleNotFoundError as exc:
            msg = (
                "Task 2 output registration requires an EntitySDK release that provides "
                "entitysdk.registration.emodel, entitysdk.registration.memodel, and "
                "entitysdk.registration.task_result.emodel_optimization."
            )
            raise RuntimeError(msg) from exc
        from entitysdk.types import (  # ruff: ignore[import-outside-top-level]
            EntityLifecycleStatus,
            ValidationStatus,
        )

        init = self.config.initialize
        emodel_name = init.emodel
        seed = int(self.config.optimization_settings.seed)  # ty:ignore[invalid-argument-type]

        # --- Gather metadata ---
        # Species and brain region come from the morphology entity, so the
        # registered emodel/me-model inherit the morphology's provenance.
        morph_entity = self.config.inputs.morphology.entity(db_client=db_client)
        brain_region_entity = morph_entity.brain_region  # ty:ignore[unresolved-attribute]
        species_entity = morph_entity.subject.species  # ty:ignore[unresolved-attribute]

        # Fetch license (CC-BY-4.0)
        license_entity = db_client.search_entity(
            entity_type=License,
            query={"name": "CC-BY-4.0"},
        ).one()

        # ETypeClass entity from user selection
        etype_class = init.etype.entity(db_client=db_client)

        # Determine authorized_public from execution activity if available
        authorized_public = False
        if execution_activity_id is not None:
            activity = db_client.get_entity(
                entity_id=execution_activity_id,  # ty:ignore[invalid-argument-type]
                entity_type=TaskActivity,
            )
            authorized_public = getattr(activity, "authorized_public", False)

        # --- Parse emodel JSON for metrics ---
        final_path = coord_root / "final.json"
        em_metrics = self._parse_final_json(final_path, emodel_name)

        # --- Collect file paths for helpers ---
        # Checkpoints: BluePyEModel writes .pkl files by default (not HDF5).
        # The entitysdk helper parameter is named hdf5_checkpoint_file but accepts
        # any checkpoint format.
        checkpoint_dir = coord_root / "checkpoints"
        checkpoint_file = None
        if checkpoint_dir.exists():
            for ckpt in checkpoint_dir.rglob("*.pkl"):
                checkpoint_file = ckpt
                break

        # Figures directory (ensure it exists for the helper)
        figures_dir = coord_root / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)

        # Summary file: use final.json (written by store_best_model)
        final_path = coord_root / "final.json"
        emodel_summary_file = final_path if final_path.exists() else None

        # Collect validation result figure files
        validation_figures: list[Path] = []
        if figures_dir.exists():
            validation_figures = [
                fp
                for fp in sorted(figures_dir.rglob("*"))
                if fp.is_file() and fp.suffix in {".pdf", ".png"}
            ]

        # --- Register TaskResult via helper ---
        task_result = register_emodel_optimization_result(
            client=db_client,
            name=f"EModel Optimization Result — {emodel_name}",
            description=f"Optimisation + analysis + export for emodel '{emodel_name}'.",
            authorized_public=authorized_public,
            hdf5_checkpoint_file=checkpoint_file,
            analysis_figures_dir=figures_dir,
            summary_file=emodel_summary_file,
        )
        L.info("TaskResult registered: %s", task_result.id)

        # --- Upload additional assets needed by task3 (export + validation) ---
        self._upload_optimization_assets(coord_root, db_client, task_result.id)

        # --- Collect ion channel model entities ---
        references = self.config.parameters_selection.ion_channel_model_references
        ion_channel_models = [reference.entity(db_client=db_client) for reference in references]

        # --- Register draft EModel via helper ---
        hoc_file = None
        validation_status_keyword = _validation_status_keyword(register_emodel)
        emodel_entity = register_emodel(
            client=db_client,
            name=f"{emodel_name} (draft)",
            description=f"Draft emodel from optimisation (emodel={emodel_name}).",
            authorized_public=authorized_public,
            species=species_entity,
            brain_region=brain_region_entity,
            license=license_entity,
            seed=seed,
            iteration=em_metrics["iteration"],
            score=em_metrics["total_score"],
            exemplar_morphology=morph_entity,
            ion_channel_models=ion_channel_models,
            lifecycle_status=EntityLifecycleStatus.draft,
            etype_class=etype_class,
            hoc_file=hoc_file,
            emodel_summary_file=emodel_summary_file,
            electrical_cell_recording_ids=trace_ids or [],
            validation_result_figure_files=validation_figures,
            **{validation_status_keyword: False},
        )
        L.info("Draft EModel registered: %s", emodel_entity.id)

        # --- Register draft MEModel via helper ---
        memodel_entity = register_memodel(
            client=db_client,
            name=f"{emodel_name} MEModel (draft)",
            description=f"Draft MEModel from optimisation (emodel={emodel_name}).",
            species=species_entity,
            brain_region=brain_region_entity,
            license=license_entity,
            morphology=morph_entity,
            emodel=emodel_entity,
            threshold_current=em_metrics["threshold_current"],
            holding_current=em_metrics["holding_current"],
            authorized_public=authorized_public,
            validation_status=ValidationStatus.created,
            lifecycle_status=EntityLifecycleStatus.draft,
        )
        L.info("Draft MEModel registered: %s", memodel_entity.id)

        # Store registered entity IDs on the task instance for external access
        self._registered_task_result_id = task_result.id
        self._registered_emodel_id = emodel_entity.id
        self._registered_memodel_id = memodel_entity.id

        # --- Update TaskActivity with generated_ids ---
        if execution_activity_id is not None:
            db_client.update_entity(
                entity_id=execution_activity_id,  # ty:ignore[invalid-argument-type]
                entity_type=TaskActivity,
                attrs_or_entity={
                    "generated_ids": [task_result.id, emodel_entity.id, memodel_entity.id],
                },
            )
