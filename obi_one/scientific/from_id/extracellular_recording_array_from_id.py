from entitysdk.models import SimulatableExtracellularRecordingArray

from obi_one.core.entity_from_id import EntityFromID


class SimulatableExtracellularRecordingArrayFromID(
    EntityFromID[SimulatableExtracellularRecordingArray]
):
    _entitysdk_type: type[SimulatableExtracellularRecordingArray] = (
        SimulatableExtracellularRecordingArray
    )
