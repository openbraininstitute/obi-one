from typing import Union, Type
from obi.modeling.core.base import OBIBaseModel
from obi.modeling.core.single import SingleCoordinateMixin

def get_all_subclasses(cls):
    subclasses = set(cls.__subclasses__())
    subclasses = set(filter(lambda _cls: SingleCoordinateMixin not in _cls.__bases__, subclasses))  # Don't include subclasses with single coordinates
    for subclass in subclasses.copy():
        subclasses.update(get_all_subclasses(subclass))
    return subclasses

def subclass_union(block_parent_class) -> Type[Union[OBIBaseModel]]:
    subclasses = get_all_subclasses(block_parent_class)
    return Union[tuple(subclasses)]