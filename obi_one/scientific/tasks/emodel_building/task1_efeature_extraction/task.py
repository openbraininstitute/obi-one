"""Task wrapper for the experimental e-feature extraction step."""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import entitysdk
import httpx

from obi_one.core.task import Task
from obi_one.db_sdk.db_sdk import fetch_recording_summary
from obi_one.scientific.from_id.electrical_cell_recording_from_id import (
    ElectricalCellRecordingFromID,
)
from obi_one.scientific.library.recording_summary import (
    RecordingSummary,
    compute_recording_summary,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.protocol_and_feature_selection import (  # ruff: ignore[line-too-long]
    SelectEFeaturesByProtocol,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.settings import (
    Settings,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.config import (
    EModelEFeatureExtractionSingleConfig,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.efeatures import (  # ruff: ignore[line-too-long]
    EFeature,
    OhmicInputResistanceVbSsseFeature,
    VoltageBaseFeature,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (  # ruff: ignore[line-too-long]
    Protocol,
    protocol_class_by_type,
    protocol_class_name_for,
)
from obi_one.utils.filesystem import chdir, create_dir
from obi_one.utils.io import write_json

L = logging.getLogger(__name__)

EXTRACTED_FEATURES_FILENAME = "extracted_features.json"

# BluePyEModel local access-point layout, relative to ``coordinate_output_root``.
EMODEL_NAME = "emodel"
RECIPES_RELPATH = "config/recipes.json"
TARGETS_CONFIG_RELPATH = "config/extract_config/targets.json"

# Fitness weight applied to every target. Amplitudes come from the recordings'
# summaries (``AmplitudesByProtocol``), so each target should match a trace; the
# tolerance absorbs the small difference between the summary's amplitude and the one
# bluepyefe recomputes as median(current[ton:toff]). It must stay well below the
# smallest step spacing in typical protocols (~20-50 pA), so 10 pA.
DEFAULT_TARGET_WEIGHT = 1.0
AMPLITUDE_TOLERANCE = 0.01

# Features BluePyEModel's threshold-based optimisation reads from the RMP and
# input-resistance sweeps (see ``TargetsConfiguration.check_presence_RMP_Rin_efeatures``).
RMP_FEATURES: tuple[type[EFeature], ...] = (VoltageBaseFeature,)
RIN_FEATURES: tuple[type[EFeature], ...] = (VoltageBaseFeature, OhmicInputResistanceVbSsseFeature)


@dataclass(frozen=True)
class RecordingInput:
    """One downloaded recording: its NWB path, LJP (mV), summary and entity id."""

    path: Path
    ljp: float
    summary: RecordingSummary
    recording_id: str

    @property
    def cell_name(self) -> str:
        """The bluepyefe cell name of the recording (its NWB file name, no suffix)."""
        return self.path.stem


def _is_relative(settings: Settings) -> bool:
    return settings.amplitude_mode == "relative"


def _protocol_canonical_name(type_name: str) -> str:
    """The bluepyefe protocol name (e.g. ``IDthresh``) of a ``Protocol`` type name."""
    cls = protocol_class_by_type(type_name)
    if cls is None:
        msg = f"Unknown protocol type {type_name!r}."
        raise ValueError(msg)
    return cls.protocol_name


def _used_protocols(
    selection: SelectEFeaturesByProtocol, settings: Settings
) -> dict[str, tuple[str, dict]]:
    """``{protocol_type: (bluepyefe_name, timing_set_in_config)}`` of the protocols read.

    The selected protocols, plus in relative mode the rheobase protocols, which are
    read for the rheobase even when no feature is extracted from them.
    """
    used = {type(p).__name__: (p.protocol_name, p.stim_timing()) for p in selection.protocols}
    if _is_relative(settings):
        for type_name in settings.rheobase_protocols:
            used.setdefault(type_name, (_protocol_canonical_name(type_name), {}))
    return used


def _summary_timing(
    recording: RecordingInput, raw_names: list[str], protocol_name: str
) -> dict[str, float]:
    """One value per timing key of a protocol in one file, from the recording's summary.

    The file's sweeps of the protocol (under all of ``raw_names``) must agree: bluepyefe
    takes one timing per protocol and file. When they do not, ``{}`` is returned with a
    warning, and bluepyefe detects the timing itself.
    """
    values: dict[str, set[float]] = {}
    for raw_name in raw_names:
        for key, times in recording.summary.protocols[raw_name].timing().items():
            values.setdefault(key, set()).update(times)
    mixed = {key: sorted(times) for key, times in values.items() if len(times) > 1}
    if mixed:
        L.warning(
            "The %s sweeps of %s have different timings %s: bluepyefe detects them instead."
            " Set the protocol's timing to choose one.",
            protocol_name,
            recording.path.name,
            mixed,
        )
        return {}
    return {key: next(iter(times)) for key, times in values.items()}


def _build_files_metadata(
    recordings: list[RecordingInput],
    used_protocols: dict[str, tuple[str, dict]],
) -> list[dict]:
    """Build the ``files_metadata`` rows (one file per cell) from the recordings' summaries.

    Each file lists only the used protocols its summary has. Each entry carries the
    recording's LJP; the protocol name(s) as written in the file when they differ from
    the bluepyefe name (e.g. ``IDThreshold`` for ``IDthresh``, a reader hint bluepyefe
    honours over the files-metadata key); and the stimulus timing: set in the config,
    else detected in that file (see :func:`_summary_timing`), else left to bluepyefe.
    """
    rows: list[dict] = []
    for recording in sorted(recordings, key=lambda r: r.path):
        ecodes: dict[str, dict] = {}
        for type_name, (protocol_name, config_timing) in used_protocols.items():
            raw_names = sorted(
                raw
                for raw in recording.summary.protocols
                if protocol_class_name_for(raw) == type_name
            )
            if not raw_names:
                continue
            entry: dict[str, Any] = {
                **_summary_timing(recording, raw_names, protocol_name),
                **config_timing,
                "ljp": recording.ljp,
            }
            if raw_names != [protocol_name]:
                entry["protocol_name"] = raw_names if len(raw_names) > 1 else raw_names[0]
            ecodes[protocol_name] = entry
        rows.append(
            {
                "cell_name": recording.cell_name,
                "filepath": str(recording.path),
                "ecodes": ecodes,
            }
        )
    return rows


def _check_rheobases(recordings: list[RecordingInput], settings: Settings) -> None:
    """Fail unless every recording has a usable rheobase from the rheobase protocols.

    bluepyefe leaves a recording without rheobase out of every relative target without
    an error. The rheobases come from the recordings' summaries (bluepyefe ``absolute``
    strategy); with another ``rheobase_strategy`` a recording can still lose its
    rheobase, which the check after extraction reports.
    """
    missing = {
        recording.path.name: {
            raw: value
            for raw, value in recording.summary.rheobase.items()
            if protocol_class_name_for(raw) in settings.rheobase_protocols
        }
        for recording in recordings
        if recording.summary.rheobase_for(settings.rheobase_protocols) is None
    }
    if missing:
        details = "; ".join(
            f"{name}: {rheobases or 'no such sweeps'}" for name, rheobases in missing.items()
        )
        msg = (
            f"No rheobase from {', '.join(settings.rheobase_protocols)} for {details}."
            " Relative amplitudes need every recording to have sweeps of these protocols"
            " that fire, and none that fires at 0 nA or below. Choose other"
            " `rheobase_protocols`, check the spike detection threshold, or leave these"
            " recordings out."
        )
        raise ValueError(msg)


def _role_targets(
    selection: SelectEFeaturesByProtocol, settings: Settings
) -> list[tuple[Protocol, float, tuple[EFeature, ...]]]:
    """``(protocol, amplitude, features)`` of the RMP and input-resistance targets.

    A role feature the protocol already selects keeps its setting overrides;
    otherwise a default instance is used.
    """
    targets = []
    for type_name, amplitude, feature_classes in (
        (settings.rmp_protocol, settings.rmp_amplitude, RMP_FEATURES),
        (settings.rin_protocol, settings.rin_amplitude, RIN_FEATURES),
    ):
        protocol = selection.protocol_of_type(type_name)
        if protocol is None:
            msg = f"{type_name} is not one of the selected protocols."
            raise ValueError(msg)
        selected = {feature.efel_name: feature for feature in selection.features_for(protocol)}
        features = tuple(selected.get(cls.efel_name) or cls() for cls in feature_classes)
        targets.append((protocol, amplitude, features))
    return targets


def _build_targets(
    selection: SelectEFeaturesByProtocol,
    settings: Settings,
) -> tuple[list[dict], list[str]]:
    """Flatten the per-protocol selection into ``bluepyefe.extract`` target rows.

    For every protocol, every ``(amplitude, is_validation)`` pair of its
    ``extraction_amplitudes`` and every feature in ``selection.features_for(protocol)``
    yields one target. Amplitudes are in nA, matched within ``AMPLITUDE_TOLERANCE``, or
    in relative mode in % of rheobase, matched within the settings'
    ``relative_amplitude_tolerance`` percentage points; relative mode also adds the
    RMP and input-resistance targets threshold-based optimisation needs
    (:data:`RMP_FEATURES` at ``rmp_amplitude``, :data:`RIN_FEATURES` at
    ``rin_amplitude``). A feature already targeted at the same protocol and amplitude
    is not repeated. Each target's ``efel_settings`` apply the cascade
    feature > protocol > global.
    Amplitudes flagged ``is_validation`` are returned as ``{protocol}_{amplitude}``
    validation-protocol names for the recipe.
    """
    relative = _is_relative(settings)
    tolerance = settings.relative_amplitude_tolerance if relative else AMPLITUDE_TOLERANCE
    global_efel_settings = settings.global_efel_settings()
    targets: list[tuple[Protocol, float, tuple[EFeature, ...]]] = []
    validation_names: list[str] = []
    for protocol in selection.protocols:
        features = selection.features_for(protocol)
        for amplitude, is_validation in protocol.extraction_amplitudes:
            if is_validation:
                validation_names.append(f"{protocol.protocol_name}_{amplitude}")
            targets.append((protocol, amplitude, features))
    if relative and targets:
        targets.extend(_role_targets(selection, settings))

    rows: list[dict] = []
    seen: set[tuple[str, str, float]] = set()
    for protocol, amplitude, features in targets:
        protocol_overrides = protocol.efel_settings_overrides()
        for feature in features:
            key = (feature.efel_name, protocol.protocol_name, amplitude)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "efeature": feature.efel_name,
                    "protocol": protocol.protocol_name,
                    "amplitude": amplitude,
                    "tolerance": tolerance,
                    "weight": DEFAULT_TARGET_WEIGHT,
                    "efel_settings": {
                        **global_efel_settings,
                        **protocol_overrides,
                        **feature.efel_settings_overrides(),
                    },
                }
            )
    return rows, validation_names


def _relative_pipeline_settings(settings: Settings) -> dict:
    """Pipeline settings that make BluePyEModel extract relative amplitudes.

    With ``extract_absolute_amplitudes`` False and both the RMP and input-resistance
    protocols named (``{protocol}_{amplitude}``, amplitude in % of rheobase), every
    extracted protocol becomes a ``ThresholdBasedProtocol``: optimisation and
    validation then stimulate each e-model at the same % of its own threshold
    current, found by BluePyEModel's holding and threshold current searches.
    """
    rmp = _protocol_canonical_name(settings.rmp_protocol)
    rin = _protocol_canonical_name(settings.rin_protocol)
    return {
        "extract_absolute_amplitudes": False,
        "name_rmp_protocol": f"{rmp}_{settings.rmp_amplitude}",
        "name_Rin_protocol": f"{rin}_{settings.rin_amplitude}",
        "rheobase_strategy_extraction": settings.rheobase_strategy,
    }


def _build_extraction_recipes(
    settings: Settings,
    *,
    validation_protocol_names: list[str],
) -> dict:
    """Build a minimal BluePyEModel ``recipes.json`` for the extraction step.

    Only the ``pipeline_settings`` consumed by ``extract_save_features_protocols``
    are populated — no morphology, mechanisms or model parameters are needed.
    Amplitudes are absolute (nA) unless ``amplitude_mode`` is relative, which
    switches to :func:`_relative_pipeline_settings`. ``efel_settings`` is the global
    base of the cascade; the per-target overrides in the targets configuration refine
    it (feature > protocol > global).
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
    if _is_relative(settings):
        pipeline_settings.update(_relative_pipeline_settings(settings))
    return {
        EMODEL_NAME: {
            "features": EXTRACTED_FEATURES_FILENAME,
            "pipeline_settings": pipeline_settings,
        },
    }


class _CellCapture:
    """A ``map`` replacement that keeps the bluepyefe cells extraction reads.

    BluePyEModel hands its mapper to bluepyefe, which maps the reading of each cell
    with it. The cells are the objects bluepyefe then computes the rheobases on and
    groups into targets, so after extraction they tell which recordings were used.
    """

    def __init__(self) -> None:
        self.cells: list = []

    def __call__(self, function: Callable, iterable: Iterable) -> list:
        from bluepyefe.cell import Cell  # ruff: ignore[import-outside-top-level]

        results = list(map(function, iterable))
        self.cells.extend(result for result in results if isinstance(result, Cell))
        return results


def _check_extraction(
    cells: list,
    recordings: list[RecordingInput],
    targets: list[dict],
    *,
    relative: bool,
) -> None:
    """Report what extraction left out, which bluepyefe does silently.

    Warns for each target amplitude no sweep matched, and fails when a recording
    contributed to no target at all: no rheobase in relative mode (bluepyefe drops the
    cell), or no sweep at any selected amplitude.
    """
    by_name = {cell.name: cell for cell in cells}
    amplitudes = sorted({(t["protocol"], t["amplitude"], t["tolerance"]) for t in targets})
    matched: set[tuple[str, float, float]] = set()
    unused: dict[str, str] = {}
    for recording in recordings:
        cell = by_name.get(recording.cell_name)
        if cell is None:
            unused[recording.path.name] = "none of the selected protocols"
            continue
        if relative and cell.rheobase is None:
            unused[recording.path.name] = "no rheobase"
            continue
        used = False
        for protocol, amplitude, tolerance in amplitudes:
            if any(
                rec.in_target(amplitude, tolerance, absolute_amplitude=not relative)
                for rec in cell.get_recordings_by_protocol_name(protocol)
            ):
                matched.add((protocol, amplitude, tolerance))
                used = True
        if not used:
            unused[recording.path.name] = "no sweep at the selected amplitudes"
    unit = "% of rheobase" if relative else "nA"
    for protocol, amplitude, _ in amplitudes:
        if not any(m[:2] == (protocol, amplitude) for m in matched):
            L.warning("No sweep matched the %s target at %s %s.", protocol, amplitude, unit)
    if unused:
        details = "; ".join(f"{name} ({reason})" for name, reason in unused.items())
        msg = (
            f"These recordings contributed to no extraction target: {details}. Choose"
            " amplitudes they have, or leave them out."
        )
        raise ValueError(msg)


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
       (amplitudes and the eFEL settings cascade) and each recording's
       ``recording_summary`` (protocol names and stimulus timing per file) into a
       :class:`bluepyemodel.efeatures_extraction.targets_configuration.TargetsConfiguration`.
    3. Write a minimal ``./config/recipes.json`` (extraction ``pipeline_settings``
       only) and store the targets configuration through the local access point.
    4. Run ``extract_save_features_protocols`` on that access point, writing the
       fitness-calculator configuration to ``./extracted_features.json`` for the
       optimisation stage, then fail if a recording contributed to no target.

    With relative amplitudes (``amplitude_mode`` relative, % of rheobase) bluepyefe
    computes each recording's rheobase, and every output protocol is a
    ``ThresholdBasedProtocol`` backed by
    RMP, input-resistance, holding and threshold current targets, so optimisation
    and validation stimulate each e-model relative to its own threshold current.
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
    ) -> list[RecordingInput]:
        """Download each recording's NWB asset and get its summary and LJP.

        The summary is the recording's ``recording_summary`` asset, or, for a recording
        without one, computed from the downloaded NWB file (not uploaded).
        """
        downloaded: list[RecordingInput] = []
        for recording in self.config.initialize.electrical_cell_recording:
            if not isinstance(recording, ElectricalCellRecordingFromID):
                msg = f"Expected ElectricalCellRecordingFromID, got {type(recording).__name__}."
                raise TypeError(msg)
            path = recording.download_nwb_asset(
                dest_dir=ephys_data_root / recording.id_str, db_client=db_client
            )
            entity = recording.entity(db_client=db_client)
            summary = fetch_recording_summary(db_client, entity)
            if summary is None:
                L.info("Recording %s has no summary: computing it from %s", entity.id, path.name)
                summary = compute_recording_summary(path)
            downloaded.append(
                RecordingInput(
                    path=path, ljp=entity.ljp, summary=summary, recording_id=recording.id_str
                )
            )
        return downloaded

    def _build_targets_configuration(
        self, recordings: list[RecordingInput]
    ) -> tuple[Any, list[dict], list[str]]:
        """Assemble the BluePyEModel ``TargetsConfiguration`` from the recordings.

        Amplitudes come from the per-protocol config; protocol names and stimulus timing
        per file from the recordings' summaries, so no NWB file is read here. In
        relative mode the ``rheobase_protocols`` become the configuration's
        ``protocols_rheobase`` and every recording's rheobase is checked first
        (:func:`_check_rheobases`). Returns the configuration, the target rows and the
        validation-protocol names.
        """
        from bluepyemodel.efeatures_extraction.targets_configuration import (  # ruff: ignore[import-outside-top-level]
            TargetsConfiguration,
        )

        selection = self.config.efeatures_by_protocol.selection
        settings = self.config.settings
        if not recordings:
            msg = "No NWB ephys files were downloaded for extraction."
            raise FileNotFoundError(msg)

        targets, validation_names = _build_targets(selection, settings)
        if not targets:
            msg = (
                "No extraction targets were built: `extraction_amplitudes` is empty for"
                " every configured protocol. Populate the amplitudes from the recordings"
                " (mapped-electrical-cell-recording-properties endpoint) before"
                " launching the task."
            )
            raise ValueError(msg)

        protocols_rheobase: list[str] = []
        if _is_relative(settings):
            _check_rheobases(recordings, settings)
            protocols_rheobase = [_protocol_canonical_name(t) for t in settings.rheobase_protocols]
        files = _build_files_metadata(recordings, _used_protocols(selection, settings))
        configuration = TargetsConfiguration(
            files=files, targets=targets, protocols_rheobase=protocols_rheobase
        )
        return configuration, targets, validation_names

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client,
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: str | None = None,
    ) -> Path:
        from bluepyemodel.access_point import (  # ruff: ignore[import-outside-top-level]
            get_access_point,
        )
        from bluepyemodel.efeatures_extraction.efeatures_extraction import (  # ruff: ignore[import-outside-top-level]
            extract_save_features_protocols,
        )

        coord_root = Path(self.config.coordinate_output_root).resolve()

        execution_activity = self._get_execution_activity(
            db_client=db_client, execution_activity_id=execution_activity_id
        )

        # 1. Download the NWB ephys assets from entitycore, with each recording's LJP
        #    and summary.
        recordings = self._download_recordings(coord_root / "ephys_data", db_client)

        # 2. Build the targets configuration + collect validation-protocol names.
        targets_configuration, targets, validation_names = self._build_targets_configuration(
            recordings
        )

        # 3. Write a minimal BluePyEModel recipe so extraction runs through the
        #    local access point rather than calling bluepyefe directly.
        recipes_path = coord_root / RECIPES_RELPATH
        create_dir(recipes_path.parent)
        write_json(
            _build_extraction_recipes(
                self.config.settings,
                validation_protocol_names=validation_names,
            ),
            recipes_path,
            indent=4,
        )

        # 4. Run BluePyEModel's extraction. chdir so the local access point anchors
        #    its relative paths (recipes, targets config, figures, extracted
        #    features) to the coordinate working directory. The mapper keeps the
        #    bluepyefe cells for the check of what extraction left out.
        capture = _CellCapture()
        with chdir(coord_root):
            access_point = get_access_point(
                access_point="local",
                emodel=EMODEL_NAME,
                recipes_path=f"./{RECIPES_RELPATH}",
                final_path="final.json",
            )
            access_point.store_targets_configuration(targets_configuration)
            extract_save_features_protocols(access_point=access_point, mapper=capture)
        _check_extraction(
            capture.cells,
            recordings,
            targets,
            relative=_is_relative(self.config.settings),
        )

        # 5. Register TaskResult entity and upload assets to entitycore.
        registered_task_result_id: str | None = None
        if db_client is not None:
            try:
                registered_task_result_id = self._register_task_result(coord_root, db_client)
            except httpx.HTTPError as e:
                L.warning(
                    "TaskResult registration failed (extraction output is still"
                    " available locally at %s): %s",
                    coord_root,
                    e,
                )

            if registered_task_result_id is not None:
                self._update_execution_activity(
                    db_client=db_client,
                    execution_activity=execution_activity,
                    generated=[registered_task_result_id],
                )

        return coord_root

    def _build_figures_manifest(self, figures_dir: Path) -> dict:  # ruff: ignore[no-self-use]
        """Build a manifest.json describing all PDF figure files in the directory."""
        import re  # ruff: ignore[import-outside-top-level]

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
    ) -> str | None:
        """Register a TaskResult entity and upload extraction output assets.

        Returns the registered TaskResult ID, or None if registration fails.
        """
        import json  # ruff: ignore[import-outside-top-level]

        from entitysdk.models import TaskResult  # ruff: ignore[import-outside-top-level]
        from entitysdk.types import (  # ruff: ignore[import-outside-top-level]
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
                entity_id=task_result.id,
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
                entity_id=task_result.id,
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
        from entitysdk.models import Derivation  # ruff: ignore[import-outside-top-level]
        from entitysdk.types import DerivationType  # ruff: ignore[import-outside-top-level]

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

        return str(task_result.id)
