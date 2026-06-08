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
from obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.blocks import (
    RheobaseStrategy,
    Settings,
)
from obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.config import (
    EModelEFeatureExtractionSingleConfig,
)

L = logging.getLogger(__name__)

EXTRACTED_FEATURES_FILENAME = "extracted_features.json"

# BluePyEModel local access-point layout, relative to ``coordinate_output_root``.
EMODEL_NAME = "emodel"
RECIPES_RELPATH = "config/recipes.json"
TARGETS_CONFIG_RELPATH = "config/extract_config/targets.json"

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
    passed to bluepyefe (``{"ton": ms}`` for ``Ramp``, else ``{}``). Protocols
    whose eCode needs timing we can't supply are returned in ``skipped``.
    """
    extractable: list = []
    ecode_metadata: dict[str, dict] = {}
    skipped: list[str] = []
    for protocol in protocols:
        ecode = _ecode_class_name(protocol.name, ecodes)
        if ecode in _TON_ONLY_ECODES:
            ton = ton_by_protocol.get(protocol.name)
            if ton is None:
                skipped.append(protocol.name)
                continue
            ecode_metadata[protocol.name] = {"ton": ton}
        elif ecode in _TIMING_UNSUPPORTED_ECODES:
            skipped.append(protocol.name)
            continue
        else:
            ecode_metadata[protocol.name] = {}
        extractable.append(protocol)
    return extractable, ecode_metadata, skipped


def _build_files_metadata(
    *,
    nwb_paths_with_ljp: list[tuple[Path, float]],
    ecodes_metadata_dict: dict,
) -> list[dict]:
    """Build files_metadata rows for NWB datasets (one file per cell).

    Each recording carries its own LJP (read from the ``ElectricalCellRecording``
    entity), so it's merged into the per-ecode metadata of that recording's row.
    """
    return [
        {
            "cell_name": path.stem,
            "filepath": str(path),
            "ecodes": {ecode: {**meta, "ljp": ljp} for ecode, meta in ecodes_metadata_dict.items()},
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
) -> list[dict]:
    """Flatten the per-protocol selection into ``bluepyefe.extract`` rows.

    Amplitudes are sourced from the NWB inspection — protocols with no
    discovered amplitudes contribute zero rows.
    """
    rows: list[dict] = []
    for protocol in protocols:
        ecode = protocol.name
        # eFEL overrides cascade global (Settings) -> protocol -> feature; the
        # most specific level wins, so feature overrides are merged on top.
        protocol_efel = protocol.efel_settings_override()
        for amplitude in amplitudes_per_protocol.get(ecode, ()):
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


def _build_extraction_recipes(settings: Settings, rheobase: RheobaseStrategy) -> dict:
    """Build a minimal BluePyEModel ``recipes.json`` for the extraction step.

    Only the ``pipeline_settings`` consumed by ``extract_save_features_protocols``
    are populated — extracting experimental e-features needs no morphology,
    mechanisms or model parameters. ``features`` points at the file that the
    optimisation stage consumes; ``path_extract_config`` at the targets
    configuration stored through the access point at execution time.

    ``extract_absolute_amplitudes`` is forced on because the amplitudes are read
    from the NWB in absolute units (nA). Note that BluePyEModel nulls
    ``name_rmp_protocol``/``name_Rin_protocol`` (with a warning) when absolute
    amplitudes are used, as the threshold-based RMP/Rin protocols do not apply.
    """
    return {
        EMODEL_NAME: {
            "features": EXTRACTED_FEATURES_FILENAME,
            "pipeline_settings": {
                "path_extract_config": TARGETS_CONFIG_RELPATH,
                "extract_absolute_amplitudes": True,
                "plot_extraction": settings.plot_extraction,
                "default_std_value": settings.default_std_value,
                "efel_settings": settings.efel_to_dict(),
                "name_rmp_protocol": settings.name_rmp_protocol,
                "name_Rin_protocol": settings.name_rin_protocol,
                "extraction_threshold_value_save": settings.threshold_nvalue_save,
                "rheobase_strategy_extraction": rheobase.strategy,
                "rheobase_settings_extraction": rheobase.to_dict(),
                "pickle_cells_extraction": settings.pickle_cells,
                "bound_max_std": settings.bound_max_std,
                "interpolate_RMP_extraction": settings.interpolate_rmp,
                "threshold_efeature_std": settings.threshold_efeature_std,
                "minimum_protocol_delay": settings.minimum_protocol_delay,
            },
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
            ljp = recording.entity(db_client=db_client).ljp
            downloaded.append((path, ljp))
        return downloaded

    def _build_targets_configuration(self, downloaded: list[tuple[Path, float]]) -> Any:
        """Assemble the BluePyEModel ``TargetsConfiguration`` from the NWBs.

        Reads per-protocol step amplitudes and, for eCodes that need it, the
        stimulus onset (``ton``) from the NWB currents; drops protocols whose
        timing can't be recovered (with a warning); and builds files_metadata +
        targets. Per-protocol ecode metadata carries each recording's LJP plus
        the detected ``ton`` for Ramp protocols.
        """
        from bluepyefe.ecode import eCodes  # noqa: PLC0415
        from bluepyemodel.efeatures_extraction.targets_configuration import (  # noqa: PLC0415
            TargetsConfiguration,
        )

        nwb_paths = [path for path, _ in downloaded]
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

        return TargetsConfiguration(
            files=files,
            targets=_build_targets_formatted(protocols_cfg, amplitudes_per_protocol),
            protocols_rheobase=list(self.config.rheobase.protocols),
        )

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,
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
            _build_extraction_recipes(self.config.settings, self.config.rheobase),
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

        return coord_root
