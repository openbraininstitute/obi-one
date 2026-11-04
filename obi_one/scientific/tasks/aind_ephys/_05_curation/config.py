"""Config for the curation stage of the AIND ephys pipeline."""

from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.tasks.aind_ephys._05_curation.blocks import (
    Bombcell,
    QCThresholds,
    Slay,
    UnitRefine,
)
from obi_one.scientific.tasks.aind_ephys.blocks import JobKwargs


class BlockGroup(StrEnum):
    """Curation block groups."""

    SETUP = "Setup"
    LABELLING = "Labelling"


class AINDEPhysCurationScanConfig(ScanConfig):
    """Label each postprocessed unit, flag the noise ones and propose merges.

    Port of https://github.com/AllenNeuralDynamics/aind-ephys-curation. Writes each recording's
    labels to ``unit_labels_<name>.csv``, the proposed merges to ``unit_merges_<name>.json``, and
    both as a spikeinterface curation to ``curation_<name>.json``.
    """

    name: ClassVar[str] = "AIND Ephys Curation"
    description: ClassVar[str] = "Labels sorted units and proposes merges."

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: False,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP, BlockGroup.LABELLING],
    }

    class Initialize(Block):
        postprocessing_output_path: Path = Field(
            title="Postprocessing output",
            description="Folder of the postprocessing stage's output.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        noise_strategy: Literal["bombcell", "unitrefine", "bombcell+unitrefine"] | None = Field(
            default="bombcell+unitrefine",
            title="Noise strategy",
            description=(
                "Which labels flag a unit as noise; 'bombcell+unitrefine' needs both to agree."
                " None flags no unit."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
        )

    initialize: Initialize = Field(
        title="Initialize",
        description="The postprocessed units and how noise is decided.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    job_kwargs: JobKwargs = Field(
        default_factory=JobKwargs,
        title="Job kwargs",
        description="SpikeInterface job kwargs.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    qc_thresholds: QCThresholds = Field(
        default_factory=QCThresholds,
        title="Default QC",
        description="Thresholds every unit passes or fails.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.LABELLING,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    unitrefine: UnitRefine = Field(
        default_factory=UnitRefine,
        title="UnitRefine",
        description="Machine-learning classifiers of noise, single and multi units.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.LABELLING,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    bombcell: Bombcell = Field(
        default_factory=Bombcell,
        title="Bombcell",
        description="Metric thresholds labelling units as good, MUA, noise or non-somatic.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.LABELLING,
            SchemaKey.GROUP_ORDER: 2,
        },
    )
    slay: Slay = Field(
        default_factory=Slay,
        title="SLAy",
        description="Search for pairs of neural units to merge.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.LABELLING,
            SchemaKey.GROUP_ORDER: 3,
        },
    )


class AINDEPhysCurationSingleConfig(AINDEPhysCurationScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`AINDEPhysCurationScanConfig`."""
