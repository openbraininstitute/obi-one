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

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(BlockA | BlockB)
    }


class SingleTypeReference(BlockReference):
    allowed_block_types: ClassVar[Any] = Annotated[BlockA, Discriminator("type")]

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(BlockA)
    }


class TestBlockReferenceCreation:
    def test_creation_with_fields(self):
        ref = TestReference(block_dict_name="neuron_sets", block_name="ns_1")
        assert ref.block_dict_name == "neuron_sets"
        assert ref.block_name == "ns_1"

    def test_default_block_dict_name(self):
        ref = TestReference(block_name="test")
        assert not ref.block_dict_name


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

    def test_unrelated_block_not_in_union(self):
        union_type = TestReference.allowed_block_types_union()
        assert not isinstance(UnrelatedBlock(val=0.0), union_type)


class TestBlockReferenceSerialization:
    def test_model_dump(self):
        ref = TestReference(block_dict_name="stimuli", block_name="stim_1")
        dump = ref.model_dump()
        assert dump["block_dict_name"] == "stimuli"
        assert dump["block_name"] == "stim_1"
        assert dump["type"] == "TestReference"

    def test_json_round_trip(self):
        ref = TestReference(block_dict_name="ns", block_name="target")
        json_str = ref.model_dump_json()
        restored = TestReference.model_validate_json(json_str)
        assert restored.block_dict_name == "ns"
        assert restored.block_name == "target"


class TestBlockReferenceErrorMessages:
    def test_unset_block_error_includes_name_and_dict(self):
        ref = TestReference(block_dict_name="neuron_sets", block_name="missing_block")
        with pytest.raises(ValueError, match="missing_block") as exc_info:
            _ = ref.block
        assert "neuron_sets" in str(exc_info.value)

    def test_unset_block_error_mentions_troubleshooting(self):
        ref = TestReference(block_dict_name="ns", block_name="x")
        with pytest.raises(ValueError, match="block_dict_name"):
            _ = ref.block
