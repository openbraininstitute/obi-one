"""Task wrapper for the experimental e-feature extraction step."""

import json
import logging
import operator
from pathlib import Path
from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.from_id.electrical_cell_recording_from_id import (
    ElectricalCellRecordingFromID,
)
from obi_one.scientific.library.electrical_cell_recording_properties import (
    _read_amplitudes_from_nwb,
)
from obi_one.scientific.tasks.emodel_optimization import _shared
from obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.config import (
    EModelEFeatureExtractionSingleConfig,
)

L = logging.getLogger(__name__)

EXTRACTED_FEATURES_FILENAME = "extracted_features.json"


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
        for amplitude in amplitudes_per_protocol.get(ecode, ()):
            for feature in protocol.selected_efeatures():
                # Same exclusion as the L5PC pipeline: skip ohmic_input_resistance for IV_0.
                if (
                    ecode == "IV"
                    and amplitude == 0
                    and feature.efel_name == "ohmic_input_resistance_vb_ssse"
                ):
                    continue
                rows.append(
                    {
                        "efeature": feature.efel_name,
                        "protocol": ecode,
                        "amplitude": amplitude,
                        "tolerance": feature.tolerance,
                        "efel_settings": feature.efel_settings_override(),
                    }
                )
    return rows


class EModelEFeatureExtractionTask(Task):
    """Extract experimental e-features from raw ephys traces via ``bluepyefe``.

    Steps performed in ``coordinate_output_root``:

    1. Download the NWB asset of every ``ElectricalCellRecording`` listed in
       ``initialize.electrical_cell_recording`` into ``./ephys_data/<id>/``.
    2. Build ``files_metadata`` + ``targets`` rows from the user-provided blocks
       and re-shape them into the BPE2 input format via
       :class:`bluepyemodel.efeatures_extraction.targets_configuration.TargetsConfiguration`.
    3. Run ``bluepyefe.extract.extract_efeatures`` directly — no
       ``EModel_pipeline``, recipes or model assets are needed.
    4. Wrap the bluepyefe output in a
       :class:`bluepyemodel.evaluation.fitness_calculator_configuration.FitnessCalculatorConfiguration`
       and serialise it to ``./extracted_features.json`` so the optimisation
       stage can slot it into ``config/features/<emodel>.json``.
    """

    name: ClassVar[str] = "EModel EFeature Extraction"
    description: ClassVar[str] = "Extract experimental e-features from ephys traces via bluepyefe."

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

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> Path:
        from bluepyefe.extract import extract_efeatures  # noqa: PLC0415
        from bluepyemodel.efeatures_extraction.targets_configuration import (  # noqa: PLC0415
            TargetsConfiguration,
        )
        from bluepyemodel.evaluation.fitness_calculator_configuration import (  # noqa: PLC0415
            FitnessCalculatorConfiguration,
        )

        settings = self.config.settings
        protocols_cfg = self.config.efeatures_by_protocol.protocols
        coord_root = Path(self.config.coordinate_output_root).resolve()

        # 1. Download the NWB ephys assets from entitycore (with per-recording LJP).
        ephys_data_root = coord_root / "ephys_data"
        downloaded = self._download_recordings(ephys_data_root, db_client)

        # 2. Inspect each NWB to discover per-protocol step amplitudes (in nA);
        #    leave ecode timing metadata empty so bluepyefe auto-detects it from
        #    the current waveform. All protocol-level metadata that lives in the
        #    NWB stays out of the user-facing schema.
        protocol_names = [p.name for p in protocols_cfg]
        amplitudes_per_protocol = _discover_amplitudes(
            [path for path, _ in downloaded], protocol_names,
        )
        L.info("Discovered amplitudes per protocol (nA): %s", amplitudes_per_protocol)

        ecodes_metadata_dict = {name: {} for name in protocol_names}
        files = _build_files_metadata(
            nwb_paths_with_ljp=downloaded,
            ecodes_metadata_dict=ecodes_metadata_dict,
        )
        if not files:
            msg = f"No NWB ephys files were downloaded under {ephys_data_root}."
            raise FileNotFoundError(msg)

        targets_configuration = TargetsConfiguration(
            files=files,
            targets=_build_targets_formatted(protocols_cfg, amplitudes_per_protocol),
            protocols_rheobase=list(settings.protocols_rheobase),
        )

        # 3. chdir so bluepyefe's plot outputs are anchored to the working dir.
        #    NWB-derived amplitudes are absolute (nA), so force absolute mode.
        extraction_dir = coord_root / "extraction"
        extraction_dir.mkdir(parents=True, exist_ok=True)
        with _shared.chdir(coord_root):
            efeatures, protocols, currents = extract_efeatures(
                output_directory=str(extraction_dir),
                files_metadata=targets_configuration.files_metadata_BPE,
                targets=targets_configuration.targets_BPE,
                protocols_rheobase=targets_configuration.protocols_rheobase_BPE,
                absolute_amplitude=True,
                efel_settings=settings.efel_to_dict(),
                plot=settings.plot_extraction,
                default_std_value=settings.default_std_value,
                write_files=False,
            )

        # 4. Serialise the fitness-calculator configuration for the next stage.
        fitness_calculator_config = FitnessCalculatorConfiguration(
            name_rmp_protocol=settings.name_rmp_protocol,
            name_rin_protocol=settings.name_rin_protocol,
            default_std_value=settings.default_std_value,
        )
        fitness_calculator_config.init_from_bluepyefe(
            efeatures,
            protocols,
            currents,
            threshold_efeature_std=None,
        )

        (coord_root / EXTRACTED_FEATURES_FILENAME).write_text(
            json.dumps(fitness_calculator_config.as_dict(), indent=2)
        )

        return coord_root
