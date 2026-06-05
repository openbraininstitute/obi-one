"""Task wrapper for the experimental e-feature extraction step."""

import json
import logging
from pathlib import Path
from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.tasks.emodel_optimization import _shared
from obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.config import (
    EModelEFeatureExtractionSingleConfig,
)

L = logging.getLogger(__name__)

EXTRACTED_FEATURES_FILENAME = "extracted_features.json"


def _build_files_metadata(
    *,
    file_type: str,
    ephys_data_path: Path,
    ecodes_metadata_dict: dict,
    voltage_pattern: str,
    current_pattern: str,
    voltage_unit: str,
    current_unit: str,
    time_unit: str,
) -> list[dict]:
    """Replicate ``configure_targets()`` from the L5PC example pipeline.py.

    https://github.com/openbraininstitute/BluePyEModel/blob/main/examples/L5PC/pipeline.py
    """
    files_metadata: list[dict] = []
    if file_type == "ibw":
        for path in sorted(Path(ephys_data_path).glob(f"*{voltage_pattern}*.ibw")):
            fn = path.name
            for ecode, ecode_meta in ecodes_metadata_dict.items():
                if ecode in fn:
                    files_metadata.append(
                        {
                            "cell_name": path.parent.name,
                            "filename": path.stem,
                            "ecodes": {ecode: ecode_meta},
                            "other_metadata": {
                                "v_file": str(path),
                                "i_file": str(path).replace(voltage_pattern, current_pattern),
                                "i_unit": current_unit,
                                "v_unit": voltage_unit,
                                "t_unit": time_unit,
                            },
                        }
                    )
    elif file_type == "nwb":
        files_metadata.extend(
            {
                "cell_name": path.stem,
                "filepath": str(path),
                "ecodes": ecodes_metadata_dict,
            }
            for path in sorted(Path(ephys_data_path).glob("*.nwb"))
        )
    else:
        msg = f"Unsupported file_type: {file_type}. Expected 'ibw' or 'nwb'."
        raise ValueError(msg)

    if not files_metadata:
        msg = (
            f"No experimental ephys files found under {ephys_data_path} for file_type"
            f" '{file_type}'."
        )
        raise FileNotFoundError(msg)
    return files_metadata


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

    1. Copy the ephys data into the working directory.
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

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
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

        init = self.config.initialize
        targets = self.config.targets
        extraction_settings = self.config.extraction_settings
        efel_settings = self.config.efel_settings
        coord_root = Path(self.config.coordinate_output_root).resolve()

        # 1. Copy the ephys data into the working directory.
        ephys_data_target = coord_root / "ephys_data" / Path(init.ephys_data_path).name
        _shared.copy_tree(Path(init.ephys_data_path).resolve(), ephys_data_target)

        # 2. Build bluepyefe inputs via TargetsConfiguration (handles the BPE1 ->
        #    BPE2 format conversion for us).
        ecodes_metadata_dict = {
            ecode: meta.to_dict() for ecode, meta in targets.ecodes_metadata.items()
        }
        files = _build_files_metadata(
            file_type=targets.file_type,
            ephys_data_path=ephys_data_target,
            ecodes_metadata_dict=ecodes_metadata_dict,
            voltage_pattern=targets.ibw_voltage_channel_pattern,
            current_pattern=targets.ibw_current_channel_pattern,
            voltage_unit=targets.ibw_voltage_unit,
            current_unit=targets.ibw_current_unit,
            time_unit=targets.ibw_time_unit,
        )
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
                efel_settings=efel_settings.to_dict(),
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

        features_path = coord_root / EXTRACTED_FEATURES_FILENAME
        features_path.write_text(json.dumps(fitness_calculator_config.as_dict(), indent=2))

        return coord_root
