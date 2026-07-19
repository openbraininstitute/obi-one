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
from typing import Any, ClassVar

import entitysdk
from pydantic import PrivateAttr

from obi_one.core.task import Task
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID
from obi_one.scientific.tasks.emodel_building import _shared
from obi_one.scientific.tasks.emodel_building.task3_export_and_validation.config import (
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
        from bluepyemodel.optimisation import store_best_model  # noqa: PLC0415
        from bluepyemodel.validation.validation import validate  # noqa: PLC0415

        init = self.config.initialize
        coord_root = Path(self.config.coordinate_output_root).resolve()

        # Fetch MEModel entity once — all helpers use this cached reference.
        memodel_entity = init.memodel.entity(db_client=db_client)

        metadata = self._derive_metadata(memodel_entity, db_client)
        emodel = metadata["emodel"]
        mtype = self._derive_mtype(memodel_entity, db_client)

        # --- 1. Download optimisation TaskResult assets ---
        opt_tr = init.optimization_task_result
        self._download_opt_assets(opt_tr, coord_root, db_client)

        # --- 1b. Stage morphology + mechanisms from MEModel ---
        self._stage_morphology(memodel_entity, coord_root, db_client)
        self._stage_mechanisms(memodel_entity, coord_root, db_client)

        # --- 2. Compile mechanisms if needed ---
        _shared.compile_mechanisms(coord_root / "mechanisms")

        # --- 3. Recipe is already on disk from step 1 (downloaded from TaskResult) ---
        # All validation/plotting settings are in the recipe's pipeline_settings.

        # --- 4. Run validation + plot + export ---
        with _shared.chdir(coord_root):
            access_point = LocalAccessPoint(
                emodel=emodel,
                etype=metadata["etype"],
                mtype=mtype,
                ttype=None,
                species=metadata["species"],
                brain_region=metadata["brain_region"],
                iteration_tag=None,
                recipes_path="./config/recipes.json",
            )

            mapper = map
            pp = access_point.pipeline_settings

            # Seed comes from the recipe's optimisation_params or default to [1]
            seeds = [pp.seed] if hasattr(pp, "seed") else [1]

            # Store optimisation results (reads checkpoints -> final.json)
            for seed in seeds:
                store_best_model(access_point=access_point, seed=seed)

            # Validation
            validate(access_point=access_point, mapper=mapper)

            # Plot (only validated models)
            _shared.run_plot_models(
                access_point=access_point,
                mapper=mapper,
                seeds=seeds,
                figures_dir=Path("./figures") / emodel,
                only_validated=True,
            )

            # Export (only validated, only best)
            export_emodels_hoc(
                access_point=access_point,
                only_validated=True,
                only_best=True,
                seeds=seeds,
            )
            export_emodels_sonata(
                access_point=access_point,
                only_validated=True,
                only_best=True,
                seeds=seeds,
                map_function=mapper,
            )

        # --- 5. Register output entities and update MEModel/EModel ---
        if db_client is not None:
            self._register_and_update(
                coord_root,
                db_client,
                memodel_entity=memodel_entity,
                execution_activity_id=execution_activity_id,
            )

        return coord_root

    def _download_opt_assets(  # noqa: PLR6301
        self,
        opt_tr: TaskResultFromID,
        coord_root: Path,
        db_client: entitysdk.client.Client,
    ) -> None:
        """Download all assets from the optimisation TaskResult.

        Assets are split into *required* (checkpoint, recipes) and *optional*
        (figures, HOC, SONATA). Required assets raise on failure; optional
        assets log a warning and continue.
        """
        from entitysdk.types import AssetLabel  # noqa: PLC0415

        from obi_one.utils.db_sdk import select_json_asset_content  # noqa: PLC0415

        # --- Required assets (task cannot proceed without these) ---

        # Checkpoint — needed by store_best_model
        ckpt_dir = coord_root / "checkpoints"
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        opt_tr.download_asset_by_label(
            AssetLabel.emodel_optimisation_checkpoint,
            dest_dir=ckpt_dir,
            db_client=db_client,
        )

        # Recipes — needed to reconstruct pipeline settings
        recipes_dict = select_json_asset_content(
            client=db_client,
            entity=opt_tr.entity(db_client=db_client),
            selection={"label": AssetLabel.task_result},
        )
        recipes_dir = coord_root / "config"
        recipes_dir.mkdir(parents=True, exist_ok=True)
        (recipes_dir / "recipes.json").write_text(
            json.dumps(recipes_dict, indent=4), encoding="utf-8"
        )

        # Params — needed for mechanism parameters
        params_dir = coord_root / "config" / "params"
        params_dir.mkdir(parents=True, exist_ok=True)
        opt_tr.download_asset_by_label(
            AssetLabel.neuron_mechanisms,
            dest_dir=params_dir,
            db_client=db_client,
        )

        # --- Optional assets (task can regenerate these) ---

        # Figures (previous analysis plots)
        figures_dir = coord_root / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(Exception):
            opt_tr.download_directory_asset_by_label(
                AssetLabel.emodel_analysis_figures,
                dest_dir=figures_dir,
                db_client=db_client,
            )

        # Final.json (summary from store_best_model — will be regenerated)
        try:
            final_dict = select_json_asset_content(
                client=db_client,
                entity=opt_tr.entity(db_client=db_client),
                selection={"label": AssetLabel.emodel_analysis_summary},
            )
            (coord_root / "final.json").write_text(
                json.dumps(final_dict, indent=4), encoding="utf-8"
            )
        except Exception:  # noqa: BLE001
            L.warning("Could not download final.json (will be regenerated by store_best_model).")

        # HOC (will be re-exported)
        hoc_dir = coord_root / "export_emodels_hoc"
        hoc_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(Exception):
            opt_tr.download_asset_by_label(
                AssetLabel.neuron_hoc,
                dest_dir=hoc_dir,
                db_client=db_client,
            )

        # SONATA (will be re-exported)
        sonata_dir = coord_root / "export_emodels_sonata"
        sonata_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(Exception):
            opt_tr.download_directory_asset_by_label(
                AssetLabel.emodel_optimization_output,
                dest_dir=sonata_dir,
                db_client=db_client,
            )

        L.info("Downloaded optimisation assets for export + validation.")

    @staticmethod
    def _derive_mtype(
        memodel_entity: Any,
        db_client: entitysdk.client.Client,
    ) -> str:
        """Derive mtype from the MEModel entity's morphology.

        Uses ``.pref_label`` (consistent with task2) for the canonical short label.
        """
        from entitysdk.models import CellMorphology  # noqa: PLC0415

        morph = db_client.get_entity(
            entity_id=memodel_entity.morphology.id,
            entity_type=CellMorphology,
        )
        if hasattr(morph, "mtypes") and morph.mtypes:
            return str(morph.mtypes[0].pref_label)
        return "unknown"

    @staticmethod
    def _derive_metadata(
        memodel_entity: Any,
        db_client: entitysdk.client.Client,  # noqa: ARG004
    ) -> dict[str, str]:
        """Derive emodel, etype, species, brain_region from the MEModel entity.

        Returns a dict with keys: emodel, etype, species, brain_region.
        """
        emodel_name = memodel_entity.emodel.name if memodel_entity.emodel else "unknown"

        etype = "unknown"
        if memodel_entity.etypes and len(memodel_entity.etypes) > 0:
            etype = str(memodel_entity.etypes[0].pref_label)

        species = memodel_entity.species.name if memodel_entity.species else "unknown"

        brain_region = (
            memodel_entity.brain_region.name if memodel_entity.brain_region else "unknown"
        )

        return {
            "emodel": emodel_name,
            "etype": etype,
            "species": species,
            "brain_region": brain_region,
        }

    @staticmethod
    def _stage_morphology(
        memodel_entity: Any,
        coord_root: Path,
        db_client: entitysdk.client.Client,
    ) -> None:
        """Download morphology SWC from MEModel -> morphology -> CellMorphology entity."""
        from obi_one.scientific.from_id.cell_morphology_from_id import (  # noqa: PLC0415
            CellMorphologyFromID,
        )

        morph_id = memodel_entity.morphology.id

        morph_dir = coord_root / "morphologies"
        morph_dir.mkdir(parents=True, exist_ok=True)
        morph_from_id = CellMorphologyFromID(id_str=str(morph_id))
        swc_content = morph_from_id.swc_file_content(db_client=db_client)
        morph_filename = f"{morph_id}.swc"
        (morph_dir / morph_filename).write_text(
            swc_content,
            encoding="utf-8",
        )
        L.info("Staged morphology from MEModel: %s", morph_filename)

    @staticmethod
    def _stage_mechanisms(
        memodel_entity: Any,
        coord_root: Path,
        db_client: entitysdk.client.Client,
    ) -> None:
        """Download .mod files from MEModel -> emodel -> EModel -> ion_channel_models."""
        from entitysdk.models import EModel  # noqa: PLC0415

        from obi_one.scientific.from_id.ion_channel_model_from_id import (  # noqa: PLC0415
            IonChannelModelFromID,
        )

        emodel_id = memodel_entity.emodel.id
        emodel_entity = db_client.get_entity(entity_id=emodel_id, entity_type=EModel)

        mech_dir = coord_root / "mechanisms"
        mech_dir.mkdir(parents=True, exist_ok=True)
        icms = getattr(emodel_entity, "ion_channel_models", []) or []
        for icm in icms:
            icm_from_id = IonChannelModelFromID(id_str=str(icm.id))
            icm_from_id.download_asset(dest_dir=mech_dir, db_client=db_client)
        L.info("Staged %d ion channel models from MEModel.", len(icms))

    def _register_and_update(  # noqa: C901, PLR0912, PLR0914, PLR0915
        self,
        coord_root: Path,
        db_client: entitysdk.client.Client,
        *,
        memodel_entity: Any,
        execution_activity_id: str | None = None,
    ) -> None:
        """Register validation TaskResult, upload assets, update MEModel and EModel.

        Converts draft EModel and MEModel to active lifecycle status after validation.
        """
        from entitysdk.models import (  # noqa: PLC0415
            EModel,
            MEModel,
            MEModelCalibrationResult,
            TaskActivity,
            TaskResult,
        )
        from entitysdk.types import (  # noqa: PLC0415
            AssetLabel,
            ContentType,
            EntityLifecycleStatus,
            TaskResultType,
            ValidationStatus,
        )

        metadata = self._derive_metadata(memodel_entity, db_client)
        emodel_name = metadata["emodel"]

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
                    entity_id=task_result.id,
                    entity_type=TaskResult,
                    name="figures",
                    paths={Path(k): Path(v) for k, v in paths.items()},
                    label=AssetLabel.emodel_analysis_figures,
                )

        # Upload validation recipe
        recipes_path = coord_root / "config" / "recipes.json"
        if recipes_path.exists():
            db_client.upload_file(
                entity_id=task_result.id,
                entity_type=TaskResult,
                file_path=recipes_path,
                asset_label=AssetLabel.task_result,
                file_content_type=ContentType.application_json,
            )

        # Upload validation details (read from recipe)
        recipes_path = coord_root / "config" / "recipes.json"
        validation_threshold = 5.0  # default
        validation_protocols: list[str] = []
        if recipes_path.exists():
            recipe_data = json.loads(recipes_path.read_text(encoding="utf-8"))
            if emodel_name in recipe_data:
                ps = recipe_data[emodel_name].get("pipeline_settings", {})
                validation_threshold = ps.get("validation_threshold", 5.0)
                validation_protocols = ps.get("validation_protocols", [])

        details = {
            "validation_threshold": validation_threshold,
            "validation_protocols": validation_protocols,
        }
        db_client.upload_content(
            entity_id=task_result.id,
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
                    entity_id=task_result.id,
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
                    entity_id=task_result.id,
                    entity_type=TaskResult,
                    name="sonata",
                    paths={Path(k): Path(v) for k, v in paths.items()},
                    label=AssetLabel.emodel_optimization_output,
                )

        # --- Update MEModel with calibration results ---

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

        # Determine validation status: score > threshold means FAILED (z-score: lower is better)
        validation_status = ValidationStatus.done
        if score > validation_threshold:
            validation_status = ValidationStatus.error

        # Register calibration result
        if holding_current is not None and threshold_current is not None:
            calibration_result = db_client.register_entity(
                MEModelCalibrationResult(
                    holding_current=float(holding_current),
                    threshold_current=float(threshold_current),
                    rin=float(rin) if rin is not None else None,
                    calibrated_entity_id=memodel_entity.id,
                )
            )
            L.info("Calibration result registered: %s", calibration_result.id)

        # Update MEModel — use partial update to avoid overwriting other fields
        # or breaking on schema changes (instead of reconstructing the full entity).
        memodel_updates: dict = {
            "validation_status": validation_status,
            "lifecycle_status": EntityLifecycleStatus.active,
        }
        if holding_current is not None:
            memodel_updates["holding_current"] = float(holding_current)
        if threshold_current is not None:
            memodel_updates["threshold_current"] = float(threshold_current)

        db_client.update_entity(
            entity_id=memodel_entity.id,
            entity_type=MEModel,
            attrs_or_entity=memodel_updates,
        )
        L.info(
            "MEModel %s updated (status=%s, lifecycle=active).",
            memodel_entity.id,
            validation_status,
        )

        # --- Update EModel with final HOC/SONATA assets ---
        emodel_entity = memodel_entity.emodel

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

            # Convert EModel from draft to active
            db_client.update_entity(
                entity_id=emodel_entity.id,
                entity_type=EModel,
                attrs_or_entity={"lifecycle_status": EntityLifecycleStatus.active},
            )
            L.info(
                "EModel %s updated with final export assets and set to active.",
                emodel_entity.id,
            )

        # Store registered entity IDs on the task instance for external access
        self._registered_task_result_id = str(task_result.id)
        if emodel_entity:
            self._registered_emodel_id = emodel_entity.id
        self._registered_memodel_id = memodel_entity.id

        # --- Update TaskActivity with generated_ids ---
        if execution_activity_id is not None:
            generated_ids = [task_result.id]
            if emodel_entity:
                generated_ids.append(emodel_entity.id)
            generated_ids.append(memodel_entity.id)
            db_client.update_entity(
                entity_id=execution_activity_id,  # ty:ignore[invalid-argument-type]
                entity_type=TaskActivity,
                attrs_or_entity={"generated_ids": generated_ids},
            )

        L.info("Export + validation complete.")
