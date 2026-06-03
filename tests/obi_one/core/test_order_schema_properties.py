"""Tests for the PARAMETER_ORDER_PRIORITY schema-ordering logic.

Blocks order the properties of their generated JSON schema by the
``SchemaKey.PARAMETER_ORDER_PRIORITY`` value found in each field's
``json_schema_extra``. Higher priorities appear first, fields without a
priority default to 0, and ties keep their original (definition) order.

The ordering is implemented by ``order_schema_properties`` (utils.pydantic)
and applied to every Block via ``Block.__get_pydantic_json_schema__``.
"""

from pydantic import BaseModel, Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey
from obi_one.utils.pydantic import order_schema_properties

PRIORITY = SchemaKey.PARAMETER_ORDER_PRIORITY


class PriorityBlock(Block):
    low: int = Field(default=0, json_schema_extra={PRIORITY: 1})
    high: int = Field(default=0, json_schema_extra={PRIORITY: 100})
    no_priority: int = 0
    mid: int = Field(default=0, json_schema_extra={PRIORITY: 50})


class NoPriorityBlock(Block):
    first: int = 0
    second: int = 0
    third: int = 0


class ParentBlock(Block):
    parent_a: int = 0
    parent_b: int = 0


class ChildBlock(ParentBlock):
    child_high: int = Field(default=0, json_schema_extra={PRIORITY: 100})


class TiePriorityBlock(Block):
    alpha: int = Field(default=0, json_schema_extra={PRIORITY: 5})
    beta: int = Field(default=0, json_schema_extra={PRIORITY: 5})
    gamma: int = Field(default=0, json_schema_extra={PRIORITY: 5})


class NegativePriorityBlock(Block):
    neg: int = Field(default=0, json_schema_extra={PRIORITY: -5})
    zero: int = 0
    pos: int = Field(default=0, json_schema_extra={PRIORITY: 5})


class TestBlockSchemaOrdering:
    """The PARAMETER_ORDER_PRIORITY logic applied through a Block's JSON schema."""

    def test_properties_ordered_by_descending_priority(self):
        props = list(PriorityBlock.model_json_schema()["properties"].keys())
        # high(100) > mid(50) > low(1) > [type, no_priority] (both default 0, stable order).
        assert props == ["high", "mid", "low", "type", "no_priority"]

    def test_field_without_priority_defaults_to_zero(self):
        props = list(PriorityBlock.model_json_schema()["properties"].keys())
        # no_priority has no priority key, so it sorts after every positive-priority field.
        assert props.index("no_priority") > props.index("low")

    def test_block_without_priorities_keeps_default_order(self):
        props = list(NoPriorityBlock.model_json_schema()["properties"].keys())
        # The inherited discriminator `type` field comes first, then definition order.
        assert props == ["type", "first", "second", "third"]

    def test_child_field_can_precede_parent_fields(self):
        # The documented motivation: a high-priority field on a child class appears
        # before the fields inherited from its parent.
        props = list(ChildBlock.model_json_schema()["properties"].keys())
        assert props[0] == "child_high"
        assert props.index("child_high") < props.index("parent_a")
        assert props.index("child_high") < props.index("parent_b")

    def test_equal_priority_preserves_definition_order(self):
        props = list(TiePriorityBlock.model_json_schema()["properties"].keys())
        assert props.index("alpha") < props.index("beta") < props.index("gamma")

    def test_negative_priority_sorts_after_unset_fields(self):
        props = list(NegativePriorityBlock.model_json_schema()["properties"].keys())
        # pos(5) > [type, zero] (default 0) > neg(-5).
        assert props == ["pos", "type", "zero", "neg"]

    def test_priority_value_retained_in_property_schema(self):
        prop = PriorityBlock.model_json_schema()["properties"]["high"]
        assert prop[PRIORITY] == 100

    def test_nested_block_ordered_in_defs(self):
        # In real schemas a Block sits behind a $ref (e.g. inside a ScanConfig), so the
        # ordering must reach the copy that pydantic stores under $defs, not just a
        # top-level schema. This guards the return-a-copy behaviour for nested blocks.
        class Parent(BaseModel):
            block: PriorityBlock

        props = list(Parent.model_json_schema()["$defs"]["PriorityBlock"]["properties"].keys())
        assert props[:3] == ["high", "mid", "low"]
        assert props.index("no_priority") > props.index("low")


class TestOrderSchemaProperties:
    """The order_schema_properties helper in isolation."""

    def test_orders_descending_by_priority(self):
        schema = {"properties": {"a": {PRIORITY: 1}, "b": {PRIORITY: 100}, "c": {PRIORITY: 50}}}
        result = order_schema_properties(schema)
        assert list(result["properties"].keys()) == ["b", "c", "a"]

    def test_returns_copy_without_mutating_input(self):
        schema = {"properties": {"a": {PRIORITY: 1}, "b": {PRIORITY: 9}}}
        result = order_schema_properties(schema)
        assert result is not schema
        # The returned copy is reordered; the input keeps its original order.
        assert list(result["properties"].keys()) == ["b", "a"]
        assert list(schema["properties"].keys()) == ["a", "b"]

    def test_missing_properties_key_returns_copy(self):
        schema = {"type": "object"}
        result = order_schema_properties(schema)  # must not raise
        assert result == {"type": "object"}
        assert result is not schema

    def test_empty_properties_returns_copy(self):
        schema = {"properties": {}}
        result = order_schema_properties(schema)
        assert result == {"properties": {}}
        assert result is not schema

    def test_property_without_priority_defaults_to_zero(self):
        schema = {"properties": {"no_key": {}, "high": {PRIORITY: 10}}}
        result = order_schema_properties(schema)
        assert list(result["properties"].keys()) == ["high", "no_key"]

    def test_equal_priority_is_stable(self):
        schema = {"properties": {"a": {PRIORITY: 5}, "b": {PRIORITY: 5}, "c": {PRIORITY: 9}}}
        result = order_schema_properties(schema)
        assert list(result["properties"].keys()) == ["c", "a", "b"]

    def test_negative_priority_sorts_last(self):
        schema = {"properties": {"neg": {PRIORITY: -5}, "zero": {}, "pos": {PRIORITY: 5}}}
        result = order_schema_properties(schema)
        assert list(result["properties"].keys()) == ["pos", "zero", "neg"]

    def test_falsy_priority_treated_as_default(self):
        # `value or 0` means a falsy priority (explicit 0 or None) collapses to 0.
        schema = {
            "properties": {
                "explicit_zero": {PRIORITY: 0},
                "none_priority": {PRIORITY: None},
                "positive": {PRIORITY: 3},
            }
        }
        result = order_schema_properties(schema)
        props = list(result["properties"].keys())
        assert props[0] == "positive"
        assert props.index("explicit_zero") < props.index("none_priority")
