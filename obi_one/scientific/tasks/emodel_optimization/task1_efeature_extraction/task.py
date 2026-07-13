"""Task wrapper for the experimental e-feature extraction step."""

import logging
import operator
from pathlib import Path
from statistics import median
from typing import Any, ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.from_id.electrical_cell_recording_from_id import (
    ElectricalCellRecordingFromID,
)
from obi_one.scientific.library.electrical_cell_recording_properties import (
    _read_amplitudes_from_nwb,
    _read_timing_from_nwb,
)
from obi_one.scientific.tasks.emodel_optimization import _shared
from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.blocks import (
    Settings,
)
from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.config import (
    EModelEFeatureExtractionSingleConfig,
)

L = logging.getLogger(__name__)

EXTRACTED_FEATURES_FILENAME = "extracted_features.json"

# BluePyEModel local access-point layout, relative to ``coordinate_output_root``.
EMODEL_NAME = "emodel"
RECIPES_RELPATH = "config/recipes.json"
TARGETS_CONFIG_RELPATH = "config/extract_config/targets.json"

# Global eFEL defaults passed as the recipe's ``efel_settings`` dict. In manual
# mode, per-feature overrides (threshold/strict_stiminterval/interp_step/stim_start
# /stim_end + custom_efel_settings) take priority via the cascade. In autoselect
# mode these are the only eFEL settings applied.
DEFAULT_EFEL_SETTINGS: dict[str, float | bool] = {
    "Threshold": -20.0,
    "strict_stiminterval": True,
    "interp_step": 0.025,
}

# bluepyefe eCodes that don't auto-detect their stimulus timing. ``Ramp`` needs
# only ``ton``, which this stage reads from the NWB current (``_read_timing_from_nwb``)
# and supplies. ``DeHyperPol`` also needs mid-transition points we can't recover
# from the current alone, so protocols routing to it are skipped at extraction
# (with a warning) rather than crashing the whole run.
_TON_ONLY_ECODES = frozenset({"Ramp"})
_TIMING_UNSUPPORTED_ECODES = frozenset({"DeHyperPol"})


def _ecode_class_name(protocol_name: str, ecodes: dict) -> str | None:
    """Return the bluepyefe eCode class name matching ``protocol_name`` (or None).

    Mirrors bluepyefe's own lookup (``cell.Cell.read_recordings``): the first
    registry key that is a case-insensitive substring of the protocol name wins.
    """
    for key, ecode_cls in ecodes.items():
        if key.lower() in protocol_name.lower():
            return ecode_cls.__name__
    return None


def _discover_timing(
    nwb_paths: list[Path],
    protocol_names: list[str],
) -> dict[str, float]:
    """Median stimulus onset (``ton``, ms) per protocol across the NWBs.

    Protocols with no detectable onset in any NWB are omitted.
    """
    collected: dict[str, list[float]] = {p: [] for p in protocol_names}
    for path in nwb_paths:
        for protocol_name, ton in _read_timing_from_nwb(path, protocol_names).items():
            collected[protocol_name].append(ton)
    return {p: median(v) for p, v in collected.items() if v}


def _partition_protocols(
    protocols: tuple,
    ecodes: dict,
    ton_by_protocol: dict[str, float],
) -> tuple[list, dict[str, dict], list[str]]:
    """Split protocols into ``(extractable, ecode_metadata, skipped)``.

    ``ecode_metadata`` maps each extractable protocol to the per-protocol config
    passed to bluepyefe. User-provided timing (``protocol.timing_override()``)
    takes priority; for ``Ramp`` protocols that don't auto-detect, the
    auto-detected ``ton_by_protocol`` is used as a fallback. Protocols whose
    eCode needs timing we can't supply are returned in ``skipped``.
    """
    extractable: list = []
    ecode_metadata: dict[str, dict] = {}
    skipped: list[str] = []
    for protocol in protocols:
        ecode = _ecode_class_name(protocol.name, ecodes)
        user_timing = protocol.timing_override()
        if ecode in _TON_ONLY_ECODES:
            ton = user_timing.get("ton", ton_by_protocol.get(protocol.name))
            if ton is None:
                skipped.append(protocol.name)
                continue
            ecode_metadata[protocol.name] = {**user_timing, "ton": ton}
        elif ecode in _TIMING_UNSUPPORTED_ECODES:
            skipped.append(protocol.name)
            continue
        else:
            ecode_metadata[protocol.name] = user_timing
        extractable.append(protocol)
    return extractable, ecode_metadata, skipped


