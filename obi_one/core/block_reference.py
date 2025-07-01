from obi_one.core.block import Block
from obi_one.core.base import OBIBaseModel


from typing import Union, ClassVar, get_args, Any, Literal
from pydantic import Field
import abc
class BlockReference(OBIBaseModel, abc.ABC):
    block_dict_name: str = Field(default="")
    block_name: str = Field()

    allowed_block_types: ClassVar[Any] = None
    
    _block: Any = None

    @classmethod
    def allowed_block_type_names(cls, allowed_block_types):
        if allowed_block_types is None:
            return []
        return [t.__name__ for t in get_args(allowed_block_types)]

    class Config:
        @staticmethod
        def json_schema_extra(schema: dict, model) -> None:
            # Dynamically get allowed_block_types from subclass
            allowed_block_types = getattr(model, 'allowed_block_types', [])
            schema['allowed_block_types'] = [t.__name__ for t in get_args(allowed_block_types)]
            schema['is_block_reference'] = True

    @property
    def block(self) -> Block:
        """Returns the block associated with this reference."""
        if self._block is None:
            raise ValueError("Block has not been set.")
        return self._block

    def has_block(self) -> bool:
        return self._block is not None

    @block.setter
    def block(self, value: Block) -> None:
        """Sets the block associated with this reference."""
        if not isinstance(value, self.allowed_block_types):
            raise TypeError(f"Value must be of type {self.block_type.__name__}.")
        self._block = value

