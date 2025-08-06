import abc
from typing import Annotated, Any, ClassVar, get_args, get_origin

from pydantic import Field

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block


class BlockReference(OBIBaseModel, abc.ABC):
    block_dict_name: str = Field(default="")
    block_name: str = Field()

    allowed_block_types: ClassVar[Any] = None

    _block: Any = None

    @classmethod
    def allowed_block_type_names(cls, allowed_block_types: Any) -> list:
        if allowed_block_types is None:
            return []
        return [t.__name__ for t in get_args(allowed_block_types)]

    class Config:
        @staticmethod
        def json_schema_extra(schema: dict, model: "BlockReference") -> None:
            # Dynamically get allowed_block_types from subclass
            allowed_block_types = getattr(model, "allowed_block_types", [])
            schema["allowed_block_types"] = [t.__name__ for t in get_args(allowed_block_types)]
            schema["is_block_reference"] = True

    @property
    def block(self) -> Block:
        """Returns the block associated with this reference."""
        if self._block is None:
            msg = "Block has not been set."
            raise ValueError(msg)
        return self._block

    def has_block(self) -> bool:
        return self._block is not None

    @block.setter
    def block(self, value: Block) -> None:
        """Sets the block associated with this reference."""
        # check if union is annotated
        if get_origin(self.allowed_block_types) is Annotated:
            args = get_args(self.allowed_block_types)
            union = args[0]
        else:
            union = self.allowed_block_types

        if not isinstance(value, union):
            msg = f"Value must be of type {self.block_type.__name__}."
            raise TypeError(msg)

        self._block = value
