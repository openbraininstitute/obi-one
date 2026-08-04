"""One pass that gives every unset block reference in a config a default.

A block reference field left as ``None`` means "whatever the task considers the obvious choice".
Which choice that is depends on the field's role rather than on the block holding it, so each field
declares its role once via ``SchemaKey.REFERENCE_TAG`` and the task supplies one reference per role.
Filling then needs no knowledge of any particular block type: walk the config, and wherever a tagged
field is ``None``, substitute the reference its tag maps to.

Roles are named by the task that resolves them -- see
``obi_one.scientific.unions_and_references.reference_tags.ReferenceTag`` for the simulation
generation set. Nothing here needs to know what a role means, only that fields sharing a tag share
a default, so tags are handled as plain strings.
"""

import logging
from collections.abc import Iterator, Mapping

from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference
from obi_one.core.schema import SchemaKey

L = logging.getLogger(__name__)


def _tagged_reference_fields(block: Block) -> Iterator[tuple[str, str]]:
    """The block's reference fields that declare what they mean when unset."""
    for name, field_info in type(block).model_fields.items():
        extra = field_info.json_schema_extra
        if isinstance(extra, dict) and SchemaKey.REFERENCE_TAG in extra:
            yield name, extra[SchemaKey.REFERENCE_TAG]


def _blocks_of(config: object) -> Iterator[Block]:
    """Every block the config holds, whether directly or inside a block dictionary."""
    for value in vars(config).values():
        if isinstance(value, Block):
            yield value
        elif isinstance(value, dict):
            yield from (item for item in value.values() if isinstance(item, Block))


def fill_none_references_in_config(
    config: object, defaults: Mapping[str, BlockReference]
) -> list[BlockReference]:
    """Replace every unset tagged block reference with the default for its role.

    A tag missing from ``defaults`` is left alone, which is how a block keeps a default only it can
    compute -- a spike time distribution spanning the stimulus's own duration, for instance.

    Args:
        config: The config whose blocks should be filled.
        defaults: The block reference to substitute for each role, keyed by reference tag.

    Returns:
        The defaults that were actually used, in the order they were first needed. Nothing is
        returned for a role no block left unset, so a caller registering these does not create
        blocks the config never refers to.
    """
    used: list[BlockReference] = []

    def use(default: BlockReference) -> BlockReference:
        if not any(default is seen for seen in used):
            used.append(default)
        return default

    for block in _blocks_of(config):
        for name, tag in _tagged_reference_fields(block):
            default = defaults.get(tag)
            if default is None:
                continue

            value = getattr(block, name, None)
            if value is None:
                L.debug(
                    "Filling %s.%s with the default for '%s'", block.__class__.__name__, name, tag
                )
                setattr(block, name, use(default))
            elif isinstance(value, tuple):
                # A combined neuron set holds its operands as (reference, set operation) pairs,
                # any of which may individually be unset.
                setattr(
                    block,
                    name,
                    tuple(
                        (use(default), operation) if reference is None else (reference, operation)
                        for reference, operation in value
                    ),
                )

    return used
