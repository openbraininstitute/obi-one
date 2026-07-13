"""Task wrapper for the BluePyEModel export + validation step (Workflow B).

Downloads optimisation TaskResult assets, runs validation + plotting,
re-exports validated models to HOC/SONATA, registers validation TaskResult,
updates MEModel with calibration results and validation status, and updates
EModel with final export assets.
"""

import contextlib
import json
import logging
from pathlib import Path
from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID
from obi_one.scientific.tasks.emodel_optimization import _shared
from obi_one.scientific.tasks.emodel_optimization.task3_export_and_validation.config import (
    EModelExportAndValidationSingleConfig,
)

L = logging.getLogger(__name__)


class EModelExportAndValidationTask(Task):
    """Run validation, plotting, and final export; update MEModel and EModel."""

    name: ClassVar[str] = "EModel Export and Validation"
    description: ClassVar[str] = (
        "Run BluePyEModel validation, plotting, and final export of validated"
        " models to HOC/SONATA. Updates MEModel with calibration results."
    )

    config: EModelExportAndValidationSingleConfig

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
        from bluepyemodel.optimisation import store_best_model  # noqa: PLC0415
        from bluepyemodel.tools.multiprocessing import get_mapper  # noqa: PLC0415
        from bluepyemodel.validation.validation import validate  # noqa: PLC0415

        init = self.config.initialize
        settings = self.config.settings
        coord_root = Path(self.config.coordinate_output_root).resolve()
        emodel = init.emodel
        mtype = self._derive_mtype_from_memodel(db_client)

        # --- 1. Download optimisation TaskResult assets ---
        opt_tr = init.optimization_task_result
        self._download_opt_assets(opt_tr, coord_root, db_client)

        # --- 2. Compile mechanisms if needed ---
        if (
            not (coord_root / "x86_64" / "special").exists()
            and not (coord_root / "arm64" / "special").exists()
        ):
            _shared.compile_mechanisms(coord_root / "mechanisms")

        # --- 3. Merge validation + export settings into recipe ---
        recipes_path = coord_root / "config" / "recipes.json"
        recipes = _shared.load_recipes(recipes_path)
        recipes = _shared.update_pipeline_settings(
            recipes,
            emodel=emodel,
            overrides=settings.to_dict(self.config.currentscape_config),
        )
        _shared.write_recipes(recipes, recipes_path)

        # --- 4. Run validation + plot + export ---
        with _shared.chdir(coord_root):
            access_point = LocalAccessPoint(
                emodel=emodel,
                etype=init.etype,
                mtype=mtype,
                ttype=None,
                species=init.species,
                brain_region=init.brain_region,
                iteration_tag=init.iteration_tag,
                recipes_path="./config/recipes.json",
            )

            # Determine mapper backend
            if init.use_ipyparallel:
                mapper = get_mapper(backend="ipyparallel")
            elif init.use_multiprocessing:
                mapper = get_mapper(backend="multiprocessing")
            else:
                mapper = map

            # Store optimisation results (reads checkpoints → final.json)
            seeds = list(settings.seeds)
            for seed in seeds:
                store_best_model(access_point=access_point, seed=seed)

            # Validation
            validate(access_point=access_point, mapper=mapper)

            # Plot (only validated)
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
                only_validated=settings.only_validated_plots,
                save_recordings=pp_settings.save_recordings,
            )

            # Final export (only validated)
            if settings.export_hoc:
                export_emodels_hoc(
                    access_point=access_point,
                    only_validated=settings.only_validated,
                    only_best=settings.only_best,
                    seeds=seeds,
                )

            if settings.export_sonata:
                export_emodels_sonata(
                    access_point=access_point,
                    only_validated=settings.only_validated,
                    only_best=settings.only_best,
                    seeds=seeds,
                    map_function=mapper,
                )

        # --- 5. Register output entities and update MEModel/EModel ---
        if db_client is not None:
            self._register_and_update(coord_root, db_client)

        return coord_root

    def _download_opt_assets(  # noqa: PLR6301
        self,
        opt_tr: TaskResultFromID,
        coord_root: Path,
        db_client: entitysdk.client.Client,
    ) -> None:
        """Download all assets from optimisation TaskResult."""
        from entitysdk.types import AssetLabel  # noqa: PLC0415

        # Checkpoint
        ckpt_dir = coord_root / "checkpoints"
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        try:
            opt_tr.download_asset_by_label(
                AssetLabel.emodel_optimisation_checkpoint,
                dest_dir=ckpt_dir,
                db_client=db_client,
            )
        except Exception:  # noqa: BLE001
            L.warning("Could not download optimisation checkpoint.")

        # Recipes
        try:
            recipes_dict = opt_tr.download_json_asset_by_label(
                AssetLabel.task_result,
                db_client=db_client,
            )
            recipes_dir = coord_root / "config"
            recipes_dir.mkdir(parents=True, exist_ok=True)
            (recipes_dir / "recipes.json").write_text(
                json.dumps(recipes_dict, indent=4), encoding="utf-8"
            )
        except Exception:  # noqa: BLE001
            L.warning("Could not download optimisation recipe.")

        # Params
        params_dir = coord_root / "config" / "params"
        params_dir.mkdir(parents=True, exist_ok=True)
        try:
            opt_tr.download_asset_by_label(
                AssetLabel.neuron_mechanisms,
                dest_dir=params_dir,
                db_client=db_client,
            )
        except Exception:  # noqa: BLE001
            L.warning("Could not download optimisation params.")

        # Figures
        figures_dir = coord_root / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        try:
            opt_tr.download_directory_asset_by_label(
                AssetLabel.emodel_analysis_figures,
                dest_dir=figures_dir,
                db_client=db_client,
            )
        except Exception:  # noqa: BLE001
            L.warning("Could not download optimisation figures.")

        # Final.json
        try:
            final_dict = opt_tr.download_json_asset_by_label(
                AssetLabel.emodel_analysis_summary,
                db_client=db_client,
            )
            (coord_root / "final.json").write_text(
                json.dumps(final_dict, indent=4), encoding="utf-8"
            )
        except Exception:  # noqa: BLE001
            L.warning("Could not download final.json.")

        # HOC
        hoc_dir = coord_root / "export_emodels_hoc"
        hoc_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(Exception):
            opt_tr.download_asset_by_label(
                AssetLabel.neuron_hoc,
                dest_dir=hoc_dir,
                db_client=db_client,
            )

        # SONATA
        sonata_dir = coord_root / "export_emodels_sonata"
        sonata_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(Exception):
            opt_tr.download_directory_asset_by_label(
                AssetLabel.emodel_optimization_output,
                dest_dir=sonata_dir,
                db_client=db_client,
            )

        L.info("Downloaded optimisation assets for export + validation.")

    def _derive_mtype_from_memodel(self, db_client: entitysdk.client.Client) -> str:
        """Derive mtype from the MEModel entity."""
        memodel_entity = self.config.initialize.memodel.entity(db_client=db_client)
        if hasattr(memodel_entity, "mtypes") and memodel_entity.mtypes:
            return str(memodel_entity.mtypes[0])  # ty:ignore[not-subscriptable]
        return "unknown"

    def _register_and_update(  # noqa: C901, PLR0912, PLR0914, PLR0915
        self,
        coord_root: Path,
        db_client: entitysdk.client.Client,
    ) -> None:
        """Register validation TaskResult, upload assets, update MEModel and EModel."""
        from entitysdk.models import (  # noqa: PLC0415
            Derivation,
            EModel,
            MEModel,
            MEModelCalibrationResult,
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
        settings = self.config.settings
        emodel_name = init.emodel

        # --- Register validation TaskResult ---
        task_result = db_client.register_entity(
            TaskResult(
                name=f"EModel Export+Validation Result — {emodel_name}",
                description=(f"Validation and final export results for emodel '{emodel_name}'."),
                task_result_type=TaskResultType.optimized_emodel_analysis_validation__result,
            )
        )
        L.info("Validation TaskResult registered: %s", task_result.id)

        # Upload validation figures
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

        # Upload validation recipe
        recipes_path = coord_root / "config" / "recipes.json"
        if recipes_path.exists():
            db_client.upload_file(
                entity_id=task_result.id,  # ty:ignore[invalid-argument-type]
                entity_type=TaskResult,
                file_path=recipes_path,
                asset_label=AssetLabel.task_result,
                file_content_type=ContentType.application_json,
            )

        # Upload validation details
        details = {
            "validation_threshold": settings.validation_threshold,
            "validation_protocols": list(settings.validation_protocols),
        }
        db_client.upload_content(
            entity_id=task_result.id,  # ty:ignore[invalid-argument-type]
            entity_type=TaskResult,
            file_content=json.dumps(details, indent=2).encode("utf-8"),
            file_name="validation_details.json",
            file_content_type=ContentType.application_json,
            asset_label=AssetLabel.validation_result_details,
        )

        # Upload final HOC
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

        # Upload final SONATA
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

        # Derivation: optimisation TaskResult → validation TaskResult
        opt_tr_entity = init.optimization_task_result.entity(db_client=db_client)
        db_client.register_entity(
            Derivation(
                used=opt_tr_entity,
                generated=task_result,
                derivation_type=DerivationType.unspecified,
            )
        )

        # --- Update MEModel with calibration results ---
        memodel_entity = init.memodel.entity(db_client=db_client)

        # Extract calibration values from final.json
        holding_current = None
        threshold_current = None
        rin = None
        score = 0.0

        final_path = coord_root / "final.json"
        if final_path.exists():
            with final_path.open(encoding="utf-8") as f:
                final_data = json.load(f)
            models = final_data.get(emodel_name, []) if isinstance(final_data, dict) else []
            if models:
                best = models[0]
                score = float(best.get("fitness", best.get("score", 0.0)))
                holding_current = best.get("holding_current")
                threshold_current = best.get("threshold_current")
                rin = best.get("rin")

        # Determine validation status
        validation_status = ValidationStatus.done
        if score > settings.validation_threshold:
            validation_status = ValidationStatus.error

        # Register calibration result
        if holding_current is not None and threshold_current is not None:
            calibration_result = db_client.register_entity(
                MEModelCalibrationResult(
                    holding_current=float(holding_current),
                    threshold_current=float(threshold_current),
                    rin=float(rin) if rin is not None else None,
                    calibrated_entity_id=memodel_entity.id,  # ty:ignore[invalid-argument-type]
                )
            )
            L.info("Calibration result registered: %s", calibration_result.id)

        # Update MEModel
        updated_memodel = db_client.update_entity(
            memodel_entity.id,  # ty:ignore[invalid-argument-type]
            MEModel,
            MEModel(
                name=memodel_entity.name,
                description=memodel_entity.description,
                species=memodel_entity.species,  # ty:ignore[unresolved-attribute]
                brain_region=memodel_entity.brain_region,  # ty:ignore[unresolved-attribute]
                morphology=memodel_entity.morphology,  # ty:ignore[unresolved-attribute]
                emodel=memodel_entity.emodel,  # ty:ignore[unresolved-attribute]
                validation_status=validation_status,
                holding_current=float(holding_current) if holding_current is not None else None,
                threshold_current=float(threshold_current)
                if threshold_current is not None
                else None,
                iteration=memodel_entity.iteration,  # ty:ignore[unresolved-attribute]
            ),
        )
        L.info("MEModel updated: %s (status=%s)", updated_memodel.id, validation_status)

        # --- Update EModel with final HOC/SONATA assets ---
        emodel_entity = memodel_entity.emodel  # ty:ignore[unresolved-attribute]

        if emodel_entity:
            if hoc_dir.exists():
                for hoc_file in hoc_dir.rglob("*.hoc"):
                    db_client.upload_file(
                        entity_id=emodel_entity.id,
                        entity_type=EModel,
                        file_path=hoc_file,
                        asset_label=AssetLabel.neuron_hoc,
                        file_content_type=ContentType.application_hoc,
                    )
                    break

            if sonata_dir.exists() and any(sonata_dir.rglob("*")):
                paths = {}
                for fp in sorted(sonata_dir.rglob("*")):
                    if fp.is_file():
                        rel = str(fp.relative_to(sonata_dir))
                        paths[rel] = str(fp)
                if paths:
                    db_client.upload_directory(
                        entity_id=emodel_entity.id,
                        entity_type=EModel,
                        name="sonata",
                        paths={Path(k): Path(v) for k, v in paths.items()},
                        label=AssetLabel.emodel_optimization_output,
                    )

            L.info("EModel %s updated with final export assets.", emodel_entity.id)

        # Derivation: validation TaskResult → EModel
        if emodel_entity:
            db_client.register_entity(
                Derivation(
                    used=task_result,
                    generated=emodel_entity,
                    derivation_type=DerivationType.unspecified,
                )
            )

        L.info("Export + validation complete.")
