from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig

from obi_one.scientific.from_id.circuit_from_id import (
    CircuitFromID,
)

from pydantic import Field

class CombineEMCircuitsScanConfig(ScanConfig):

    class Initialize(Block):
        circuits: CircuitFromID = Field(
            title="Circuit",
            description="Circuit to simulate.",
            json_schema_extra={"ui_element": "model_selection_multi"},
        )


class CombineEMCircuitsSingleConfig(
    CombineEMCircuitsScanConfig, SingleConfigMixin
):
    """Only allows single values."""