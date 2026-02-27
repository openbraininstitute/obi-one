import abc
from typing import Annotated, Any, ClassVar, get_args

from pydantic import Discriminator, Field

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block


class BlockReference(OBIBaseModel, abc.ABC):
    block_dict_name: str = Field(default="")
    block_name: str = Field()

    allowed_block_types: ClassVar[
        Annotated[type[OBIBaseModel] | tuple[type[OBIBaseModel], ...], Discriminator("type")]
    ] = None

    _block: Any = None

    @classmethod
    def allowed_block_types_union(
        cls,
    ) -> type[OBIBaseModel] | tuple[type[OBIBaseModel], ...]:
        """Returns the union type of allowed block types."""
        return get_args(cls.allowed_block_types)[0]

    @property
    def block(self) -> Block:
        """Returns the block associated with this reference."""
        if self._block is None:
            msg = (
                f"Block '{self.block_name}' not found in '{self.block_dict_name}'. "
                f"Define the block before referencing it, or check for typos in the block name."
            )
            raise ValueError(msg)
        return self._block

    def has_block(self) -> bool:
        return self._block is not None

    @block.setter
    def block(self, value: Block) -> None:
        """Sets the block associated with this reference."""
        if not isinstance(value, self.allowed_block_types_union()):
            msg = f"Value must be of type {self.block_type.__name__}."
            raise TypeError(msg)

        self._block = value
