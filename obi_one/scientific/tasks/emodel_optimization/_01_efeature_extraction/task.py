"""Task wrapper for the BluePyEModel feature-extraction step."""

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
    """Flatten the per-protocol targets dict into ``configure_targets`` rows."""
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
    """Set up the BluePyEModel working directory and run feature extraction.

    Steps performed in ``coordinate_output_root``:

    1. Copy the ephys data, morphologies, mechanisms, params, and recipes into
       a self-contained working directory.
    2. Compile the mod files via ``nrnivmodl`` (skipped if already compiled).
    3. Merge the extraction-related ``pipeline_settings`` overrides into
       ``./config/recipes.json``.
    4. Build ``files_metadata`` + ``targets_formated`` + ``protocols_rheobase``
       from the user-provided blocks (no separate ``targets.py`` required).
    5. ``chdir`` into the working directory and run
       ``configure_targets(pipeline.access_point)`` followed by
       ``pipeline.extract_efeatures()``.
    """

    name: ClassVar[str] = "EModel EFeature Extraction"
    description: ClassVar[str] = "Run BluePyEModel feature extraction on experimental ephys traces."

    config: EModelEFeatureExtractionSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> Path:
        from bluepyemodel.efeatures_extraction.targets_configurator import (  # noqa: PLC0415
            TargetsConfigurator,
        )
        from bluepyemodel.emodel_pipeline.emodel_pipeline import (  # noqa: PLC0415
            EModel_pipeline,
        )

        init = self.config.initialize
        targets = self.config.targets
        coord_root = Path(self.config.coordinate_output_root).resolve()

        # 1. Materialise the working directory.
        ephys_data_target = coord_root / "ephys_data" / Path(init.ephys_data_path).name
        _shared.copy_tree(Path(init.ephys_data_path).resolve(), ephys_data_target)
        _shared.copy_tree(Path(init.morphology_path).resolve(), coord_root / "morphologies")
        _shared.copy_tree(Path(init.mechanisms_path).resolve(), coord_root / "mechanisms")
        params_target = coord_root / "config" / "params" / Path(init.params_path).name
        _shared.copy_tree(Path(init.params_path).resolve(), params_target)

        # 2. Compile the mechanisms.
        _shared.compile_mechanisms(coord_root / "mechanisms")

        # 3. Recipes + pipeline_settings overrides.
        recipes = _shared.load_recipes(Path(init.recipes_path).resolve())
        recipes = _shared.update_pipeline_settings(
            recipes,
            emodel=init.emodel,
            overrides=self.config.extraction_settings.to_dict(self.config.efel_settings),
        )
        recipes_target = coord_root / "config" / "recipes.json"
        _shared.write_recipes(recipes, recipes_target)

        # 4. Build configure_targets() inputs from the blocks.
        ecodes_metadata_dict = {
            ecode: meta.to_dict() for ecode, meta in targets.ecodes_metadata.items()
        }
        files_metadata = _build_files_metadata(
            file_type=targets.file_type,
            ephys_data_path=ephys_data_target,
            ecodes_metadata_dict=ecodes_metadata_dict,
            voltage_pattern=targets.ibw_voltage_channel_pattern,
            current_pattern=targets.ibw_current_channel_pattern,
            voltage_unit=targets.ibw_voltage_unit,
            current_unit=targets.ibw_current_unit,
            time_unit=targets.ibw_time_unit,
        )
        targets_formatted = _build_targets_formatted(targets.targets)

        # 5. chdir into the working directory and let BluePyEModel resolve relative paths.
        with _shared.chdir(coord_root):
            pipeline = EModel_pipeline(
                emodel=init.emodel,
                etype=init.etype,
                mtype=init.mtype,
                ttype=init.ttype,
                species=init.species,
                brain_region=init.brain_region,
                recipes_path="./config/recipes.json",
                use_ipyparallel=init.use_ipyparallel,
                use_multiprocessing=init.use_multiprocessing,
            )

            configurator = TargetsConfigurator(pipeline.access_point)
            configurator.new_configuration(
                files=files_metadata,
                targets=targets_formatted,
                protocols_rheobase=list(targets.protocols_rheobase),
            )
            configurator.save_configuration()

            pipeline.extract_efeatures()

        return coord_root
