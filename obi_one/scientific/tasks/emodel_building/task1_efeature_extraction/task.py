"""Task wrapper for the experimental e-feature extraction step."""

import logging
import operator
from pathlib import Path
from typing import Any, ClassVar

import entitysdk
import httpx
from pydantic import PrivateAttr

from obi_one.core.task import Task
from obi_one.scientific.from_id.electrical_cell_recording_from_id import (
    ElectricalCellRecordingFromID,
)
from obi_one.scientific.tasks.emodel_building import _shared
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.settings import (
    Settings,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.config import (
    EModelEFeatureExtractionSingleConfig,
)

L = logging.getLogger(__name__)

EXTRACTED_FEATURES_FILENAME = "extracted_features.json"

# BluePyEModel local access-point layout, relative to ``coordinate_output_root``.
EMODEL_NAME = "emodel"
RECIPES_RELPATH = "config/recipes.json"
TARGETS_CONFIG_RELPATH = "config/extract_config/targets.json"

# Fitness weight applied to every target. Amplitudes come from the recordings'
# discovered values (``AMPLITUDES_BY_PROTOCOL``), so each target matches a trace
# exactly and the tolerance only guards float-precision differences in the
# amplitude bluepyefe recomputes from the trace.
DEFAULT_TARGET_WEIGHT = 1.0
AMPLITUDE_TOLERANCE = 1e-3


def _build_files_metadata(
    *,
    nwb_paths_with_ljp: list[tuple[Path, float]],
    ecode_timing: dict[str, dict],
) -> list[dict]:
    """Build ``files_metadata`` rows for the NWB datasets (one file per cell).

    Each recording carries its own LJP (read from the ``ElectricalCellRecording``
    entity); the per-protocol stimulus timing in ``ecode_timing`` is shared across
    cells. Timing left unset is omitted so bluepyefe auto-detects it from the NWB.
    """
    return [
        {
            "cell_name": path.stem,
            "filepath": str(path),
            "ecodes": {ecode: {**timing, "ljp": ljp} for ecode, timing in ecode_timing.items()},
        }
        for path, ljp in sorted(nwb_paths_with_ljp, key=operator.itemgetter(0))
    ]


def _build_targets(
    protocols: tuple,
    global_efel_settings: dict,
) -> tuple[list[dict], list[str]]:
    """Flatten the per-protocol selection into ``bluepyefe.extract`` target rows.

    For every protocol, every ``(amplitude, is_validation)`` pair in
    ``extraction_amplitudes`` and every feature in ``features`` yields one target.
    Each target's ``efel_settings`` apply the cascade feature > protocol > global.
    Amplitudes flagged ``is_validation`` are returned as ``{protocol}_{amplitude}``
    validation-protocol names for the recipe.
    """
    rows: list[dict] = []
    validation_names: list[str] = []
    for protocol in protocols:
        protocol_overrides = protocol.efel_settings_overrides()
        for amplitude, is_validation in protocol.extraction_amplitudes:
            if is_validation:
                validation_names.append(f"{protocol.protocol_name}_{amplitude}")
            rows.extend(
                {
                    "efeature": feature.efel_name,
                    "protocol": protocol.protocol_name,
                    "amplitude": amplitude,
                    "tolerance": AMPLITUDE_TOLERANCE,
                    "weight": DEFAULT_TARGET_WEIGHT,
                    "efel_settings": {
                        **global_efel_settings,
                        **protocol_overrides,
                        **feature.efel_settings_overrides(),
                    },
                }
                for feature in protocol.features
            )
    return rows, validation_names


def _build_extraction_recipes(
    settings: Settings,
    *,
    validation_protocol_names: list[str],
) -> dict:
    """Build a minimal BluePyEModel ``recipes.json`` for the extraction step.

    Only the ``pipeline_settings`` consumed by ``extract_save_features_protocols``
    are populated — no morphology, mechanisms or model parameters are needed.
    Amplitudes are absolute (nA), so ``extract_absolute_amplitudes`` is always True.
    ``efel_settings`` is the global base of the cascade; the per-target overrides in
    the targets configuration refine it (feature > protocol > global).
    """
    pipeline_settings: dict = {
        "path_extract_config": TARGETS_CONFIG_RELPATH,
        "extract_absolute_amplitudes": True,
        "plot_extraction": True,
        "default_std_value": settings.default_std_value,
        "efel_settings": settings.global_efel_settings(),
        "extraction_threshold_value_save": settings.threshold_nvalue_save,
        "bound_max_std": settings.bound_max_std,
        "interpolate_RMP_extraction": settings.interpolate_rmp,
        "threshold_efeature_std": settings.threshold_efeature_std or None,
        "minimum_protocol_delay": settings.minimum_protocol_delay,
        "validation_protocols": sorted(set(validation_protocol_names)),
    }
    return {
        EMODEL_NAME: {
            "features": EXTRACTED_FEATURES_FILENAME,
            "pipeline_settings": pipeline_settings,
        },
    }


class EModelEFeatureExtractionTask(Task):
    """Extract experimental e-features from raw ephys traces via BluePyEModel.

    Extraction is routed through BluePyEModel's
    :func:`bluepyemodel.efeatures_extraction.efeatures_extraction.extract_save_features_protocols`
    rather than calling ``bluepyefe.extract.extract_efeatures`` directly, so the
    targets, pipeline settings and fitness-calculator output all flow through the
    BluePyEModel local access point.

    Steps performed in ``coordinate_output_root``:

    1. Download the NWB asset of every ``ElectricalCellRecording`` listed in
       ``initialize.electrical_cell_recording`` into ``./ephys_data/<id>/``.
    2. Build ``files_metadata`` + ``targets`` rows from the per-protocol blocks
       (amplitudes, stimulus timing and the eFEL settings cascade) into a
       :class:`bluepyemodel.efeatures_extraction.targets_configuration.TargetsConfiguration`.
    3. Write a minimal ``./config/recipes.json`` (extraction ``pipeline_settings``
       only) and store the targets configuration through the local access point.
    4. Run ``extract_save_features_protocols`` on that access point, writing the
       fitness-calculator configuration to ``./extracted_features.json`` for the
       optimisation stage.
    """

    name: ClassVar[str] = "EModel EFeature Extraction"
    description: ClassVar[str] = (
        "Extract experimental e-features from ephys traces via BluePyEModel."
    )

    config: EModelEFeatureExtractionSingleConfig

    _registered_task_result_id: str | None = PrivateAttr(default=None)

    def _download_recordings(
        self,
        ephys_data_root: Path,
        db_client: entitysdk.client.Client,
    ) -> list[tuple[Path, float]]:
        """Download each recording's NWB asset and return ``(path, ljp)`` pairs."""
        downloaded: list[tuple[Path, float]] = []
        for recording in self.config.initialize.electrical_cell_recording:
            if not isinstance(recording, ElectricalCellRecordingFromID):
                msg = f"Expected ElectricalCellRecordingFromID, got {type(recording).__name__}."
                raise TypeError(msg)
            target_dir = ephys_data_root / recording.id_str
            path = recording.download_asset(dest_dir=target_dir, db_client=db_client)
            ljp = recording.entity(db_client=db_client).ljp  # ty:ignore[unresolved-attribute]
            downloaded.append((path, ljp))
        return downloaded

    def _build_targets_configuration(
        self, downloaded: list[tuple[Path, float]]
    ) -> tuple[Any, list[str]]:
        """Assemble the BluePyEModel ``TargetsConfiguration`` from the recordings.

        Stimulus timing and amplitudes come from the per-protocol config (the
        amplitudes were discovered up front via the mapped-properties endpoint), so
        the NWBs only need downloading — no timing or amplitude discovery happens
        here. Returns the configuration and the validation-protocol names.
        """
        from bluepyemodel.efeatures_extraction.targets_configuration import (  # noqa: PLC0415
            TargetsConfiguration,
        )

        protocols = self.config.efeatures_by_protocol.selection.protocols
        ecode_timing = {p.protocol_name: p.stim_timing() for p in protocols}

        files = _build_files_metadata(nwb_paths_with_ljp=downloaded, ecode_timing=ecode_timing)
        if not files:
            msg = "No NWB ephys files were downloaded for extraction."
            raise FileNotFoundError(msg)

        targets, validation_names = _build_targets(
            protocols, self.config.settings.global_efel_settings()
        )
        configuration = TargetsConfiguration(files=files, targets=targets, protocols_rheobase=[])
        return configuration, validation_names

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> Path:
        from bluepyemodel.access_point import get_access_point  # noqa: PLC0415
        from bluepyemodel.efeatures_extraction.efeatures_extraction import (  # noqa: PLC0415
            extract_save_features_protocols,
        )

        coord_root = Path(self.config.coordinate_output_root).resolve()

        # 1. Download the NWB ephys assets from entitycore (with per-recording LJP).
        downloaded = self._download_recordings(coord_root / "ephys_data", db_client)

        # 2. Build the targets configuration + collect validation-protocol names.
        targets_configuration, validation_names = self._build_targets_configuration(downloaded)

        # 3. Write a minimal BluePyEModel recipe so extraction runs through the
        #    local access point rather than calling bluepyefe directly.
        _shared.write_recipes(
            _build_extraction_recipes(
                self.config.settings,
                validation_protocol_names=validation_names,
            ),
            coord_root / RECIPES_RELPATH,
        )

        # 4. Run BluePyEModel's extraction. chdir so the local access point anchors
        #    its relative paths (recipes, targets config, figures, extracted
        #    features) to the coordinate working directory.
        with _shared.chdir(coord_root):
            access_point = get_access_point(
                access_point="local",
                emodel=EMODEL_NAME,
                recipes_path=f"./{RECIPES_RELPATH}",
                final_path="final.json",
            )
            access_point.store_targets_configuration(targets_configuration)
            extract_save_features_protocols(access_point=access_point, mapper=map)

        # 5. Register TaskResult entity and upload assets to entitycore.
        if db_client is not None:
            try:
                self._register_task_result(coord_root, db_client)
            except httpx.HTTPError as e:
                L.warning(
                    "TaskResult registration failed (extraction output is still"
                    " available locally at %s): %s",
                    coord_root,
                    e,
                )

        return coord_root

    def _build_figures_manifest(self, figures_dir: Path) -> dict:  # noqa: PLR6301
        """Build a manifest.json describing all PDF figure files in the directory."""
        import re  # noqa: PLC0415

        files_list = []
        for pdf_path in sorted(figures_dir.rglob("*.pdf")):
            rel_path = pdf_path.relative_to(figures_dir)
            entry: dict[str, str] = {"path": str(rel_path)}

            # Try to parse: <cell>_<protocol>_<feature>_amp.pdf or <cell>_<protocol>_recordings.pdf
            name = pdf_path.stem
            if name == "legend":
                entry["type"] = "legend"
            elif name.endswith("_recordings"):
                parts = name.rsplit("_recordings", 1)
                # parts[0] = <cell>_<protocol>
                last_underscore = parts[0].rfind("_")
                if last_underscore > 0:
                    entry["protocol"] = parts[0][last_underscore + 1 :]
                    entry["cell"] = parts[0][:last_underscore]
                entry["type"] = "recordings_plot"
            elif "_amp" in name:
                # <cell>_<protocol>_<feature>_amp
                match = re.match(r"^(.+?)_([^_]+)_(.+?)_amp$", name)
                if match:
                    entry["cell"] = match.group(1)
                    entry["protocol"] = match.group(2)
                    entry["feature"] = match.group(3)
                entry["type"] = "feature_plot"
            else:
                entry["type"] = "other"

            files_list.append(entry)

        # Collect unique cells
        cells = sorted({e.get("cell", "") for e in files_list if e.get("cell")})

        return {"cells": cells, "files": files_list}

    def _register_task_result(
        self,
        coord_root: Path,
        db_client: entitysdk.client.Client,
    ) -> None:
        """Register a TaskResult entity and upload extraction output assets."""
        import json  # noqa: PLC0415

        from entitysdk.models import TaskResult  # noqa: PLC0415
        from entitysdk.types import (  # noqa: PLC0415
            AssetLabel,
            ContentType,
            TaskResultType,
        )

        campaign_name = getattr(self.config, "campaign_name", "EFeature Extraction")

        # Register the TaskResult entity.
        task_result = db_client.register_entity(
            TaskResult(
                name=f"EFeature Extraction Result — {campaign_name}",
                description="Extracted e-features from ephys recordings.",
                task_result_type=TaskResultType.efeature_extraction__result,
            )
        )
        L.info("TaskResult entity registered: %s", task_result.id)

        # Store registered entity ID on the task instance for external access
        self._registered_task_result_id = str(task_result.id)

        # Upload extracted features JSON.
        features_path = coord_root / EXTRACTED_FEATURES_FILENAME
        if features_path.exists():
            db_client.upload_file(
                entity_id=task_result.id,  # ty:ignore[invalid-argument-type]
                entity_type=TaskResult,
                file_path=features_path,
                asset_label=AssetLabel.efeature_extraction_features,
                file_content_type=ContentType.application_json,
            )
            L.info("Uploaded extracted features JSON.")

        # Keep recipes JSON local for the extraction workflow.
        recipes_path = coord_root / RECIPES_RELPATH
        if recipes_path.exists():
            L.info("Recipes JSON remains local: %s", recipes_path)

        # Upload figures directory with manifest.
        figures_dir = coord_root / "figures"
        if figures_dir.exists() and any(figures_dir.rglob("*.pdf")):
            # Generate manifest
            manifest = self._build_figures_manifest(figures_dir)
            manifest_path = figures_dir / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2))

            # Build paths dict for directory upload: {relative_path: absolute_path}
            paths = {}
            for file_path in sorted(figures_dir.rglob("*")):
                if file_path.is_file():
                    rel = str(file_path.relative_to(figures_dir))
                    paths[rel] = str(file_path)

            db_client.upload_directory(
                entity_id=task_result.id,  # ty:ignore[invalid-argument-type]
                entity_type=TaskResult,
                name="figures",
                paths={Path(k): Path(v) for k, v in paths.items()},
                label=AssetLabel.efeature_extraction_figures,
            )
            L.info("Uploaded figures directory (%d files).", len(paths))

        # Keep targets JSON local because extraction consumes it directly.
        targets_path = coord_root / TARGETS_CONFIG_RELPATH
        if targets_path.exists():
            L.info("Targets JSON remains local: %s", targets_path)

        # Note: bluepyefe cells pickle (.pkl) is not uploaded because
        # entitycore expects HDF5 for efeature_extraction_cells. The pickle
        # format is not compatible with the allowed content type.

        # Link input ElectricalCellRecording entities to the TaskResult via Derivation.
        from entitysdk.models import Derivation  # noqa: PLC0415
        from entitysdk.types import DerivationType  # noqa: PLC0415

        for recording in self.config.initialize.electrical_cell_recording:
            recording_entity = recording.entity(db_client=db_client)
            db_client.register_entity(
                Derivation(
                    used=recording_entity,
                    generated=task_result,
                    derivation_type=DerivationType.unspecified,
                )
            )
        L.info(
            "Linked %d input recordings to TaskResult.",
            len(self.config.initialize.electrical_cell_recording),
        )
