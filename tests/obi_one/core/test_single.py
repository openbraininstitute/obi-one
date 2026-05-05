import json
import logging
from pathlib import Path

import pytest

from obi_one.core.param import SingleValueScanParam
from obi_one.core.path import NamedPath
from obi_one.core.single import SingleCoordinateScanParams
from obi_one.scientific.tasks.folder_compression import (
    FolderCompressionScanConfig,
    FolderCompressionSingleConfig,
)


class TestSingleCoordinateScanParamsEmpty:
    def test_empty_scan_params(self):
        scp = SingleCoordinateScanParams()
        assert scp.scan_params == []

    def test_empty_nested_param_name_and_value_subpath(self):
        scp = SingleCoordinateScanParams()
        assert scp.nested_param_name_and_value_subpath == Path()

    def test_empty_nested_param_value_subpath(self):
        scp = SingleCoordinateScanParams()
        assert scp.nested_param_value_subpath == Path()


class TestSingleCoordinateScanParamsWithParams:
    @pytest.fixture
    def scan_params(self):
        return SingleCoordinateScanParams(
            scan_params=[
                SingleValueScanParam(location_list=["initialize", "file_format"], value="gz"),
                SingleValueScanParam(location_list=["initialize", "file_name"], value="out"),
            ]
        )

    def test_nested_param_name_and_value_subpath(self, scan_params):
        path = scan_params.nested_param_name_and_value_subpath
        assert "initialize.file_format=gz" in str(path)
        assert "initialize.file_name=out" in str(path)

    def test_nested_param_value_subpath(self, scan_params):
        path = scan_params.nested_param_value_subpath
        assert "gz" in str(path)
        assert "out" in str(path)

    def test_dictionary_representation(self, scan_params):
        d = scan_params.dictionary_representation()
        assert d["initialize.file_format"] == "gz"
        assert d["initialize.file_name"] == "out"


class TestSingleConfigMixinEnforcement:
    def test_single_config_rejects_list_in_block(self):
        with pytest.raises(TypeError, match="must not be a list"):
            FolderCompressionSingleConfig(
                initialize=FolderCompressionScanConfig.Initialize(
                    folder_path=[
                        NamedPath(name="a", path="/a"),
                        NamedPath(name="b", path="/b"),
                    ],
                )
            )

    def test_single_config_accepts_single_values(self):
        config = FolderCompressionSingleConfig(
            initialize=FolderCompressionScanConfig.Initialize(
                folder_path=NamedPath(name="test", path="/data/test"),
                file_format="gz",
                file_name="output",
            )
        )
        assert config.initialize.folder_path.name == "test"


class TestSingleConfigMixinDefaults:
    def test_default_idx(self):
        config = FolderCompressionSingleConfig(
            initialize=FolderCompressionScanConfig.Initialize(
                folder_path=NamedPath(name="t", path="/t"),
            )
        )
        assert config.idx == -1

    def test_default_scan_output_root(self):
        config = FolderCompressionSingleConfig(
            initialize=FolderCompressionScanConfig.Initialize(
                folder_path=NamedPath(name="t", path="/t"),
            )
        )
        assert config.scan_output_root == Path()


class TestInitializeCoordinateOutputRoot:
    @pytest.fixture
    def single_config(self):
        config = FolderCompressionSingleConfig(
            initialize=FolderCompressionScanConfig.Initialize(
                folder_path=NamedPath(name="t", path="/t"),
            )
        )
        config.single_coordinate_scan_params = SingleCoordinateScanParams(
            scan_params=[
                SingleValueScanParam(location_list=["initialize", "file_format"], value="gz"),
            ]
        )
        config.idx = 0
        return config

    def test_name_equals_value_option(self, single_config, tmp_path):
        single_config.initialize_coordinate_output_root(tmp_path, "NAME_EQUALS_VALUE")
        assert single_config.scan_output_root == tmp_path
        assert single_config.coordinate_output_root.exists()
        assert "initialize.file_format=gz" in str(single_config.coordinate_output_root)

    def test_value_option(self, single_config, tmp_path):
        single_config.initialize_coordinate_output_root(tmp_path, "VALUE")
        assert "gz" in str(single_config.coordinate_output_root)

    def test_zero_index_option(self, single_config, tmp_path):
        single_config.initialize_coordinate_output_root(tmp_path, "ZERO_INDEX")
        assert single_config.coordinate_output_root == tmp_path / "0"
        assert single_config.coordinate_output_root.exists()

    def test_invalid_option_raises(self, single_config, tmp_path):
        with pytest.raises(ValueError, match="Invalid coordinate_directory_option"):
            single_config.initialize_coordinate_output_root(tmp_path, "INVALID")


