import abc
from typing import Annotated, Any, ClassVar, Union, get_args, get_origin
    
from pydantic import Discriminator, Field

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block


class BlockReference(OBIBaseModel, abc.ABC):
    block_dict_name: str = Field(
        default="",
        description=(
            "Name of the root level dictionary which contains the block you are referencing. "
            "E.g. `neuron_sets` when referencing a block within the neuron_sets dictionary, "
            "or `timestamps` when referencing a block within the timestamps dictionary."
            "To reference a block at the root (i.e. a block that is not contained "
            "within a dictionary), block_dict_name should be an empty string. "
        ),
    )
    block_name: str = Field(description="Name of the block.")

    allowed_block_types: ClassVar[
        Annotated[type[OBIBaseModel] | tuple[type[OBIBaseModel], ...], Discriminator("type")]
    ] = None  # ty:ignore[invalid-assignment]

    _block: Any = None

    @staticmethod
    def get_class_names(tp):
        args = get_args(tp)
        return [t.__name__ for t in args] if args else [tp.__name__]

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
                f"Ensure: (1) The block is defined in the configuration, "
                f"(2) No typos in the block name, "
                f"(3) The 'block_dict_name' field matches the parent field name "
                f"containing the block dictionary. "
                f"Example: If referencing a block inside the 'neuron_sets' field, "
                f"set block_dict_name='neuron_sets'."
            )
            raise ValueError(msg)
        return self._block

    def has_block(self) -> bool:
        return self._block is not None

    @block.setter
    def block(self, value: Block) -> None:
        """Sets the block associated with this reference."""
        """
        Temp commented out to get working
        if not isinstance(value, self.allowed_block_types_union()):
            msg = f"Value must be of type {self.block_type.__name__}."  # ty:ignore[unresolved-attribute]
            raise TypeError(msg)
        """

        self._block = value
