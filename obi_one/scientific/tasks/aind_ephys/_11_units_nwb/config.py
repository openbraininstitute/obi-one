"""ScanConfig for the aind-units-nwb capsule."""

from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from entitysdk import Client
from entitysdk.models import Entity, TaskConfig
from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import Field, PositiveInt

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin


class BlockGroup(StrEnum):
    """Units-NWB block groups."""

    SETUP = "Setup"


class AINDUnitsNWBScanConfig(ScanConfig):
    """ScanConfig wrapping the aind-units-nwb CLI.

    The capsule reads an existing base NWB plus the results-collector layout
    (``preprocessed/``, ``curated/``, ``spikesorted/``, ``postprocessed/``)
    and the dispatch ``job_*.json``, then appends a ``units`` table populated
    from the curated sorting (UUIDs, depths, amplitudes) and per-unit
    ``waveform_mean`` / ``waveform_sd``.
    """

    single_coord_class_name: ClassVar[str] = "AINDUnitsNWBSingleConfig"
    name: ClassVar[str] = "AIND Units NWB Export"
    description: ClassVar[str] = (
        "Append the curated sorting + waveforms to a base NWB via the aind-units-nwb capsule."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: False,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = None
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = None

    def input_entities(self, db_client: Client) -> list[Entity]:  # noqa: ARG002, PLR6301
        return []

    class Initialize(Block):
        """Top-level CLI / control parameters for the units-NWB capsule."""

        nwb_input_path: Path = Field(
            title="NWB input path",
            description=(
                "Directory containing the base ``.nwb`` (or ``.nwb.zarr``)"
                " produced by AINDEcephysNWBTask."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        collected_output_path: Path = Field(
            title="Collected output path",
            description=(
                "Directory containing the results-collector layout"
                " (``preprocessed/``, ``curated/``, ``spikesorted/``, ``postprocessed/``)."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        dispatch_output_path: Path = Field(
            title="Dispatch output path",
            description="Directory containing ``job_*.json`` from the dispatch stage.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )

        stub: bool = Field(
            default=False,
            title="Stub",
            description="Limit to ``stub_units`` units for fast tests.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )
        stub_units: PositiveInt = Field(
            default=10,
            title="Stub units",
            description="Number of units kept when ``stub`` is True.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
        )

        session_name: str = Field(
            default="ecephys_toy",
            title="Session name",
            description="Synthetic ``ecephys_*`` folder name (must start with 'ecephys').",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        subject_id: str = Field(
            default="000000",
            title="Subject id",
            description="Subject id written into the synthetic ``subject.json``.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )

    initialize: Initialize = Field(
        title="Initialize",
        description="Top-level control parameters for the units-NWB run.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
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


class AINDUnitsNWBSingleConfig(AINDUnitsNWBScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`AINDUnitsNWBScanConfig`."""

    def create_single_entity_with_config(
        self,
        campaign: TaskConfig,  # noqa: ARG002
        db_client: Client,  # noqa: ARG002
    ) -> None:
        return None
