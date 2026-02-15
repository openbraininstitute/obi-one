from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, model_validator


class OBIBaseModel(BaseModel):
    """Sets `type` fields for model_dump which are then used for desserialization.

    Sets encoder for EntitySDK Entities
    """

    model_config = ConfigDict(discriminator="type", extra="forbid", json_schema_extra={})

    title: ClassVar[str | None] = None  # Optional: subclasses can override
    json_schema_extra_additions: ClassVar[dict] = {}

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
        cls.type = cls.__qualname__

        # Use the subclass-provided title, or fall back to the class name
        cls.model_config.update({"title": cls.title or cls.__name__})

        cls.model_config["json_schema_extra"].update(cls.json_schema_extra_additions)

    def __str__(self) -> str:
        """Return a string representation of the OBIBaseModel object."""
        return self.__repr__()
