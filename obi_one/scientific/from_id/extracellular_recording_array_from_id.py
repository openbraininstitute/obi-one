from entitysdk.models import SimulatableExtracellularRecordingArray

from obi_one.core.entity_from_id import DBType, EntityFromID


class SimulatableExtracellularRecordingArrayFromID(
    EntityFromID[SimulatableExtracellularRecordingArray]
):
    entitysdk_type: DBType[SimulatableExtracellularRecordingArray] = (
        SimulatableExtracellularRecordingArray
    )
