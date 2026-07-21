"""Task wrapper for the BluePyEModel optimisation step.

Runs optimisation + analysis + export in a single task. Seeds the working
directory from extraction features and entity downloads, reconstructs the
optimisation recipe, and runs the full pipeline.
"""

import json
import logging
from pathlib import Path
from typing import ClassVar

import entitysdk
from pydantic import PrivateAttr

from obi_one.core.task import Task
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID
from obi_one.scientific.tasks.emodel_building import _shared
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.config import (
    EModelOptimizationSingleConfig,
)

L = logging.getLogger(__name__)


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
       ``plot_models()`` → ``export_emodels_hoc()`` / ``export_emodels_sonata()``
       using a ``LocalAccessPoint`` with metadata (emodel, etype, mtype, etc.).
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
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,
    ) -> Path:
        from bluepyemodel.access_point.local import LocalAccessPoint  # noqa: PLC0415
        from bluepyemodel.export_emodel.export_emodel import (  # noqa: PLC0415
            export_emodels_hoc,
            export_emodels_sonata,
        )
        from bluepyemodel.optimisation import (  # noqa: PLC0415
            setup_and_run_optimisation,
            store_best_model,
        )

        init = self.config.initialize
        coord_root = Path(self.config.coordinate_output_root).resolve()
        emodel = init.emodel
        mtype = self._derive_mtype(db_client)

        # --- 1. Download extracted features ---
        extraction_tr = init.target_efeatures
        self._download_extraction_features(extraction_tr, coord_root, db_client)

        # --- 2. Download morphology ---
        morph_filename = self._stage_morphology(coord_root, db_client)

        # --- 3. Download ion channel models (.mod files) ---
        self._stage_mechanisms(coord_root, db_client)

        # --- 4. Fetch traces via derivation chain ---
        trace_ids = self._stage_traces(extraction_tr, coord_root, db_client)

        # --- 5. Stage params file (before building recipe) ---
        params_path = self._stage_params(coord_root)

        # --- 6. Reconstruct recipe ---
        recipes = {}

        morph_dir = "./morphologies/"
        features_path = f"config/features/{emodel}.json"
        recipes[emodel] = {
            "morph_path": morph_dir,
            "morphology": [[mtype, morph_filename]],
            "features": features_path,
            "params": f"config/params/{params_path.name}",
        }

        recipes = _shared.update_pipeline_settings(
            recipes,
            emodel=emodel,
            overrides=self.config.optimization_settings.to_dict(
                self.config.optimization_params,
            ),
        )
        recipes_target = coord_root / "config" / "recipes.json"
        _shared.write_recipes(recipes, recipes_target)

        # --- 6. Compile mechanisms ---
        _shared.compile_mechanisms(coord_root / "mechanisms")

        # --- 7. Run optimisation + store + plot + export ---
        # Species and brain region are taken from the morphology entity (cached
        # by the from-id wrapper, so this does not re-fetch).
        with _shared.chdir(coord_root):
            access_point = LocalAccessPoint(
                emodel=emodel,
                etype=init.etype.entity(db_client=db_client).pref_label,
                mtype=mtype,
                ttype=None,
                species=init.morphology.entity(db_client=db_client).subject.species.name,
                brain_region=init.morphology.entity(db_client=db_client).brain_region.name,
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

            # Export (always — spec says optimisation stage always exports)
            export_emodels_hoc(
                access_point=access_point,
                only_best=False,
                seeds=seeds,
            )
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
        from entitysdk.types import AssetLabel  # noqa: PLC0415

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
        morph_entity = self.config.initialize.morphology
        swc_content = morph_entity.swc_file_content(db_client=db_client)
        # Use entity ID as filename base
        morph_id = morph_entity.id_str
        morph_filename = f"{morph_id}.swc"
        (morph_dir / morph_filename).write_text(
            swc_content,  # ty:ignore[invalid-argument-type]
            encoding="utf-8",
        )
        L.info("Staged morphology: %s", morph_filename)
        return morph_filename

    def _stage_mechanisms(self, coord_root: Path, db_client: entitysdk.client.Client) -> None:
        """Download .mod files from ion channel model entities."""
        mech_dir = coord_root / "mechanisms"
        mech_dir.mkdir(parents=True, exist_ok=True)
        for icm in self.config.parameters_selection.ion_channel_models:
            icm.download_asset(dest_dir=mech_dir, db_client=db_client)
        L.info(
            "Staged %d ion channel models.",
            len(self.config.parameters_selection.ion_channel_models),
        )

    @staticmethod
    def _stage_params(coord_root: Path) -> Path:
        """Stage the params file and return the full Path to it.

        Builds the BluePyEModel params file from the selected ion channel models.
        """
        params_dir = coord_root / "config" / "params"
        params_dir.mkdir(parents=True, exist_ok=True)

        # Dynamic builder mode: TODO - build from ion channel models
        params_path = params_dir / "params.json"
        if not params_path.exists():
            params_path.write_text(
                json.dumps({"mechanisms": [], "distributions": {}, "parameters": []}, indent=4),
                encoding="utf-8",
            )
            L.warning("Wrote placeholder params file. Dynamic builder not yet implemented.")
        return params_path

    def _stage_traces(  # noqa: PLR6301
        self,
        extraction_tr: TaskResultFromID,
        coord_root: Path,  # noqa: ARG002
        db_client: entitysdk.client.Client,
    ) -> list[str]:
        """Fetch trace IDs via derivation chain from extraction TaskResult.

        Returns a list of trace (ElectricalCellRecording) IDs. The actual NWB
        assets are not downloaded because the optimisation stage only needs
        the extracted features and protocols, not the raw traces.
        """
        from entitysdk.models import Derivation  # noqa: PLC0415

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
        morph_entity = self.config.initialize.morphology
        entity = morph_entity.entity(db_client=db_client)
        if hasattr(entity, "mtypes") and entity.mtypes:
            return str(entity.mtypes[0].pref_label)  # ty:ignore[union-attr]
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
        """Upload recipes, params, HOC, and SONATA to the TaskResult for task3."""
        from entitysdk.models import TaskResult  # noqa: PLC0415
        from entitysdk.types import AssetLabel, ContentType  # noqa: PLC0415

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

        # HOC file — needed by task3 for final export
        hoc_dir = coord_root / "export_emodels_hoc"
        hoc_file = None
        if hoc_dir.exists():
            for hf in hoc_dir.rglob("*.hoc"):
                hoc_file = hf
                break
        if hoc_file is not None:
            db_client.upload_file(
                entity_id=task_result_id,  # ty:ignore[invalid-argument-type]
                entity_type=TaskResult,
                file_path=hoc_file,
                file_content_type=ContentType.application_hoc,
                asset_label=AssetLabel.neuron_hoc,
            )
            L.info("Uploaded HOC to TaskResult.")

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

    def register_output_entities(  # noqa: PLR0914
        self,
        coord_root: Path,
        db_client: entitysdk.Client,
        *,
        trace_ids: list | None = None,
        execution_activity_id: str | None = None,
    ) -> None:
        """Register TaskResult, draft EModel, draft MEModel using entitysdk helpers.

        Uses the shared registration helpers from entitysdk PR #252 to ensure
        alignment with the launch-system ``run_optimisation.py`` flow.
        """
        from entitysdk.models import (  # noqa: PLC0415
            License,
            TaskActivity,
        )
        from entitysdk.registration.emodel import register_emodel  # noqa: PLC0415
        from entitysdk.registration.memodel import register_memodel  # noqa: PLC0415
        from entitysdk.registration.task_result.emodel_optimization import (  # noqa: PLC0415
            register_emodel_optimization_result,
        )
        from entitysdk.types import (  # noqa: PLC0415
            EntityLifecycleStatus,
            ValidationStatus,
        )

        init = self.config.initialize
        emodel_name = init.emodel
        seed = int(self.config.optimization_settings.seed)  # ty:ignore[invalid-argument-type]

        # --- Gather metadata ---
        # Species and brain region come from the morphology entity, so the
        # registered emodel/me-model inherit the morphology's provenance.
        morph_entity = self.config.initialize.morphology.entity(db_client=db_client)
        brain_region_entity = morph_entity.brain_region
        species_entity = morph_entity.subject.species

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
        ion_channel_models = [
            icm.entity(db_client=db_client)
            for icm in self.config.parameters_selection.ion_channel_models
        ]

        # --- Register draft EModel via helper ---
        hoc_dir = coord_root / "export_emodels_hoc"
        hoc_file = None
        if hoc_dir.exists():
            for hf in hoc_dir.rglob("*.hoc"):
                hoc_file = hf
                break

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
            validateion_result_status=False,
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
