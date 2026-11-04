"""Curation stage: label each postprocessed unit, flag the noise ones and propose merges."""

import copy
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import entitysdk
import pandas as pd
import spikeinterface as si
import spikeinterface.curation as scur
from spikeinterface.core.core_tools import SIJsonEncoder
from spikeinterface.curation.curation_model import Curation

from obi_one.core.task import Task
from obi_one.scientific.tasks.aind_ephys._05_curation.config import AINDEPhysCurationSingleConfig
from obi_one.scientific.tasks.aind_ephys.utils import (
    global_job_kwargs,
    load_analyzer,
    stage_output_names,
    was_skipped,
    write_data_process,
)

L = logging.getLogger(__name__)

# Bombcell runs without up to this many of its metrics, as in the AIND pipeline.
MAX_MISSING_BOMBCELL_METRICS = 2
LIGHTWEIGHT_UNITREFINE_CLASSIFIERS = (
    "SpikeInterface/UnitRefine_noise_neural_classifier_lightweight",
    "SpikeInterface/UnitRefine_sua_mua_classifier_lightweight",
)
QUALITY_LABEL_DEFINITIONS = {
    "quality": {"label_options": ["good", "MUA", "noise"], "exclusive": True}
}


def unitrefine_classifiers(
    noise_neural: str, sua_mua: str | None, metric_names: set[str]
) -> tuple[str, str | None] | None:
    """The configured classifiers, else the lightweight ones, if the metrics they need exist."""
    for candidate in ((noise_neural, sua_mua), LIGHTWEIGHT_UNITREFINE_CLASSIFIERS):
        required = set(scur.get_required_metrics_from_model(repo_id=candidate[0], trust_model=True))
        if candidate[1] is not None:
            required |= set(
                scur.get_required_metrics_from_model(repo_id=candidate[1], trust_model=True)
            )
        missing = required - metric_names
        if not missing:
            return candidate
        L.info("UnitRefine %s lacks metrics %s.", candidate[0], sorted(missing))
    return None


def bombcell_thresholds(thresholds: dict, metric_names: set[str]) -> dict | None:
    """The thresholds without metrics that are missing, or None if too many are."""
    missing = {
        metric for metric_bounds in thresholds.values() for metric in metric_bounds
    } - metric_names
    if len(missing) >= MAX_MISSING_BOMBCELL_METRICS:
        L.info("Skipping Bombcell, which lacks metrics %s.", sorted(missing))
        return None
    kept = copy.deepcopy(thresholds)
    for metric_bounds in kept.values():
        for metric in missing:
            metric_bounds.pop(metric, None)
    return kept


def noise_mask(labels: pd.DataFrame, strategy: str | None) -> pd.Series:
    """Which units the strategy flags as noise, using only the labels that were computed."""
    voters = [] if strategy is None else strategy.split("+")
    voters = [voter for voter in voters if f"{voter}_label" in labels.columns]
    if not voters:
        return pd.Series(data=False, index=labels.index)
    mask = pd.Series(data=True, index=labels.index)
    for voter in voters:
        mask &= labels[f"{voter}_label"] == "noise"
    return mask