def _build_files_metadata(
    *,
    nwb_paths_with_ljp: list[tuple[Path, float]],
    ecodes_metadata_dict: dict,
) -> list[dict]:
    """Build files_metadata rows for NWB datasets (one file per cell).

    Each recording carries its own LJP (read from the ``ElectricalCellRecording``
    entity). If the user set a per-protocol LJP override (via
    ``protocol.timing_override()``), it takes priority over the recording's LJP.
    """
    return [
        {
            "cell_name": path.stem,
            "filepath": str(path),
            "ecodes": {
                ecode: {**meta, "ljp": meta.get("ljp", ljp)}
                for ecode, meta in ecodes_metadata_dict.items()
            },
        }
        for path, ljp in sorted(nwb_paths_with_ljp, key=operator.itemgetter(0))
    ]


def _discover_amplitudes(
    nwb_paths: list[Path],
    protocol_names: list[str],
) -> dict[str, list[float]]:
    """Union of step amplitudes (nA) discovered across every NWB, per protocol."""
    combined: dict[str, set[float]] = {p: set() for p in protocol_names}
    for path in nwb_paths:
        per_file = _read_amplitudes_from_nwb(path, protocol_names)
        for protocol_name, amps in per_file.items():
            combined[protocol_name].update(amps)
    return {p: sorted(v) for p, v in combined.items()}


def _build_targets_formatted(
    protocols: list,
    amplitudes_per_protocol: dict[str, list[float]],
    *,
    threshold_based: bool = False,
) -> list[dict]:
    """Flatten the per-protocol selection into ``bluepyefe.extract`` rows.

    Amplitude selection (rule 7):
    - If ``threshold_based=True`` and the protocol has ``extraction_amplitudes``
      set, those relative (% of rheobase) amplitudes are used.
    - Otherwise, fall back to the NWB-discovered amplitudes from
      ``amplitudes_per_protocol``. When falling back in relative mode a warning
      is logged (the discovered amplitudes may be absolute nA).

    Protocols with no amplitudes from either source contribute zero rows.
    """
    rows: list[dict] = []
    for protocol in protocols:
        ecode = protocol.name
        # eFEL overrides cascade global -> protocol -> feature.
        protocol_efel = protocol.efel_settings_override()

        # Amplitude selection per rule 7.
        if threshold_based and protocol.extraction_amplitudes:
            amplitudes = list(protocol.extraction_amplitudes)
        else:
            amplitudes = amplitudes_per_protocol.get(ecode, ())
            if threshold_based and not amplitudes:
                L.warning(
                    "Protocol %s: threshold_based=True but no extraction_amplitudes set"
                    " and no amplitudes discovered from NWB. No rows will be generated.",
                    ecode,
                )

        for amplitude in amplitudes:
            for feature in protocol.selected_efeatures():
                # Same exclusion as the L5PC pipeline: skip ohmic_input_resistance for IV_0.
                if (
                    ecode == "IV"
                    and amplitude == 0
                    and feature.efel_name == "ohmic_input_resistance_vb_ssse"
                ):
                    continue
                row = {
                    "efeature": feature.efel_name,
                    "protocol": ecode,
                    "amplitude": amplitude,
                    "tolerance": feature.tolerance,
                    "weight": feature.weight,
                    "efel_settings": {**protocol_efel, **feature.efel_settings_override()},
                }
                if feature.efeature_name is not None:
                    row["efeature_name"] = feature.efeature_name
                rows.append(row)
    return rows


