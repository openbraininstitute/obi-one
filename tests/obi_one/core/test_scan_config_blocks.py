"""Tests for ScanConfig block-related methods using simple test fixtures.

These tests use minimal concrete subclasses to avoid importing scientific modules.
"""

from typing import Annotated, Any, ClassVar

import pytest
from pydantic import Discriminator, Field

from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference
from obi_one.core.scan_config import ScanConfig

# --- Test fixtures: minimal concrete types ---


class BlockTypeA(Block):
    val_a: int = 1


class BlockTypeB(Block):
    val_b: str = "b"


BlockUnion = Annotated[BlockTypeA | BlockTypeB, Discriminator("type")]


class TestRef(BlockReference):
    allowed_block_types: ClassVar[Any] = BlockUnion


class SimpleConfig(ScanConfig):
    """ScanConfig with only a root-level Block, no dicts."""

    single_coord_class_name: ClassVar[str] = ""
    name: ClassVar[str] = "SimpleConfig"
    description: ClassVar[str] = "Simple"

    class Initialize(Block):
        type: str = "Block"
        x: int = 0

    initialize: Initialize


class DictBlockConfig(ScanConfig):
    """ScanConfig with a dictionary of Blocks, for block_mapping tests."""

    single_coord_class_name: ClassVar[str] = ""
    name: ClassVar[str] = "DictBlockConfig"
    description: ClassVar[str] = "Has dict blocks"

    class Initialize(Block):
        type: str = "Block"
        x: int = 0

    initialize: Initialize

    blocks: dict[str, BlockUnion] = Field(
        default_factory=dict,
        json_schema_extra={"reference_type": "TestRef"},
    )


class RefHolder(Block):
    """A block that holds a BlockReference attribute."""

    ref_field: TestRef | None = None


class ConfigWithRefBlock(ScanConfig):
    """ScanConfig where a root-level block contains a BlockReference."""

    single_coord_class_name: ClassVar[str] = ""
    name: ClassVar[str] = "ConfigWithRefBlock"
    description: ClassVar[str] = "Has ref block"

    class Initialize(Block):
        type: str = "Block"
        x: int = 0

    initialize: Initialize

    blocks: dict[str, BlockUnion] = Field(
        default_factory=dict,
        json_schema_extra={"reference_type": "TestRef"},
    )

    ref_holder: RefHolder = Field(default_factory=RefHolder)


# --- Tests ---


class TestBlockMappingEmpty:
    def test_no_dict_blocks_returns_empty(self):
        config = SimpleConfig(initialize=SimpleConfig.Initialize(x=1))
        assert config.block_mapping == {}


class TestBlockMappingDict:
    def test_dict_blocks_in_mapping(self):
        config = DictBlockConfig(
            initialize=DictBlockConfig.Initialize(x=1),
            blocks={"b1": BlockTypeA(val_a=10)},
        )
        mapping = config.block_mapping
        assert "BlockTypeA" in mapping
        assert "BlockTypeB" in mapping

    def test_mapping_contains_block_dict_name(self):
        config = DictBlockConfig(
            initialize=DictBlockConfig.Initialize(),
        )
        mapping = config.block_mapping
        assert mapping["BlockTypeA"]["block_dict_name"] == "blocks"

    def test_mapping_contains_reference_type(self):
        config = DictBlockConfig(
            initialize=DictBlockConfig.Initialize(),
        )
        mapping = config.block_mapping
        assert mapping["BlockTypeA"]["reference_type"] == "TestRef"

    def test_mapping_cached_on_second_call(self):
        config = DictBlockConfig(
            initialize=DictBlockConfig.Initialize(),
        )
        m1 = config.block_mapping
        m2 = config.block_mapping
        assert m1 is m2


class TestBlockMappingMissingReferenceType:
    def test_missing_reference_type_raises(self):
        """If json_schema_extra lacks 'reference_type', should raise."""

        class BadConfig(ScanConfig):
            single_coord_class_name: ClassVar[str] = ""
            name: ClassVar[str] = "Bad"
            description: ClassVar[str] = ""

            class Initialize(Block):
                type: str = "Block"

            initialize: Initialize
            blocks: dict[str, BlockUnion] = Field(
                default_factory=dict,
                json_schema_extra={"ui_element": "block_dictionary"},
                # No 'reference_type'!
            )

        config = BadConfig(initialize=BadConfig.Initialize())
        with pytest.raises(ValueError, match="reference_type"):
            _ = config.block_mapping


