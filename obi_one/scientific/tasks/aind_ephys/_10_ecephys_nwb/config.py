"""ScanConfig for the aind-ecephys-nwb capsule."""

from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal

from entitysdk import Client
from entitysdk.models import Entity, TaskConfig
from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import Field, PositiveFloat, PositiveInt

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.core.units import Units


class BlockGroup(StrEnum):
    """Ecephys-NWB block groups."""

    SETUP = "Setup"
    LFP = "LFP"


class AINDEcephysNWBScanConfig(ScanConfig):
    """ScanConfig wrapping the aind-ecephys-nwb CLI.

    The capsule reads ``job_*.json`` from the dispatch stage to write the raw
    ``ElectricalSeries`` to one NWB file per (block, recording).
    """

    single_coord_class_name: ClassVar[str] = "AINDEcephysNWBSingleConfig"
    name: ClassVar[str] = "AIND Ecephys NWB Export"
    description: ClassVar[str] = (
        "Export raw + LFP ElectricalSeries to NWB via the aind-ecephys-nwb capsule."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: False,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP, BlockGroup.LFP],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = None
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = None

    def input_entities(self, db_client: Client) -> list[Entity]:  # noqa: ARG002, PLR6301
        return []

    class Initialize(Block):
        """Top-level CLI / control parameters for the NWB-export capsule."""

        dispatch_output_path: Path = Field(
            title="Dispatch output path",
            description="Directory containing ``job_*.json`` from the dispatch stage.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )

        backend: Literal["hdf5", "zarr"] = Field(
            default="hdf5",
            title="NWB backend",
            description="NWB IO backend.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
        )
        write_raw: bool = Field(
            default=True,
            title="Write raw",
            description="Add the raw ElectricalSeries to the NWB.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )
        skip_lfp: bool = Field(
            default=True,
            title="Skip LFP",
            description=(
                "Skip writing the LFP ElectricalSeries. Recommended on toy data"
                " (the capsule's hard-coded LFP ``freq_min=0.5`` trips newer"
                " spikeinterface's highpass-filter check)."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )
        stub: bool = Field(
            default=False,
            title="Stub",
            description="Truncate the recording to ``stub_seconds`` for testing.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )
        stub_seconds: PositiveFloat = Field(
            default=10.0,
            title="Stub seconds",
            description="Stub-mode recording duration.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
                SchemaKey.UNITS: Units.SECONDS,
            },
        )

    initialize: Initialize = Field(
        title="Initialize",
        description="Top-level control parameters for the NWB-export run.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    class LFP(Block):
        """LFP-extraction parameters (used when ``skip_lfp`` is False)."""

        temporal_factor: PositiveInt | list[PositiveInt] = Field(
            default=2,
            title="Temporal subsampling factor",
            description="Temporal subsampling factor for the LFP signal.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
        )
        spatial_factor: PositiveInt | list[PositiveInt] = Field(
            default=4,
            title="Spatial subsampling factor",
            description="Spatial subsampling factor for the LFP signal.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
        )
        highpass_freq_min: PositiveFloat | list[PositiveFloat] = Field(
            default=0.1,
            title="Highpass freq_min",
            description="Highpass cutoff (Hz) for the LFP filter.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
                SchemaKey.UNITS: Units.HERTZ,
            },
        )

    lfp: LFP = Field(
        default_factory=LFP,
        title="LFP",
        description="LFP-extraction parameters (only used when skip_lfp=False).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.LFP,
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


class AINDEcephysNWBSingleConfig(AINDEcephysNWBScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`AINDEcephysNWBScanConfig`."""

    def create_single_entity_with_config(
        self,
        campaign: TaskConfig,  # noqa: ARG002
        db_client: Client,  # noqa: ARG002
    ) -> None:
        return None
