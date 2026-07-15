"""Task wrapper for the BluePyEModel optimisation step.

Runs optimisation + analysis + export in a single task. Seeds the working
directory from extraction ``TaskResult`` assets and entity downloads, merges
optimisation settings into the recipe, and runs the full pipeline.
"""

import json
import logging
from pathlib import Path
from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID
from obi_one.scientific.tasks.emodel_optimization import _shared
from obi_one.scientific.tasks.emodel_optimization.task2_emodel_optimization.config import (
    EModelOptimizationSingleConfig,
)

L = logging.getLogger(__name__)


class EModelOptimizationTask(Task):
    """Run optimisation + analysis + export in a fresh working directory.

    Steps performed in ``coordinate_output_root``:

    1. Download extraction ``TaskResult`` assets (features, recipes, targets).
    2. Download morphology SWC from ``CellMorphology`` entity.
    3. Download ion channel model ``.mod`` files.
    4. Fetch experimental traces via derivation chain.
    5. Merge optimisation settings into recipe (preserving validation entries).
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

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> Path:
        from bluepyemodel.access_point.local import LocalAccessPoint  # noqa: PLC0415
        from bluepyemodel.emodel_pipeline import plotting  # noqa: PLC0415
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

        # --- 1. Download extraction TaskResult assets ---
        extraction_tr = init.extraction_task_result
        self._download_extraction_features(extraction_tr, coord_root, db_client)
        base_recipes = self._download_extraction_recipes(extraction_tr, coord_root, db_client)
        self._download_extraction_targets(extraction_tr, coord_root, db_client)

        # --- 2. Download morphology ---
        morph_filename = self._stage_morphology(coord_root, db_client)

        # --- 3. Download ion channel models (.mod files) ---
        self._stage_mechanisms(coord_root, db_client)

        # --- 4. Fetch traces via derivation chain ---
        self._stage_traces(extraction_tr, coord_root, db_client)

        # --- 5. Merge recipe ---
        # Rename extraction key ("emodel") to the user-specified emodel name
        if "emodel" in base_recipes and emodel != "emodel":
            base_recipes[emodel] = base_recipes.pop("emodel")
        recipes = base_recipes
        recipes.setdefault(emodel, {})
        recipes[emodel]["morph_path"] = "./morphologies/"
        recipes[emodel]["morphology"] = [[mtype, morph_filename]]
        recipes[emodel]["features"] = f"config/features/{emodel}.json"
        params_filename = self._stage_params(coord_root, db_client)
        recipes[emodel]["params"] = f"config/params/{params_filename}"

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
        if (
            not (coord_root / "x86_64" / "special").exists()
            and not (coord_root / "arm64" / "special").exists()
        ):
            _shared.compile_mechanisms(coord_root / "mechanisms")

        # --- 7. Run optimisation + store + plot + export ---
        with _shared.chdir(coord_root):
            access_point = LocalAccessPoint(
                emodel=emodel,
                etype=init.etype,
                mtype=mtype,
                ttype=None,
                species=init.species,
                brain_region=init.brain_region,
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

            pp_settings = access_point.pipeline_settings
            plotting.plot_models(
                access_point=access_point,
                mapper=mapper,
                seeds=seeds,
                figures_dir=Path("./figures") / emodel,
                plot_optimisation_progress=pp_settings.plot_optimisation_progress,
                optimiser=pp_settings.optimiser,
                plot_parameter_evolution=pp_settings.plot_parameter_evolution,
                plot_distributions=pp_settings.plot_distributions,
                plot_scores=pp_settings.plot_scores,
                plot_traces=pp_settings.plot_traces,
                plot_thumbnail=pp_settings.plot_thumbnail,
                plot_currentscape=pp_settings.plot_currentscape,
                plot_dendritic_ISI_CV=pp_settings.plot_dendritic_ISI_CV,
                plot_dendritic_rheobase=pp_settings.plot_dendritic_rheobase,
                plot_bAP_EPSP=pp_settings.plot_bAP_EPSP,
                plot_IV_curve=pp_settings.plot_IV_curves,
                plot_FI_curve_comparison=pp_settings.plot_FI_curve_comparison,
                plot_phase_plot=pp_settings.plot_phase_plot,
                plot_traces_comparison=pp_settings.plot_traces_comparison,
                run_plot_custom_sinspec=pp_settings.run_plot_custom_sinspec,
                IV_curve_prot_name=pp_settings.IV_curve_prot_name,
                FI_curve_prot_name=pp_settings.FI_curve_prot_name,
                phase_plot_settings=pp_settings.phase_plot_settings,
                sinespec_settings=pp_settings.sinespec_settings,
                custom_bluepyefe_cells_pklpath=pp_settings.custom_bluepyefe_cells_pklpath,
                custom_bluepyefe_protocols_pklpath=pp_settings.custom_bluepyefe_protocols_pklpath,
                only_validated=False,
                save_recordings=pp_settings.save_recordings,
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
            self._register_output_entities(coord_root, db_client)

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

    def _download_extraction_recipes(  # noqa: PLR6301
        self,
        extraction_tr: TaskResultFromID,
        coord_root: Path,  # noqa: ARG002
        db_client: entitysdk.client.Client,
    ) -> dict:
        """Download recipes JSON from extraction TaskResult and return parsed dict."""
        from entitysdk.types import AssetLabel  # noqa: PLC0415

        try:
            recipes_dict = extraction_tr.download_json_asset_by_label(
                AssetLabel.efeature_extraction_protocols,
                db_client=db_client,
            )
        except Exception:  # noqa: BLE001
            L.warning("Could not download extraction recipe; starting with empty recipes.")
            return {}
        else:
            L.info("Downloaded extraction recipes from TaskResult.")
            return recipes_dict

    def _download_extraction_targets(  # noqa: PLR6301
        self,
        extraction_tr: TaskResultFromID,
        coord_root: Path,
        db_client: entitysdk.client.Client,
    ) -> None:
        """Download targets config JSON from extraction TaskResult."""
        from entitysdk.types import AssetLabel  # noqa: PLC0415

        targets_dir = coord_root / "config" / "extract_config"
        targets_dir.mkdir(parents=True, exist_ok=True)
        try:
            extraction_tr.download_asset_by_label(
                AssetLabel.task_result,
                dest_dir=targets_dir,
                db_client=db_client,
            )
            L.info("Staged extraction targets config.")
        except Exception:  # noqa: BLE001
            L.warning("Could not download extraction targets config; optimisation may fail.")

    def _stage_morphology(self, coord_root: Path, db_client: entitysdk.client.Client) -> str:
        """Download morphology SWC and return the filename."""
        morph_dir = coord_root / "morphologies"
        morph_dir.mkdir(parents=True, exist_ok=True)
        morph_entity = self.config.morphology_selection.morphology
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

    def _stage_params(self, coord_root: Path, db_client: entitysdk.client.Client) -> str:  # noqa: ARG002
        """Stage params file — either from params-file mode or dynamic builder."""
        from obi_one.scientific.tasks.emodel_optimization.task2_emodel_optimization.blocks import (  # noqa: PLC0415
            validate_params_file,
        )

        params_dir = coord_root / "config" / "params"
        params_dir.mkdir(parents=True, exist_ok=True)
        params_filename = "params.json"
        params_path = params_dir / params_filename

        # Params-file mode: validate and write the embedded content
        if self.config.use_params_file:
            params_data = self.config.params_file.params_content
            validate_params_file(params_data)
            params_path.write_text(
                json.dumps(params_data, indent=4), encoding="utf-8"
            )
            L.info("Staged validated params file from embedded content.")
            return params_filename

        # Dynamic builder mode: TODO — build from ion channel models
        if not params_path.exists():
            params_path.write_text(
                json.dumps({"mechanisms": [], "distributions": {}, "parameters": []}, indent=4),
                encoding="utf-8",
            )
            L.warning("Wrote placeholder params file. Dynamic builder not yet implemented.")
        return params_filename

    def _stage_traces(  # noqa: PLR6301
        self,
        extraction_tr: TaskResultFromID,
        coord_root: Path,
        db_client: entitysdk.client.Client,
    ) -> None:
        """Fetch experimental traces via derivation chain from extraction TaskResult."""
        from entitysdk.models import Derivation  # noqa: PLC0415

        ephys_dir = coord_root / "ephys_data"
        ephys_dir.mkdir(parents=True, exist_ok=True)

        # Follow derivation chain: extraction TaskResult → ElectricalCellRecording entities
        tr_entity = extraction_tr.entity(db_client=db_client)
        derivations = db_client.search_entity(
            entity_type=Derivation,
            query={"generated_id": tr_entity.id},
        )
        from obi_one.scientific.from_id.electrical_cell_recording_from_id import (  # noqa: PLC0415
            ElectricalCellRecordingFromID,
        )

        for deriv in derivations:
            if deriv.used and deriv.used.id:
                recording = ElectricalCellRecordingFromID(id_str=str(deriv.used.id))
                target_dir = ephys_dir / recording.id_str
                recording.download_asset(dest_dir=target_dir, db_client=db_client)
        L.info("Staged experimental traces via derivation chain.")

    def _derive_mtype(self, db_client: entitysdk.client.Client) -> str:
        """Derive mtype from the selected morphology entity."""
        morph_entity = self.config.morphology_selection.morphology
        entity = morph_entity.entity(db_client=db_client)
        # Try to get mtype from the morphology entity's classification
        if hasattr(entity, "mtype") and entity.mtype:
            return str(entity.mtype)
        # Fallback: use a placeholder
        return "unknown"

    # --- Entity registration ---

    def _register_output_entities(  # noqa: C901, PLR0912, PLR0914, PLR0915
        self,
        coord_root: Path,
        db_client: entitysdk.client.Client,
    ) -> None:
        """Register TaskResult, draft EModel, draft MEModel, and Derivation links."""
        from entitysdk.models import (  # noqa: PLC0415
            Derivation,
            EModel,
            MEModel,
            TaskResult,
        )
        from entitysdk.types import (  # noqa: PLC0415
            AssetLabel,
            ContentType,
            DerivationType,
            TaskResultType,
            ValidationStatus,
        )

        init = self.config.initialize
        emodel_name = init.emodel

        # --- Register TaskResult ---
        task_result = db_client.register_entity(
            TaskResult(
                name=f"EModel Optimization Result — {emodel_name}",
                description=f"Optimisation + analysis + export for emodel '{emodel_name}'.",
                task_result_type=TaskResultType.emodel_optimization__result,
            )
        )
        L.info("TaskResult registered: %s", task_result.id)

        # Upload checkpoint
        checkpoint_dir = coord_root / "checkpoints"
        if checkpoint_dir.exists():
            for ckpt in checkpoint_dir.glob("*.h5"):
                db_client.upload_file(
                    entity_id=task_result.id,  # ty:ignore[invalid-argument-type]
                    entity_type=TaskResult,
                    file_path=ckpt,
                    asset_label=AssetLabel.emodel_optimisation_checkpoint,
                    file_content_type=ContentType.application_x_hdf5,
                )
                break

        # Upload final.json
        final_path = coord_root / "final.json"
        if final_path.exists():
            db_client.upload_file(
                entity_id=task_result.id,  # ty:ignore[invalid-argument-type]
                entity_type=TaskResult,
                file_path=final_path,
                asset_label=AssetLabel.emodel_analysis_summary,
                file_content_type=ContentType.application_json,
            )

        # Upload figures directory
        figures_dir = coord_root / "figures"
        if figures_dir.exists() and any(figures_dir.rglob("*")):
            paths = {}
            for fp in sorted(figures_dir.rglob("*")):
                if fp.is_file():
                    rel = str(fp.relative_to(figures_dir))
                    paths[rel] = str(fp)
            if paths:
                db_client.upload_directory(
                    entity_id=task_result.id,  # ty:ignore[invalid-argument-type]
                    entity_type=TaskResult,
                    name="figures",
                    paths={Path(k): Path(v) for k, v in paths.items()},
                    label=AssetLabel.emodel_analysis_figures,
                )

        # Upload recipe
        recipes_path = coord_root / "config" / "recipes.json"
        if recipes_path.exists():
            db_client.upload_file(
                entity_id=task_result.id,  # ty:ignore[invalid-argument-type]
                entity_type=TaskResult,
                file_path=recipes_path,
                asset_label=AssetLabel.task_result,
                file_content_type=ContentType.application_json,
            )

        # Upload params
        params_path = coord_root / "config" / "params"
        if params_path.exists():
            for pf in params_path.glob("*.json"):
                db_client.upload_file(
                    entity_id=task_result.id,  # ty:ignore[invalid-argument-type]
                    entity_type=TaskResult,
                    file_path=pf,
                    asset_label=AssetLabel.neuron_mechanisms,
                    file_content_type=ContentType.application_json,
                )
                break

        # Upload hoc export
        hoc_dir = coord_root / "export_emodels_hoc"
        if hoc_dir.exists():
            for hoc_file in hoc_dir.rglob("*.hoc"):
                db_client.upload_file(
                    entity_id=task_result.id,  # ty:ignore[invalid-argument-type]
                    entity_type=TaskResult,
                    file_path=hoc_file,
                    asset_label=AssetLabel.neuron_hoc,
                    file_content_type=ContentType.application_hoc,
                )
                break

        # Upload sonata export
        sonata_dir = coord_root / "export_emodels_sonata"
        if sonata_dir.exists() and any(sonata_dir.rglob("*")):
            paths = {}
            for fp in sorted(sonata_dir.rglob("*")):
                if fp.is_file():
                    rel = str(fp.relative_to(sonata_dir))
                    paths[rel] = str(fp)
            if paths:
                db_client.upload_directory(
                    entity_id=task_result.id,  # ty:ignore[invalid-argument-type]
                    entity_type=TaskResult,
                    name="sonata",
                    paths={Path(k): Path(v) for k, v in paths.items()},
                    label=AssetLabel.emodel_optimization_output,
                )

        # --- Derivation links from inputs ---
        extraction_tr_entity = init.extraction_task_result.entity(db_client=db_client)
        db_client.register_entity(
            Derivation(
                used=extraction_tr_entity,
                generated=task_result,
                derivation_type=DerivationType.unspecified,
            )
        )
        morph_entity = self.config.morphology_selection.morphology.entity(db_client=db_client)
        db_client.register_entity(
            Derivation(
                used=morph_entity,
                generated=task_result,
                derivation_type=DerivationType.unspecified,
            )
        )
        for icm in self.config.parameters_selection.ion_channel_models:
            icm_entity = icm.entity(db_client=db_client)
            db_client.register_entity(
                Derivation(
                    used=icm_entity,
                    generated=task_result,
                    derivation_type=DerivationType.unspecified,
                )
            )

        # --- Register draft EModel ---
        # Read score and seed from final.json (written by store_best_model)
        score = 0.0
        first_seed = int(self.config.optimization_settings.seed)
        final_path = coord_root / "final.json"
        if final_path.exists():
            with final_path.open(encoding="utf-8") as f:
                final_data = json.load(f)
            # final.json is a dict of emodel_name -> list of model dicts
            models = final_data.get(emodel_name, []) if isinstance(final_data, dict) else []
            if models:
                best = models[0]
                score = float(best.get("fitness", best.get("score", 0.0)))

        # Get species and brain region entities
        species_entity = morph_entity.species if hasattr(morph_entity, "species") else None
        brain_region_entity = (
            morph_entity.brain_region if hasattr(morph_entity, "brain_region") else None
        )

        emodel_entity = db_client.register_entity(
            EModel(
                species=species_entity,  # ty:ignore[invalid-argument-type]
                brain_region=brain_region_entity,  # ty:ignore[invalid-argument-type]
                iteration="0",
                score=score,
                seed=first_seed,
                exemplar_morphology=morph_entity,  # ty:ignore[invalid-argument-type]
                name=f"{emodel_name} (draft)",
                description=f"Draft emodel from optimisation (emodel={emodel_name}).",
            )
        )
        L.info("Draft EModel registered: %s", emodel_entity.id)

        # Upload hoc to EModel
        if hoc_dir.exists():
            for hoc_file in hoc_dir.rglob("*.hoc"):
                db_client.upload_file(
                    entity_id=emodel_entity.id,  # ty:ignore[invalid-argument-type]
                    entity_type=EModel,
                    file_path=hoc_file,
                    asset_label=AssetLabel.neuron_hoc,
                    file_content_type=ContentType.application_hoc,
                )
                break

        # Upload sonata to EModel
        if sonata_dir.exists() and any(sonata_dir.rglob("*")):
            paths = {}
            for fp in sorted(sonata_dir.rglob("*")):
                if fp.is_file():
                    rel = str(fp.relative_to(sonata_dir))
                    paths[rel] = str(fp)
            if paths:
                db_client.upload_directory(
                    entity_id=emodel_entity.id,  # ty:ignore[invalid-argument-type]
                    entity_type=EModel,
                    name="sonata",
                    paths={Path(k): Path(v) for k, v in paths.items()},
                    label=AssetLabel.emodel_optimization_output,
                )

        # Derivation: TaskResult → EModel
        db_client.register_entity(
            Derivation(
                used=task_result,
                generated=emodel_entity,
                derivation_type=DerivationType.unspecified,
            )
        )

        # --- Register draft MEModel ---
        memodel_entity = db_client.register_entity(
            MEModel(
                name=f"{emodel_name} MEModel (draft)",
                description=f"Draft MEModel from optimisation (emodel={emodel_name}).",
                species=species_entity,  # ty:ignore[invalid-argument-type]
                brain_region=brain_region_entity,  # ty:ignore[invalid-argument-type]
                morphology=morph_entity,  # ty:ignore[invalid-argument-type]
                emodel=emodel_entity,
                validation_status=ValidationStatus.created,
                holding_current=None,  # Set after validation in Workflow B
                threshold_current=None,  # Set after validation in Workflow B
            )
        )
        L.info("Draft MEModel registered: %s", memodel_entity.id)

        # Derivation: EModel → MEModel
        db_client.register_entity(
            Derivation(
                used=emodel_entity,
                generated=memodel_entity,
                derivation_type=DerivationType.unspecified,
            )
        )
