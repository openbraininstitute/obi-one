# """
# Adapted from https://github.com/pydantic/pydantic/issues/7366
# """


from pydantic import BaseModel, model_serializer, model_validator, ValidatorFunctionWrapHandler
from typing import Any, Dict, List, Type, TypeVar

T = TypeVar('T')

def get_subclasses_recursive(cls: Type[T]) -> List[Type[T]]:
    """
    Returns all the subclasses of a given class.
    """
    subclasses = []
    for subclass in cls.__subclasses__():
        subclasses.append(subclass)
        subclasses.extend(get_subclasses_recursive(subclass))
    return subclasses


def get_subclass_recursive(cls: Type[T], name: str, allow_same_class: bool = False) -> Type[T]:
    # I oversimplified this to keep it short (there are checks for 0 or more than 1 subclasses
    # and we did not even use parameter `allow_same_class` to also match the parent class) 
    return next(c for c in get_subclasses_recursive(cls=cls) if c.__qualname__ == name)

from typing import Literal
from pydantic import Field, BaseModel, model_validator
class OBIBaseModel(BaseModel):

    type: str = ""

    @model_validator(mode="before")
    @classmethod
    def set_type(cls, data):
        """Automatically sets `type` when instantiated in Python."""
        if isinstance(data, dict) and "type" not in data:
            data["type"] = cls.__qualname__
        return data

    def __init_subclass__(cls, **kwargs):
        """Dynamically set the `type` field to the class name"""
        super().__init_subclass__(**kwargs)
        cls.__annotations__["type"] = Literal[cls.__qualname__]

    def __str__(self):
        return self.__repr__()

    @model_validator(mode='wrap')  # noqa  # the decorator position is correct
    @classmethod
    def retrieve_type_on_deserialization(cls, value: Any,
                                         handler: ValidatorFunctionWrapHandler) -> 'OBIBaseModel':
        if isinstance(value, dict):
            # WARNING: we do not want to modify `value` which will come from the outer scope
            # WARNING2: `sub_cls(**modified_value)` will trigger a recursion, and thus we need to remove `obi_class`
            modified_value = value.copy()
            sub_cls_name = modified_value.pop('type', None)
            if sub_cls_name is not None:
                sub_cls = get_subclass_recursive(cls=OBIBaseModel, name=sub_cls_name, allow_same_class=True)
                return sub_cls(**modified_value)
            else:
                return handler(value)
        return handler(value)