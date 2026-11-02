"""ScanConfig for the aind-ephys-qc-collector capsule."""

from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin


class BlockGroup(StrEnum):
    """QC-collector block groups."""

    SETUP = "Setup"


class AINDEPhysQCCollectorScanConfig(ScanConfig):
    """ScanConfig wrapping the aind-ephys-qc-collector CLI.

    The capsule reads every ``quality_control_*.json`` (and matching figure
    folder) from ``../data/`` and aggregates them into a single
    ``quality_control.json`` plus a flat ``quality_control/<probe>/`` figure
    tree in ``../results/``.
    """

    name: ClassVar[str] = "AIND Ephys QC Collector"
    description: ClassVar[str] = (
        "Aggregate per-recording QC documents into a single QualityControl document."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: False,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP],
    }

    class Initialize(Block):
        """Top-level CLI / control parameters for the QC-collector capsule."""

        qc_output_path: Path = Field(
            title="QC output path",
            description=(
                "Directory containing per-recording ``quality_control_<name>.json``"
                " files and matching ``quality_control_<name>/`` figure folders"
                " (output of AINDEPhysProcessingQCTask)."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )

    initialize: Initialize = Field(
        title="Initialize",
        description="Top-level control parameters for the QC-collector run.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class AINDEPhysQCCollectorSingleConfig(AINDEPhysQCCollectorScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`AINDEPhysQCCollectorScanConfig`."""
