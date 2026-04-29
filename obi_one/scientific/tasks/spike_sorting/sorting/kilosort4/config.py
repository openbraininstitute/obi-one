"""ScanConfig for the aind-ephys-spikesort-kilosort4 capsule."""

from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from entitysdk import Client
from entitysdk.models import Entity, TaskConfig
from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import Field, NonNegativeInt

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.tasks.spike_sorting.sorting.kilosort4.blocks import (
    Kilosort4JobKwargs,
    Kilosort4Sorter,
)


class BlockGroup(StrEnum):
    """Spike-sorting block groups."""

    SETUP = "Setup"
    SORTING = "Sorting"


class AINDEPhysSpikesortKilosort4ScanConfig(ScanConfig):
    """ScanConfig wrapping the aind-ephys-spikesort-kilosort4 CLI.

    The capsule consumes ``preprocessed_<name>/`` directories + matching
    ``binary_<name>.json`` files from ``../data/`` (i.e. the output of the
    preprocessing stage) and writes one ``spikesorted_<name>/`` per recording
    to ``../results/``. ``initialize.preprocessing_output_path`` tells the
    OBI-side task where to seed those files from.
    """

    single_coord_class_name: ClassVar[str] = "AINDEPhysSpikesortKilosort4SingleConfig"
    name: ClassVar[str] = "AIND Ephys Spikesort Kilosort4"
    description: ClassVar[str] = (
        "Run the aind-ephys-spikesort-kilosort4 capsule on preprocessed ephys recordings."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: False,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP, BlockGroup.SORTING],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = None
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = None

    def input_entities(self, db_client: Client) -> list[Entity]:  # noqa: ARG002, PLR6301
        return []

    class Initialize(Block):
        """Top-level CLI / control parameters for the Kilosort4 capsule."""

        preprocessing_output_path: Path = Field(
            title="Preprocessing output path",
            description=(
                "Directory containing one or more ``preprocessed_<name>/`` directories"
                " and matching ``binary_<name>.json`` files (the output of"
                " AINDEPhysPreprocessingTask). Every preprocessed recording in this"
                " folder will be spike-sorted by the capsule."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )

        raise_if_fails: bool = Field(
            default=True,
            title="Raise if fails",
            description="Raise an error (instead of skipping) when a recording fails to sort.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )

        skip_motion_correction: bool = Field(
            default=False,
            title="Skip motion correction",
            description=(
                "Skip the capsule's post-sort motion-readout step. Set True when the"
                " upstream preprocessing (or sorter) didn't produce motion ops."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )

        min_drift_channels: NonNegativeInt = Field(
            default=64,
            title="Min drift channels",
            description="Minimum number of channels required to enable drift correction.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
        )

        clear_cache: bool = Field(
            default=False,
            title="Clear cache",
            description="Pass --clear-cache to the capsule.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )

        n_jobs: int = Field(
            default=1,
            title="n_jobs",
            description="Parallel job count (-1 for all cores).",
            json_schema_extra={SchemaKey.UI_HIDDEN: True},
        )

    initialize: Initialize = Field(
        title="Initialize",
        description="Top-level control parameters for the spike-sorting run.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    job_kwargs: Kilosort4JobKwargs = Field(
        default_factory=Kilosort4JobKwargs,
        title="Job kwargs",
        description="SpikeInterface job_kwargs.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    sorter: Kilosort4Sorter = Field(
        default_factory=Kilosort4Sorter,
        title="Sorter",
        description="Kilosort4 sorter parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SORTING,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    def create_campaign_entity_with_config(
        self,
        output_root: Path,  # noqa: ARG002
        multiple_value_parameters_dictionary: dict | None = None,  # noqa: ARG002
        db_client: Client = None,  # noqa: ARG002
    ) -> None:
        return None

    def create_campaign_generation_entity(
        self,
        generated: list,  # noqa: ARG002
        db_client: Client,  # noqa: ARG002
    ) -> None:
        return None


class AINDEPhysSpikesortKilosort4SingleConfig(
    AINDEPhysSpikesortKilosort4ScanConfig, SingleConfigMixin
):
    """Single-coordinate variant of :class:`AINDEPhysSpikesortKilosort4ScanConfig`."""

    def create_single_entity_with_config(
        self,
        campaign: TaskConfig,  # noqa: ARG002
        db_client: Client,  # noqa: ARG002
    ) -> None:
        return None

    def params_dict(self) -> dict:
        """Build the params.json payload the capsule expects.

        Top-level keys are forwarded straight to the capsule's run_capsule.py
        (which pops ``skip_motion_correction``, etc. when ``--params`` is given).
        """
        return {
            "job_kwargs": self.job_kwargs.to_dict(),
            "sorter": self.sorter.to_dict(),
            "skip_motion_correction": self.initialize.skip_motion_correction,
            "min_drift_channels": self.initialize.min_drift_channels,
        }
