from typing import Union, Type
from obi.modeling.simulation.timestamps import Timestamps

def get_timestamps_union() -> Type[Union[Timestamps]]:
    subclasses = Timestamps.__subclasses__()
    return Union[tuple(subclasses)]

TimestampsUnion = get_timestamps_union()