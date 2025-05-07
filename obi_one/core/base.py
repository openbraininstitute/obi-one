from typing import Any
from pydantic import (
    BaseModel,
    ConfigDict,
    model_validator
)
from entitysdk.models.entity import Entity
from obi_one.core.serialization import entity_encoder

class OBIBaseModel(BaseModel):
    """
    Sets `type` fields for model_dump which are then used for desserialization.
    Sets encoder for EntitySDK Entities
    """

    type: str = ""
    model_config = ConfigDict(json_encoders={Entity: entity_encoder})

    @model_validator(mode="before")
    @classmethod
    def set_type(cls, data: Any) -> Any:
        if isinstance(data, dict) and "type" not in data:
            data["type"] = cls.__qualname__
        return data