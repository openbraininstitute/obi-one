from typing import Any, Dict, List, Type, TypeVar, Literal
from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    model_validator,
    ValidatorFunctionWrapHandler,
)
from entitysdk.models.entity import Entity


def entity_encoder(obj: Any) -> Dict[str, str]:
    """
    Encode an Entity into a JSON-serializable dictionary.
    """
    cls_name = obj.__class__.__name__
    if issubclass(obj.__class__, Entity) and "FromID" not in cls_name:
        return {"type": f"{cls_name}FromID", "id_str": str(obj.id)}
    elif "FromID" in cls_name:
        return {"type": cls_name, "id_str": str(obj.id)}
    raise TypeError(f"Object of type {cls_name} is not JSON serializable")


"""
To do: 
- add json_encoder for adding type?
- add json_decoder for from_id as not a subclass of Entity anymore
"""


class OBIBaseModel(BaseModel):
    """
    Base model for OBI entities. Automatically sets and resolves `type` fields during
    (de)serialization to handle polymorphic models.
    """

    type: str = ""
    model_config = ConfigDict(json_encoders={Entity: entity_encoder})

    @model_validator(mode="before")
    @classmethod
    def set_type(cls, data: Any) -> Any:
        """Set the `type` field to the class name if not provided."""
        if isinstance(data, dict) and "type" not in data:
            data["type"] = cls.__qualname__
        return data

    # def __init_subclass__(cls, **kwargs):
    #     """Force `type` to match the subclass's qualified name."""
    #     super().__init_subclass__(**kwargs)
    #     cls.__annotations__["type"] = Literal[cls.__qualname__]

    # def __str__(self) -> str:
    #     return self.__repr__()

    # @model_validator(mode="wrap")
    # @classmethod
    # def retrieve_type_on_deserialization(
    #     cls, value: Any, handler: ValidatorFunctionWrapHandler
    # ) -> 'OBIBaseModel':
    #     """
    #     Dynamically determine and instantiate the correct subclass based on the `type` field.
    #     """
    #     if isinstance(value, dict):
    #         modified_value = value.copy()
    #         sub_cls_name = modified_value.pop("type", None)
    #         if sub_cls_name:
    #             sub_cls = get_subclass_recursive(cls=OBIBaseModel, name=sub_cls_name, allow_same_class=True)
    #             return sub_cls(**modified_value)
    #     return handler(value)