def _build_extraction_recipes(settings: Settings) -> dict:
    """Build a minimal BluePyEModel ``recipes.json`` for the extraction step.

    Only the ``pipeline_settings`` consumed by ``extract_save_features_protocols``
    are populated — extracting experimental e-features needs no morphology,
    mechanisms or model parameters. ``features`` points at the file that the
    optimisation stage consumes; ``path_extract_config`` at the targets
    configuration stored through the access point at execution time.

    ``extract_absolute_amplitudes`` is the inverse of ``settings.threshold_based``:
    - Default (threshold_based=False): absolute amplitudes from NWB (nA).
    - threshold_based=True: relative amplitudes (% of rheobase).

    R_in and RMP protocols are only emitted when ``threshold_based=True`` and the
    corresponding protocol name is set; BluePyEModel nulls them under absolute
    amplitudes anyway.
    """
    # R_in / RMP protocol: [protocol_name, amplitude] or None.
    name_rin_protocol = None
    if settings.threshold_based and settings.rin_protocol_name:
        name_rin_protocol = [settings.rin_protocol_name, settings.rin_protocol_amplitude]

    name_rmp_protocol = None
    if settings.threshold_based and settings.rmp_protocol_name:
        name_rmp_protocol = [settings.rmp_protocol_name, settings.rmp_protocol_amplitude]

    pipeline_settings: dict = {
        "path_extract_config": TARGETS_CONFIG_RELPATH,
        "extract_absolute_amplitudes": not settings.threshold_based,
        "plot_extraction": settings.plot_extraction,
        "default_std_value": settings.default_std_value,
        "efel_settings": DEFAULT_EFEL_SETTINGS,
        "name_rmp_protocol": name_rmp_protocol,
        "name_Rin_protocol": name_rin_protocol,
        "extraction_threshold_value_save": settings.threshold_nvalue_save,
        "pickle_cells_extraction": settings.pickle_cells,
        "bound_max_std": settings.bound_max_std,
        "interpolate_RMP_extraction": settings.interpolate_rmp,
        "threshold_efeature_std": settings.threshold_efeature_std,
        "minimum_protocol_delay": settings.minimum_protocol_delay,
        "validation_protocols": list(settings.validation_protocols),
    }

    if settings.compute_rheobase:
        pipeline_settings["rheobase_strategy_extraction"] = "absolute"
        pipeline_settings["rheobase_settings_extraction"] = {"spike_threshold": 1}

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
    (the entry point that also backs ``EModel_pipeline.extract_efeatures``) rather
    than calling ``bluepyefe.extract.extract_efeatures`` directly, so the targets,
    pipeline settings and fitness-calculator output all flow through the
    BluePyEModel local access point. The function is invoked directly (instead of
    via ``EModel_pipeline``) to avoid importing the Nexus access point and its
    optional dependencies.

    Steps performed in ``coordinate_output_root``:

    1. Download the NWB asset of every ``ElectricalCellRecording`` listed in
       ``initialize.electrical_cell_recording`` into ``./ephys_data/<id>/``.
    2. Build ``files_metadata`` + ``targets`` rows from the user-provided blocks
       into a
       :class:`bluepyemodel.efeatures_extraction.targets_configuration.TargetsConfiguration`.
    3. Write a minimal ``./config/recipes.json`` (extraction ``pipeline_settings``
       only) and store the targets configuration through the local access point.
    4. Run ``extract_save_features_protocols`` on that access point, which extracts
       the e-features and writes the fitness-calculator configuration to
       ``./extracted_features.json`` for the optimisation stage to slot into
       ``config/features/<emodel>.json``.
    """

    name: ClassVar[str] = "EModel EFeature Extraction"
    description: ClassVar[str] = (
        "Extract experimental e-features from ephys traces via BluePyEModel."
    )

    config: EModelEFeatureExtractionSingleConfig

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

    def _build_targets_configuration(self, downloaded: list[tuple[Path, float]]) -> Any:
        """Assemble the BluePyEModel ``TargetsConfiguration`` from the NWBs.

        Reads per-protocol step amplitudes and, for eCodes that need it, the
        stimulus onset (``ton``) from the NWB currents; drops protocols whose
        timing can't be recovered (with a warning); and builds files_metadata +
        targets. Per-protocol ecode metadata carries each recording's LJP plus
        the detected ``ton`` for Ramp protocols.

        When ``autoselect`` is enabled, uses BluePyEModel's auto_targets presets
        instead of manually-built targets rows.
        """
        from bluepyefe.ecode import eCodes  # noqa: PLC0415
        from bluepyemodel.efeatures_extraction.targets_configuration import (  # noqa: PLC0415
            TargetsConfiguration,
        )

        nwb_paths = [path for path, _ in downloaded]

        # --- Autoselect mode: use auto_targets presets ---
        if self.config.efeatures_by_protocol.autoselect:
            from bluepyemodel.efeatures_extraction.auto_targets import (  # noqa: PLC0415
                get_auto_target_from_presets,
            )

            auto_targets = get_auto_target_from_presets(
                list(self.config.efeatures_by_protocol.auto_targets_presets)
            )
            L.info(
                "Autoselect enabled: using auto_targets presets %s",
                self.config.efeatures_by_protocol.auto_targets_presets,
            )

            # Still need files_metadata with LJP — build with empty ecodes_metadata
            # since auto_targets handles protocol selection internally.
            files = _build_files_metadata(
                nwb_paths_with_ljp=downloaded,
                ecodes_metadata_dict={},
            )
            if not files:
                msg = "No NWB ephys files were downloaded for extraction."
                raise FileNotFoundError(msg)

            rheobase_protocols = (
                [self.config.settings.rheobase_protocol_name]
                if self.config.settings.compute_rheobase
                else []
            )

            return TargetsConfiguration(
                files=files,
                auto_targets=auto_targets,
                protocols_rheobase=rheobase_protocols,
            )

        # --- Manual mode: build targets from per-protocol feature selection ---
        all_protocols = self.config.efeatures_by_protocol.protocols

        # Stimulus onset for protocols whose eCode (Ramp) needs it but doesn't
        # auto-detect it; the rest auto-detect their timing or use defaults.
        ton_names = [
            p.name for p in all_protocols if _ecode_class_name(p.name, eCodes) in _TON_ONLY_ECODES
        ]
        ton_per_protocol = _discover_timing(nwb_paths, ton_names) if ton_names else {}

        protocols_cfg, ecodes_metadata_dict, skipped = _partition_protocols(
            all_protocols, eCodes, ton_per_protocol
        )
        if skipped:
            L.warning(
                "Skipping protocols whose bluepyefe eCode needs stimulus timing not "
                "recoverable from the NWB: %s",
                skipped,
            )

        amplitudes_per_protocol = _discover_amplitudes(nwb_paths, [p.name for p in protocols_cfg])
        L.info("Discovered amplitudes per protocol (nA): %s", amplitudes_per_protocol)

        files = _build_files_metadata(
            nwb_paths_with_ljp=downloaded,
            ecodes_metadata_dict=ecodes_metadata_dict,
        )
        if not files:
            msg = "No NWB ephys files were downloaded for extraction."
            raise FileNotFoundError(msg)

        rheobase_protocols = (
            [self.config.settings.rheobase_protocol_name]
            if self.config.settings.compute_rheobase
            else []
        )

        return TargetsConfiguration(
            files=files,
            targets=_build_targets_formatted(
                protocols_cfg,
                amplitudes_per_protocol,
                threshold_based=self.config.settings.threshold_based,
            ),
            protocols_rheobase=rheobase_protocols,
        )

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

        # 2. Build the targets configuration (amplitudes + timing read from the NWB).
        targets_configuration = self._build_targets_configuration(downloaded)

        # 3. Write a minimal BluePyEModel recipe so extraction runs through the
        #    local access point rather than calling bluepyefe directly.
        _shared.write_recipes(
            _build_extraction_recipes(self.config.settings),
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
            self._register_task_result(coord_root, db_client)

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

        # Upload recipes JSON.
        # Note: entitycore does not yet have an asset label that accepts JSON
        # for recipes/protocols — efeature_extraction_protocols requires HDF5.
        # The recipes file is written to disk locally for downstream notebooks.
        recipes_path = coord_root / RECIPES_RELPATH
        if recipes_path.exists():
            L.info(
                "Recipes JSON written to %s (not uploaded — no compatible asset label).",
                recipes_path,
            )

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

        # Upload targets configuration JSON.
        # Note: same as recipes — no asset label accepts JSON for this content.
        targets_path = coord_root / TARGETS_CONFIG_RELPATH
        if targets_path.exists():
            L.info(
                "Targets JSON written to %s (not uploaded — no compatible asset label).",
                targets_path,
            )

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