class TestFillBlockNamesOnValidation:
    def test_dict_block_names_set_on_construction(self):
        config = DictBlockConfig(
            initialize=DictBlockConfig.Initialize(),
            blocks={
                "alpha": BlockTypeA(val_a=1),
                "beta": BlockTypeB(val_b="hello"),
            },
        )
        assert config.blocks["alpha"].block_name == "alpha"
        assert config.blocks["beta"].block_name == "beta"

    def test_root_block_not_given_name(self):
        """Root-level blocks (not in dicts) are not given block names via the validator."""
        config = SimpleConfig(initialize=SimpleConfig.Initialize(x=5))
        assert not config.initialize.has_block_name()


class TestFillBlockReferences:
    def test_block_reference_in_dict_block_resolved(self):
        """A block inside a dict that has a BlockReference pointing to another dict block."""
        # RefHolder is a root block, but the reference targets a dict block.
        holder = RefHolder(ref_field=TestRef(block_dict_name="blocks", block_name="target_block"))
        config = ConfigWithRefBlock(
            initialize=ConfigWithRefBlock.Initialize(),
            blocks={"target_block": BlockTypeA(val_a=99)},
            ref_holder=holder,
        )
        # The reference should be resolved to the actual block
        assert config.ref_holder.ref_field.has_block()
        assert config.ref_holder.ref_field.block is config.blocks["target_block"]

    def test_block_reference_bad_dict_name_raises(self):
        holder = RefHolder(ref_field=TestRef(block_dict_name="nonexistent_dict", block_name="x"))
        with pytest.raises(KeyError):
            ConfigWithRefBlock(
                initialize=ConfigWithRefBlock.Initialize(),
                blocks={},
                ref_holder=holder,
            )

    def test_block_reference_bad_block_name_raises(self):
        holder = RefHolder(ref_field=TestRef(block_dict_name="blocks", block_name="missing"))
        with pytest.raises(KeyError, match="missing"):
            ConfigWithRefBlock(
                initialize=ConfigWithRefBlock.Initialize(),
                blocks={"other": BlockTypeA()},
                ref_holder=holder,
            )


class TestSetMethod:
    def test_set_replaces_root_block(self):
        config = SimpleConfig(initialize=SimpleConfig.Initialize(x=1))
        new_init = SimpleConfig.Initialize(x=99)
        config.set(new_init, name="initialize")
        assert config.initialize.x == 99


class TestValidatedConfig:
    def test_round_trip_preserves_values(self):
        config = DictBlockConfig(
            initialize=DictBlockConfig.Initialize(x=42),
            blocks={"b1": BlockTypeA(val_a=7)},
        )
        validated = config.validated_config()
        assert validated.initialize.x == 42
        assert validated.blocks["b1"].val_a == 7
        assert isinstance(validated, DictBlockConfig)


class TestEmptyConfig:
    def test_empty_config_type(self):
        config = DictBlockConfig.empty_config()
        assert isinstance(config, DictBlockConfig)


class TestScanConfigSerialization:
    def test_dict_blocks_serialize(self):
        config = DictBlockConfig(
            initialize=DictBlockConfig.Initialize(x=5),
            blocks={"b1": BlockTypeA(val_a=10)},
        )
        dump = config.model_dump()
        assert dump["blocks"]["b1"]["val_a"] == 10
        assert dump["blocks"]["b1"]["type"] == "BlockTypeA"

    def test_json_round_trip_dict_blocks(self):
        config = DictBlockConfig(
            initialize=DictBlockConfig.Initialize(x=5),
            blocks={"b1": BlockTypeA(val_a=10)},
        )
        json_str = config.model_dump_json()
        restored = DictBlockConfig.model_validate_json(json_str)
        assert restored.blocks["b1"].val_a == 10
