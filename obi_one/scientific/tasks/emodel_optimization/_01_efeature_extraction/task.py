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


def _build_targets_formatted(targets_dict: dict) -> list[dict]:
    """Flatten the per-protocol targets dict into ``bluepyefe.extract`` rows."""
    rows: list[dict] = []
    for ecode, protocol in targets_dict.items():
        for amplitude in protocol.amplitudes:
            for efeature in protocol.efeatures:
                # Same exclusion as the L5PC pipeline: skip ohmic_input_resistance for IV_0.
                if (
                    ecode == "IV"
                    and amplitude == 0
                    and efeature == "ohmic_input_resistance_vb_ssse"
                ):
                    continue
                rows.append(
                    {
                        "efeature": efeature,
                        "protocol": ecode,
                        "amplitude": amplitude,
                        "tolerance": protocol.tolerance,
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

        targets = self.config.targets
        extraction_settings = self.config.extraction_settings
        coord_root = Path(self.config.coordinate_output_root).resolve()

        # 1. Download the NWB ephys assets from entitycore (with per-recording LJP).
        ephys_data_root = coord_root / "ephys_data"
        downloaded = self._download_recordings(ephys_data_root, db_client)

        # 2. Build bluepyefe inputs via TargetsConfiguration (handles the BPE1 ->
        #    BPE2 format conversion for us).
        ecodes_metadata_dict = {
            ecode: meta.to_dict() for ecode, meta in targets.ecodes_metadata.items()
        }
        files = _build_files_metadata(
            nwb_paths_with_ljp=downloaded,
            ecodes_metadata_dict=ecodes_metadata_dict,
        )
        if not files:
            msg = f"No NWB ephys files were downloaded under {ephys_data_root}."
            raise FileNotFoundError(msg)

        targets_configuration = TargetsConfiguration(
            files=files,
            targets=_build_targets_formatted(targets.targets),
            protocols_rheobase=list(targets.protocols_rheobase),
        )

        # 3. chdir so bluepyefe's plot outputs are anchored to the working dir.
        extraction_dir = coord_root / "extraction"
        extraction_dir.mkdir(parents=True, exist_ok=True)
        with _shared.chdir(coord_root):
            efeatures, protocols, currents = extract_efeatures(
                output_directory=str(extraction_dir),
                files_metadata=targets_configuration.files_metadata_BPE,
                targets=targets_configuration.targets_BPE,
                protocols_rheobase=targets_configuration.protocols_rheobase_BPE,
                absolute_amplitude=extraction_settings.extract_absolute_amplitudes,
                efel_settings=self.config.efel_settings.to_dict(),
                plot=extraction_settings.plot_extraction,
                default_std_value=extraction_settings.default_std_value,
                write_files=False,
            )

        # 4. Serialise the fitness-calculator configuration for the next stage.
        fitness_calculator_config = FitnessCalculatorConfiguration(
            name_rmp_protocol=extraction_settings.name_rmp_protocol,
            name_rin_protocol=extraction_settings.name_rin_protocol,
            default_std_value=extraction_settings.default_std_value,
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
