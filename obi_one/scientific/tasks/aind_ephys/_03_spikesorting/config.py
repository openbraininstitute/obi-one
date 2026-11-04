"""Config for the spike sorting stage of the AIND ephys pipeline."""

from enum import StrEnum
from pathlib import Path
from typing import ClassVar

import entitysdk
from entitysdk.models.entity import Entity
from entitysdk.types import TaskResultType
from pydantic import Field, NonNegativeInt

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID
from obi_one.scientific.library.info_scan_config.config import (
    BlockGroup as InfoBlockGroup,
    InfoScanConfig,
)
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.blocks import (
    SorterUnion,
    SpykingCircus2Sorter,
)
from obi_one.scientific.tasks.aind_ephys.blocks import JobKwargs


class BlockGroup(StrEnum):
    """Spike sorting block groups."""

    SORTING = "Sorting"


class AINDEPhysSpikeSortingScanConfig(InfoScanConfig):
    """Sort the spikes of each preprocessed recording.

    Port of the AIND pipeline's sorter steps (aind-ephys-spikesort-kilosort4, -spykingcircus2 and
    -lupin), which differ only in the sorter they run. Writes each recording's sorting to
    ``spikesorted_<name>/``, and Kilosort4's motion estimate to ``spikesortedmotion_<name>/``.
    """

    name: ClassVar[str] = "AIND Ephys Spike Sorting"
    description: ClassVar[str] = "Sorts the spikes of preprocessed extracellular recordings."

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [InfoBlockGroup.SETUP_BLOCK_GROUP, BlockGroup.SORTING],
    }

    class Initialize(Block):
        preprocessing_result: TaskResultFromID | None = Field(
            default=None,
            title="Preprocessing result",
            description="Result of the preprocessing stage, whose recordings are sorted.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.TASK_RESULT_SELECTOR,
                SchemaKey.TASK_RESULT_TYPE: TaskResultType.aind_ephys_preprocessing__result,
            },
        )
        preprocessing_output_path: Path | None = Field(
            default=None,
            title="Preprocessing output",
            description=(
                "Local folder of the preprocessing stage's output, instead of a result entity."
                " With neither, a toy recording is made and preprocessed on the fly."
            ),
            json_schema_extra={SchemaKey.UI_HIDDEN: True},
        )
        skip_motion_correction: bool = Field(
            default=False,
            title="Skip motion correction",
            description="Turn off the sorter's own motion correction.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )
        min_drift_channels: NonNegativeInt = Field(
            default=96,
            title="Minimum drift channels",
            description="Recordings with fewer channels are sorted without motion correction.",
            json_schema_extra={SchemaKey.UI_HIDDEN: True},
        )
        raise_if_fails: bool = Field(
            default=True,
            title="Raise if sorting fails",
            description="Whether a failed sorting stops the task, or skips the recording.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )

    initialize: Initialize = Field(
        default_factory=Initialize,
        title="Initialize",
        description="The preprocessed recordings and the settings every sorter shares.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: InfoBlockGroup.SETUP_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    job_kwargs: JobKwargs = Field(
        default=JobKwargs(),
        title="Job kwargs",
        description="SpikeInterface job kwargs.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    sorter: SorterUnion = Field(
        default_factory=SpykingCircus2Sorter,
        title="Sorter",
        description="The spike sorter and its parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_UNION,
            SchemaKey.GROUP: BlockGroup.SORTING,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    def input_entities(self, db_client: entitysdk.client.Client) -> list[Entity]:
        """The preprocessing result, recorded as the input of the task config."""
        if self.initialize.preprocessing_result is None:
            return []
        return [self.initialize.preprocessing_result.entity(db_client=db_client)]


class AINDEPhysSpikeSortingSingleConfig(AINDEPhysSpikeSortingScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`AINDEPhysSpikeSortingScanConfig`."""
