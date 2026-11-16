import abc
from collections.abc import Iterable, Iterator, Mapping
from typing import Annotated, Any, ClassVar, get_args

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
    def get_class_names(tp: Any) -> list[str]:
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
        """The block associated with this reference."""
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
        # NOTE: Do NOT add an isinstance check here to reject a block whose type is not in
        # ``allowed_block_types_union()``. References are built from client payloads that omit
        # ``type``, so pydantic stamps the first union member (often the wrong one), and configs
        # already persisted in entitycore may carry that wrong ``type``. Rejecting a type/block
        # mismatch here would break loading those stored configs. Instead, the reference ``type``
        # is corrected to match the resolved block's variant in
        # ``ScanConfig._correct_reference_type`` (obi_one/core/scan_config.py), which heals both
        # new payloads and already-stored configs.
        self._block = value


def _references_in(values: Iterable[object]) -> Iterator[BlockReference]:
    """The block references in ``values``, including those inside tuples and lists."""
    for value in values:
        if isinstance(value, BlockReference):
            yield value
        elif isinstance(value, (tuple, list)):
            yield from _references_in(value)


def resolve_block_references(
    block: Block, blocks: Mapping[str, Block], block_dict_name: str
) -> None:
    """Name ``blocks`` by their keys and point the references reached from ``block`` at them.

    What a ScanConfig does for its own dictionaries, for a block used outside one: an
    endpoint given a combined neuron set plus the named neuron sets it references. Only the
    blocks reached from ``block`` are resolved, so an unrelated broken entry does not fail.

    Raises:
        ValueError: A reference names another dictionary or a block not in ``blocks``.
    """
    for name, named_block in blocks.items():
        named_block.set_block_name(name)
    pending, seen = [block], set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        for reference in _references_in(current.__dict__.values()):
            target = blocks.get(reference.block_name)
            if reference.block_dict_name != block_dict_name or target is None:
                msg = (
                    f"Block '{reference.block_name}' in '{reference.block_dict_name}' is "
                    f"referenced but was not sent: add it to '{block_dict_name}'."
                )
                raise ValueError(msg)
            reference.block = target
            pending.append(target)
