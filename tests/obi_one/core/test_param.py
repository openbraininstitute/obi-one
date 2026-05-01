from obi_one.core.param import (
    MultiValueScanParam,
    SingleValueScanParam,
    nested_param_short,
)


class TestNestedParamShort:
    def test_single_element(self):
        assert nested_param_short(["field"]) == "field"

    def test_multiple_elements(self):
        assert nested_param_short(["stimuli", "stim_1", "amplitude"]) == "stimuli.stim_1.amplitude"

    def test_two_elements(self):
        assert nested_param_short(["block", "value"]) == "block.value"

    def test_empty_list(self):
        assert not nested_param_short([])


class TestScanParamLocationStr:
    def test_location_str_from_multi_value(self):
        param = MultiValueScanParam(
            location_list=["stimuli", "stim_1", "amplitude"], values=[1.0, 2.0]
        )
        assert param.location_str == "stimuli.stim_1.amplitude"

    def test_location_str_from_single_value(self):
        param = SingleValueScanParam(location_list=["initialize", "dt"], value=0.025)
        assert param.location_str == "initialize.dt"


class TestMultiValueScanParam:
    def test_default_values(self):
        param = MultiValueScanParam()
        assert param.values == [None]
        assert param.location_list == []

    def test_with_values(self):
        param = MultiValueScanParam(location_list=["a", "b"], values=[1, 2, 3])
        assert param.values == [1, 2, 3]
        assert param.location_list == ["a", "b"]

    def test_with_string_values(self):
        param = MultiValueScanParam(values=["gz", "bz2", "xz"])
        assert param.values == ["gz", "bz2", "xz"]


class TestSingleValueScanParam:
    def test_with_int_value(self):
        param = SingleValueScanParam(location_list=["x"], value=42)
        assert param.value == 42

    def test_with_string_value(self):
        param = SingleValueScanParam(location_list=["fmt"], value="gz")
        assert param.value == "gz"

    def test_with_float_value(self):
        param = SingleValueScanParam(location_list=["dt"], value=0.025)
        assert param.value == 0.025  # noqa: RUF069

    def test_with_none_value(self):
        param = SingleValueScanParam(location_list=["opt"], value=None)
        assert param.value is None

    def test_index_in_scan_dimension(self):
        param = SingleValueScanParam(location_list=["x"], value=42, index_in_scan_dimension=3)
        assert param.index_in_scan_dimension == 3

    def test_index_in_scan_dimension_default_none(self):
        param = SingleValueScanParam(location_list=["x"], value=42)
        assert param.index_in_scan_dimension is None

    def test_index_in_scan_dimension_zero(self):
        param = SingleValueScanParam(location_list=["x"], value=42, index_in_scan_dimension=0)
        assert param.index_in_scan_dimension == 0


class TestScanParamSerialization:
    def test_multi_value_model_dump(self):
        param = MultiValueScanParam(location_list=["a", "b"], values=[1, 2, 3])
        dump = param.model_dump()
        assert dump["location_list"] == ["a", "b"]
        assert dump["values"] == [1, 2, 3]

    def test_single_value_model_dump(self):
        param = SingleValueScanParam(location_list=["x"], value=42)
        dump = param.model_dump()
        assert dump["location_list"] == ["x"]
        assert dump["value"] == 42
        assert dump["index_in_scan_dimension"] is None

    def test_single_value_model_dump_with_index(self):
        param = SingleValueScanParam(location_list=["x"], value=42, index_in_scan_dimension=5)
        dump = param.model_dump()
        assert dump["index_in_scan_dimension"] == 5


class TestNestedParamShortEdgeCases:
    def test_numeric_elements(self):
        assert nested_param_short([0, 1, 2]) == "0.1.2"

    def test_single_empty_string(self):
        assert not nested_param_short([""])
