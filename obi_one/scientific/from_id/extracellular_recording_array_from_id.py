from entitysdk.models import SimulatableExtracellularRecordingArray

from obi_one.core.entity_from_id import EntityFromID


class SimulatableExtracellularRecordingArrayFromID(
    EntityFromID[SimulatableExtracellularRecordingArray]
):
    @classmethod
    def entitysdk_class(cls) -> type[SimulatableExtracellularRecordingArray]:
        return SimulatableExtracellularRecordingArray
