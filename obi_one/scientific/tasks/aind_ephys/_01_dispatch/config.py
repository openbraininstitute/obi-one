"""Config for the dispatch stage of the AIND ephys pipeline."""

from pathlib import Path
from typing import ClassVar

from pydantic import Field

from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.tasks.aind_ephys._01_dispatch.blocks import JobDispatch


class AINDEPhysDispatchScanConfig(ScanConfig):
    """Split the raw recordings of an NWB file into the jobs the later stages process.

    Port of https://github.com/AllenNeuralDynamics/aind-ephys-job-dispatch for NWB input: one job
    per ElectricalSeries in ``acquisition``, split further by segment and probe group.
    """

    name: ClassVar[str] = "AIND Ephys Job Dispatch"
    description: ClassVar[str] = (
        "Splits the extracellular recordings of an NWB file into per-probe spike sorting jobs."
    )

    json_schema_extra_additions: ClassVar[dict] = {SchemaKey.UI_ENABLED: False}

    class Initialize(JobDispatch):
        nwb_path: Path = Field(
            title="NWB file",
            description="NWB file whose acquisition holds the raw extracellular recording.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )

    initialize: Initialize = Field(
        title="Initialize",
        description="The NWB input and how its recordings are split into jobs.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE},
    )


class AINDEPhysDispatchSingleConfig(AINDEPhysDispatchScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`AINDEPhysDispatchScanConfig`."""
