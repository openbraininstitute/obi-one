from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidatorFunctionWrapHandler, model_validator


def get_subclasses_recursive[T](cls: type[T]) -> list[type[T]]:
    """Returns all the subclasses of a given class."""
    subclasses = []
    for subclass in cls.__subclasses__():
        subclasses.append(subclass)
        subclasses.extend(get_subclasses_recursive(subclass))
    return subclasses


def get_subclass_recursive[T](cls: type[T], name: str) -> type[T]:
    return next(c for c in get_subclasses_recursive(cls=cls) if c.__qualname__ == name)


class OBIBaseModel(BaseModel):
    """Sets `type` fields for model_dump which are then used for desserialization.

    Sets encoder for EntitySDK Entities
    """

    type: str = ""

    model_config = ConfigDict(json_encoders={Path: str})

    @model_validator(mode="before")
    @classmethod
    def set_type(cls, data: Any) -> dict[str, Any]:
        """Automatically sets `type` when instantiated in Python if a dictionary."""
        if isinstance(data, dict) and "type" not in data:
            data["type"] = cls.__qualname__
        return data

    def __init_subclass__(cls, **kwargs) -> None:
        """Dynamically set the `type` field to the class name."""
        super().__init_subclass__(**kwargs)
        cls.__annotations__["type"] = Literal[cls.__qualname__]

    def __str__(self) -> str:
        """Return a string representation of the OBIBaseModel object."""
        return self.__repr__()


    @model_validator(mode="wrap")
    @classmethod
    def retrieve_type_on_deserialization(cls, 
                                        value: Any, 
                                        handler: ValidatorFunctionWrapHandler
                ) -> "OBIBaseModel":

        if isinstance(value, dict):

            # `sub_cls(**modified_value)` will trigger a recursion, and thus we need to
            # remove `type` from the dictionary before passing it to the subclass constructor
            
            modified_value = value.copy()
            sub_cls_name = modified_value.pop("type", None)
            
            if sub_cls_name is not None:

                sub_cls = get_subclass_recursive(
                    cls=OBIBaseModel,
                    name=sub_cls_name,  # , allow_same_class=True
                )

                return sub_cls(**modified_value)

            return handler(value)

        return handler(value)