class TestSingleConfigMixinSerialize:
    def test_serialize_creates_json(self, tmp_path):
        config = FolderCompressionSingleConfig(
            initialize=FolderCompressionScanConfig.Initialize(
                folder_path=NamedPath(name="t", path="/t"),
            )
        )
        config.single_coordinate_scan_params = SingleCoordinateScanParams()
        config.idx = 0

        output_path = tmp_path / "config.json"
        config.serialize(output_path)

        assert output_path.exists()
        data = json.loads(output_path.read_text())
        assert "type" in data
        assert "idx" in data
        assert data["idx"] == 0
        assert "obi_one_version" in data

    def test_serialize_key_order(self, tmp_path):
        config = FolderCompressionSingleConfig(
            initialize=FolderCompressionScanConfig.Initialize(
                folder_path=NamedPath(name="t", path="/t"),
            )
        )
        config.single_coordinate_scan_params = SingleCoordinateScanParams()
        config.idx = 0

        output_path = tmp_path / "config.json"
        config.serialize(output_path)

        data = json.loads(output_path.read_text())
        keys = list(data.keys())
        # First keys should be obi_one_version, type, idx, coordinate_output_root, scan_output_root
        assert keys[0] == "obi_one_version"
        assert keys[1] == "type"
        assert keys[2] == "idx"


class TestSingleCoordinateScanParamsDisplay:
    def test_display_no_params(self, caplog):
        with caplog.at_level(logging.INFO):
            scp = SingleCoordinateScanParams()
            scp.display_parameters()

    def test_display_with_params(self, caplog):
        scp = SingleCoordinateScanParams(
            scan_params=[
                SingleValueScanParam(location_list=["a", "b"], value=1),
                SingleValueScanParam(location_list=["c"], value=2),
            ]
        )
        with caplog.at_level(logging.INFO):
            scp.display_parameters()


class TestSingleCoordinateScanParamsDictionaryRepresentation:
    def test_empty(self):
        scp = SingleCoordinateScanParams()
        assert scp.dictionary_representation() == {}

    def test_single_param(self):
        scp = SingleCoordinateScanParams(
            scan_params=[
                SingleValueScanParam(location_list=["x", "y"], value=42),
            ]
        )
        d = scp.dictionary_representation()
        assert d == {"x.y": 42}

    def test_multiple_params(self):
        scp = SingleCoordinateScanParams(
            scan_params=[
                SingleValueScanParam(location_list=["a"], value=1),
                SingleValueScanParam(location_list=["b"], value=2),
            ]
        )
        d = scp.dictionary_representation()
        assert d == {"a": 1, "b": 2}


class TestInitializeCoordinateOutputRootDefaults:
    def test_default_option_is_name_equals_value(self, tmp_path):
        config = FolderCompressionSingleConfig(
            initialize=FolderCompressionScanConfig.Initialize(
                folder_path=NamedPath(name="t", path="/t"),
            )
        )
        config.single_coordinate_scan_params = SingleCoordinateScanParams(
            scan_params=[
                SingleValueScanParam(location_list=["x"], value="v"),
            ]
        )
        config.idx = 0
        # Default option
        config.initialize_coordinate_output_root(tmp_path)
        assert config.coordinate_output_root.exists()
