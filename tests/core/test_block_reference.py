from typing import Annotated, Any, ClassVar

import pytest
from pydantic import Discriminator

from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference


class BlockA(Block):
    val: int = 1


class BlockB(Block):
    val: str = "b"


class UnrelatedBlock(Block):
    val: float = 0.0


TestUnion = Annotated[BlockA | BlockB, Discriminator("type")]


class TestReference(BlockReference):
    allowed_block_types: ClassVar[Any] = TestUnion


class SingleTypeReference(BlockReference):
    allowed_block_types: ClassVar[Any] = Annotated[BlockA, Discriminator("type")]


class TestBlockReferenceCreation:
    def test_creation_with_fields(self):
        ref = TestReference(block_dict_name="neuron_sets", block_name="ns_1")
        assert ref.block_dict_name == "neuron_sets"
        assert ref.block_name == "ns_1"

    def test_default_block_dict_name(self):
        ref = TestReference(block_name="test")
        assert ref.block_dict_name == ""


class TestBlockReferenceBlock:
    def test_block_not_set_raises(self):
        ref = TestReference(block_dict_name="cat", block_name="my_block")
        with pytest.raises(ValueError, match="Block 'my_block' not found"):
            _ = ref.block

    def test_has_block_false_initially(self):
        ref = TestReference(block_name="test")
        assert ref.has_block() is False

    def test_set_block_correct_type(self):
        ref = TestReference(block_name="test")
        block = BlockA(val=42)
        ref.block = block
        assert ref.block is block
        assert ref.has_block() is True

    def test_set_block_second_union_type(self):
        ref = TestReference(block_name="test")
        block = BlockB(val="hello")
        ref.block = block
        assert ref.block is block


class TestBlockReferenceAllowedTypes:
    def test_allowed_block_types_union_returns_union(self):
        union_type = TestReference.allowed_block_types_union()
        # Should accept both BlockA and BlockB
        assert isinstance(BlockA(val=1), union_type)
        assert isinstance(BlockB(val="x"), union_type)

    def test_single_type_reference(self):
        union_type = SingleTypeReference.allowed_block_types_union()
        assert isinstance(BlockA(val=1), union_type)