class AINDEPhysCurationTask(Task):
    """Curate every postprocessed recording into this config's output folder."""

    name: ClassVar[str] = "AIND Ephys Curation"
    description: ClassVar[str] = "Labels sorted units and proposes merges."

    config: AINDEPhysCurationSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # ruff: ignore[unused-method-argument]  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: str | None = None,  # ruff: ignore[unused-method-argument]
    ) -> Path:
        output_folder = Path(self.config.coordinate_output_root)
        output_folder.mkdir(parents=True, exist_ok=True)
        source = Path(self.config.initialize.postprocessing_output_path)
        names = stage_output_names(source, "postprocessed_", ".zarr")
        if not names:
            msg = f"No postprocessed_<name>.zarr in {source}; run the postprocessing stage first."
            raise FileNotFoundError(msg)
        with global_job_kwargs(self.config.job_kwargs.to_dict()):
            for name in names:
                analyzer_folder = source / f"postprocessed_{name}.zarr"
                if was_skipped(analyzer_folder):
                    L.info("Skipping %s, which postprocessing skipped.", name)
                    continue
                self.curate(load_analyzer(analyzer_folder), name, output_folder)
        return output_folder

    def label(self, analyzer: si.SortingAnalyzer, notes: list[str]) -> pd.DataFrame:
        """Every label the configured methods give each unit."""
        metrics = analyzer.get_metrics_extension_data()
        metric_names = set(metrics.columns)
        labels = []

        qc_thresholds = self.config.qc_thresholds.to_dict()
        if set(qc_thresholds) <= metric_names:
            labels.append(
                scur.threshold_metrics_label_units(
                    metrics,
                    thresholds=qc_thresholds,
                    pass_label=True,  # ty:ignore[invalid-argument-type]
                    fail_label=False,  # ty:ignore[invalid-argument-type]
                    column_name="default_qc",
                )
            )
        else:
            notes.append("Default QC skipped: its metrics are missing.")

        unitrefine = self.config.unitrefine
        classifiers = None
        if unitrefine.noise_neural_classifier is not None:
            classifiers = unitrefine_classifiers(
                unitrefine.noise_neural_classifier, unitrefine.sua_mua_classifier, metric_names
            )
        if classifiers is not None:
            labels.append(
                scur.unitrefine_label_units(
                    sorting_analyzer=analyzer,
                    noise_neural_classifier=classifiers[0],
                    sua_mua_classifier=classifiers[1],
                )
            )
            notes.append(f"UnitRefine with {classifiers[0]} and {classifiers[1]}.")
        else:
            notes.append("UnitRefine skipped.")

        thresholds = bombcell_thresholds(self.config.bombcell.thresholds, metric_names)
        if thresholds is not None:
            labels.append(scur.bombcell_label_units(analyzer, thresholds=thresholds))
        else:
            notes.append("Bombcell skipped: too many of its metrics are missing.")

        if not labels:
            return pd.DataFrame(index=pd.Index(analyzer.unit_ids, name="unit_id"))
        return pd.concat(labels, axis=1).rename_axis("unit_id")

    def curate(self, analyzer: si.SortingAnalyzer, name: str, output_folder: Path) -> None:
        """Curate one postprocessed recording."""
        start = datetime.now(UTC)
        notes: list[str] = []
        labels = self.label(analyzer, notes)
        labels.to_csv(output_folder / f"unit_labels_{name}.csv")

        noise = noise_mask(labels, self.config.initialize.noise_strategy)
        noise_units = labels.index[noise].tolist()
        neural_units = labels.index[~noise].tolist()
        try:
            merges = scur.compute_merge_unit_groups(
                analyzer.select_units(unit_ids=neural_units),
                preset="slay",
                steps_params=self.config.slay.to_dict(),
            )
        except Exception as error:  # ruff: ignore[blind-except]
            L.warning("SLAy failed on %s: %s", name, error)
            notes.append(f"SLAy failed: {error}")
            merges = []
        merge_groups = [[*group] for group in merges]
        (output_folder / f"unit_merges_{name}.json").write_text(
            json.dumps(merge_groups, cls=SIJsonEncoder), encoding="utf-8"
        )

        curation = Curation(
            format_version="2",
            unit_ids=analyzer.unit_ids.tolist(),
            label_definitions=QUALITY_LABEL_DEFINITIONS,
            manual_labels=[{"unit_id": unit, "quality": ["noise"]} for unit in noise_units],
            removed=noise_units,
            merges=[{"unit_ids": group} for group in merge_groups],
            splits=[],
        )
        (output_folder / f"curation_{name}.json").write_text(
            curation.model_dump_json(indent=4), encoding="utf-8"
        )
        L.info("Curated %s: %d noise units, %d merges.", name, len(noise_units), len(merges))

        write_data_process(
            output_folder / f"data_process_curation_{name}.json",
            name="Ephys curation",
            parameters=self.config.model_dump(
                mode="json",
                include={"initialize", "qc_thresholds", "unitrefine", "bombcell", "slay"},
            ),
            outputs={
                "total_units": len(analyzer.unit_ids),
                "noise_units": len(noise_units),
                "merges": len(merges),
                **{
                    f"{column}_{value}": int(count)
                    for column in labels.columns
                    if column.endswith("_label") or column == "default_qc"
                    for value, count in labels[column].value_counts().items()
                },
            },
            notes="\n".join(notes),
            start=start,
        )
