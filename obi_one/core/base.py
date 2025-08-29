from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator


class OBIBaseModel(BaseModel):
    """Sets `type` fields for model_dump which are then used for desserialization.

    Sets encoder for EntitySDK Entities
    """

    model_config = ConfigDict(json_encoders={Path: str}, discriminator="type", extra="forbid")

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
