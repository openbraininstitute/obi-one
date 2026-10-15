from entitysdk.models import SimulatableExtracellularRecordingArray
from pydantic import Field

from obi_one.core.entity_from_id import EntityFromID


class SimulatableExtracellularRecordingArrayFromID(
    EntityFromID[SimulatableExtracellularRecordingArray]
):
    entitysdk_type: type[SimulatableExtracellularRecordingArray] = Field(
        default=SimulatableExtracellularRecordingArray, exclude=True, repr=False
    )
