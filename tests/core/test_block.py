import pytest

from obi_one.core.block import Block
from obi_one.core.parametric_multi_values import IntRange


class SimpleBlock(Block):
    value: int = 0
    name: str = "test"


class MultiValueBlock(Block):
    single_val: int = 1
    list_val: list[int] = [10, 20, 30]
    another_single: str = "hello"


class RangeBlock(Block):
    single_val: float = 1.0
    range_val: IntRange = IntRange(start=1, step=1, end=3)


class TestBlockCreation:
    def test_create_simple_block(self):
        block = SimpleBlock(value=5, name="myblock")
        assert block.value == 5
        assert block.name == "myblock"

    def test_block_has_type_field(self):
        block = SimpleBlock()
        assert block.type == "SimpleBlock"

    def test_block_inherits_obi_base_model(self):
        from obi_one.core.base import OBIBaseModel

        assert issubclass(Block, OBIBaseModel)


class TestBlockName:
    def test_block_name_not_set_raises(self):
        block = SimpleBlock()
        with pytest.raises(ValueError, match="Block name has not been set"):
            _ = block.block_name

    def test_has_block_name_false_initially(self):
        block = SimpleBlock()
        assert block.has_block_name() is False

    def test_set_block_name(self):
        block = SimpleBlock()
        block.set_block_name("my_block")
        assert block.block_name == "my_block"
        assert block.has_block_name() is True

    def test_set_block_name_overwrite(self):
        block = SimpleBlock()
        block.set_block_name("first")
        block.set_block_name("second")
        assert block.block_name == "second"


class TestBlockRef:
    def test_ref_not_set_raises(self):
        block = SimpleBlock()
        with pytest.raises(ValueError, match="Block reference has not been set"):
            _ = block.ref

    def test_has_ref_false_initially(self):
        block = SimpleBlock()
        assert block.has_ref() is False

    def test_set_ref(self):
        block = SimpleBlock()
        sentinel = object()
        block.set_ref(sentinel)
        assert block.ref is sentinel
        assert block.has_ref() is True


class TestMultipleValueParameters:
    def test_list_field_detected(self):
        block = MultiValueBlock()
        params = block.multiple_value_parameters(category_name="cat")
        list_params = [p for p in params if "list_val" in p.location_list]
        assert len(list_params) == 1
        assert list_params[0].values == [10, 20, 30]

    def test_single_field_not_detected(self):
        block = SimpleBlock(value=5, name="test")
        params = block.multiple_value_parameters(category_name="cat")
        assert len(params) == 0

    def test_location_list_without_block_key(self):
        block = MultiValueBlock()
        params = block.multiple_value_parameters(category_name="stimuli")
        for p in params:
            assert p.location_list[0] == "stimuli"
            assert len(p.location_list) == 2  # [category, field_name]

    def test_location_list_with_block_key(self):
        block = MultiValueBlock()
        params = block.multiple_value_parameters(category_name="stimuli", block_key="stim_1")
        for p in params:
            assert p.location_list[0] == "stimuli"
            assert p.location_list[1] == "stim_1"
            assert len(p.location_list) == 3  # [category, block_key, field_name]

    def test_parametric_multi_value_detected(self):
        block = RangeBlock()
        params = block.multiple_value_parameters(category_name="cat")
        range_params = [p for p in params if "range_val" in p.location_list]
        assert len(range_params) == 1
        assert range_params[0].values == [1, 2, 3]

    def test_resets_on_each_call(self):
        block = MultiValueBlock()
        params1 = block.multiple_value_parameters(category_name="cat1")
        params2 = block.multiple_value_parameters(category_name="cat2")
        # Locations should reflect the most recent call
        assert all(p.location_list[0] == "cat2" for p in params2)


class TestEnforceNoMultiParam:
    def test_raises_on_list(self):
        block = MultiValueBlock()
        with pytest.raises(TypeError, match="must not be a list"):
            block.enforce_no_multi_param()

    def test_raises_on_parametric_multi_value(self):
        block = RangeBlock()
        with pytest.raises(TypeError, match="must not be a ParametericMultiValue"):
            block.enforce_no_multi_param()

    def test_passes_on_single_values(self):
        block = SimpleBlock(value=5, name="ok")
        block.enforce_no_multi_param()  # Should not raise

    def test_error_message_includes_field_name(self):
        block = MultiValueBlock()
        with pytest.raises(TypeError, match="list_val"):
            block.enforce_no_multi_param()
