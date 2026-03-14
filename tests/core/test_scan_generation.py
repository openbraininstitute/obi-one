import json
from pathlib import Path

import pytest

from obi_one.core.exception import OBIONEError
from obi_one.core.path import NamedPath
from obi_one.core.scan_generation import (
    CoupledScanGenerationTask,
    GridScanGenerationTask,
)
from obi_one.core.single import SingleCoordinateScanParams
from obi_one.scientific.tasks.folder_compression import (
    FolderCompressionScanConfig,
)


def make_config(**init_kwargs):
    """Helper to create a FolderCompressionScanConfig."""
    defaults = {
        "folder_path": NamedPath(name="test", path="/data/test"),
    }
    defaults.update(init_kwargs)
    return FolderCompressionScanConfig(
        initialize=FolderCompressionScanConfig.Initialize(**defaults)
    )


def make_grid_scan(config, output_root=None):
    return GridScanGenerationTask(
        form=config,
        output_root=output_root or Path(),
    )


def make_coupled_scan(config, output_root=None):
    return CoupledScanGenerationTask(
        form=config,
        output_root=output_root or Path(),
    )


class TestScanGenerationTaskCreation:
    def test_create_grid_scan(self):
        config = make_config()
        scan = make_grid_scan(config)
        assert scan.form is not None

    def test_create_coupled_scan(self):
        config = make_config()
        scan = make_coupled_scan(config)
        assert scan.form is not None

    def test_default_output_root(self):
        scan = make_grid_scan(make_config())
        assert scan.output_root == Path()

    def test_default_coordinate_directory_option(self):
        scan = make_grid_scan(make_config())
        assert scan.coordinate_directory_option == "NAME_EQUALS_VALUE"


class TestSingleConfigsProperty:
    def test_raises_when_not_generated(self):
        scan = make_grid_scan(make_config())
        with pytest.raises(OBIONEError, match="No single_configs"):
            _ = scan.single_configs


class TestMultipleValueParameters:
    def test_no_multi_value_params(self):
        config = make_config()
        scan = make_grid_scan(config)
        params = scan.multiple_value_parameters()
        assert len(params) == 0

    def test_single_list_param(self):
        config = make_config(file_format=["gz", "bz2"])
        scan = make_grid_scan(config)
        params = scan.multiple_value_parameters()
        assert len(params) == 1
        assert params[0].values == ["gz", "bz2"]

    def test_multiple_list_params(self):
        config = make_config(
            file_format=["gz", "bz2"],
            file_name=["out1", "out2"],
        )
        scan = make_grid_scan(config)
        params = scan.multiple_value_parameters()
        assert len(params) == 2

    def test_multiple_value_parameters_dictionary(self):
        config = make_config(file_format=["gz", "bz2"])
        scan = make_grid_scan(config)
        d = scan.multiple_value_parameters_dictionary
        assert len(d) == 1
        values = next(iter(d.values()))
        assert values == ["gz", "bz2"]


class TestGridScanCoordinateParameters:
    def test_no_multi_values_single_coordinate(self):
        config = make_config()
        scan = make_grid_scan(config)
        coords = scan.coordinate_parameters()
        assert len(coords) == 1
        assert isinstance(coords[0], SingleCoordinateScanParams)

    def test_single_dimension(self):
        config = make_config(file_format=["gz", "bz2", "xz"])
        scan = make_grid_scan(config)
        coords = scan.coordinate_parameters()
        assert len(coords) == 3

    def test_two_dimensions_cartesian_product(self):
        config = make_config(
            file_format=["gz", "bz2"],
            file_name=["out1", "out2", "out3"],
        )
        scan = make_grid_scan(config)
        coords = scan.coordinate_parameters()
        assert len(coords) == 6  # 2 * 3

    def test_coordinate_values_correct(self):
        config = make_config(file_format=["gz", "bz2"])
        scan = make_grid_scan(config)
        coords = scan.coordinate_parameters()
        values = [cp.scan_params[0].value for cp in coords]
        assert "gz" in values
        assert "bz2" in values


class TestCoupledScanCoordinateParameters:
    def test_no_multi_values_single_coordinate(self):
        config = make_config()
        scan = make_coupled_scan(config)
        coords = scan.coordinate_parameters()
        assert len(coords) == 1

    def test_equal_length_params(self):
        config = make_config(
            file_format=["gz", "bz2"],
            file_name=["out1", "out2"],
        )
        scan = make_coupled_scan(config)
        coords = scan.coordinate_parameters()
        assert len(coords) == 2  # Coupled, not Cartesian

    def test_unequal_length_params_raises(self):
        config = make_config(
            file_format=["gz", "bz2"],
            file_name=["out1", "out2", "out3"],
        )
        scan = make_coupled_scan(config)
        with pytest.raises(ValueError, match="different lengths"):
            scan.coordinate_parameters()

    def test_coupled_values_paired(self):
        config = make_config(
            file_format=["gz", "bz2"],
            file_name=["out1", "out2"],
        )
        scan = make_coupled_scan(config)
        coords = scan.coordinate_parameters()
        # First coordinate should have first value of each param
        first_values = {p.value for p in coords[0].scan_params}
        assert "gz" in first_values or "out1" in first_values


class TestCreateSingleConfigs:
    def test_no_multi_values(self, tmp_path):
        config = make_config()
        scan = make_grid_scan(config, output_root=tmp_path)
        scan.coordinate_parameters()
        singles = scan.create_single_configs()
        assert len(singles) == 1

    def test_with_multi_values(self, tmp_path):
        config = make_config(file_format=["gz", "bz2"])
        scan = make_grid_scan(config, output_root=tmp_path)
        scan.coordinate_parameters()
        singles = scan.create_single_configs()
        assert len(singles) == 2

    def test_single_config_idx(self, tmp_path):
        config = make_config(file_format=["gz", "bz2", "xz"])
        scan = make_grid_scan(config, output_root=tmp_path)
        scan.coordinate_parameters()
        singles = scan.create_single_configs()
        indices = [s.idx for s in singles]
        assert indices == [0, 1, 2]

    def test_single_config_has_single_values(self, tmp_path):
        config = make_config(file_format=["gz", "bz2"])
        scan = make_grid_scan(config, output_root=tmp_path)
        scan.coordinate_parameters()
        singles = scan.create_single_configs()
        for single in singles:
            assert not isinstance(single.initialize.file_format, list)


class TestScanGenerationTaskSerialize:
    def test_serialize_creates_file(self, tmp_path):
        config = make_config()
        scan = make_grid_scan(config, output_root=tmp_path)
        output_path = tmp_path / "scan.json"
        result = scan.serialize(output_path)

        assert output_path.exists()
        assert isinstance(result, dict)

    def test_serialize_includes_version(self, tmp_path):
        config = make_config()
        scan = make_grid_scan(config, output_root=tmp_path)
        output_path = tmp_path / "scan.json"
        result = scan.serialize(output_path)

        assert "obi_one_version" in result

    def test_serialize_key_order(self, tmp_path):
        config = make_config()
        scan = make_grid_scan(config, output_root=tmp_path)
        output_path = tmp_path / "scan.json"
        result = scan.serialize(output_path)

        keys = list(result.keys())
        assert keys[0] == "obi_one_version"
        assert keys[1] == "type"
        assert keys[2] == "output_root"

    def test_serialize_form_has_type_first(self, tmp_path):
        config = make_config()
        scan = make_grid_scan(config, output_root=tmp_path)
        output_path = tmp_path / "scan.json"
        result = scan.serialize(output_path)

        form_keys = list(result["form"].keys())
        assert form_keys[0] == "type"

    def test_serialize_file_is_valid_json(self, tmp_path):
        config = make_config()
        scan = make_grid_scan(config, output_root=tmp_path)
        output_path = tmp_path / "scan.json"
        scan.serialize(output_path)

        data = json.loads(output_path.read_text())
        assert data["type"] == "GridScanGenerationTask"


class TestScanGenerationTaskExecute:
    def test_execute_creates_output_dir(self, tmp_path):
        output_root = tmp_path / "scan_output"
        config = make_config()
        scan = make_grid_scan(config, output_root=output_root)
        scan.execute()

        assert output_root.exists()

    def test_execute_creates_scan_config_file(self, tmp_path):
        output_root = tmp_path / "scan_output"
        config = make_config()
        scan = make_grid_scan(config, output_root=output_root)
        scan.execute()

        assert (output_root / "obi_one_scan.json").exists()

    def test_execute_creates_coordinate_config_files(self, tmp_path):
        output_root = tmp_path / "scan_output"
        config = make_config(file_format=["gz", "bz2"])
        scan = make_grid_scan(config, output_root=output_root)
        scan.execute()

        # Should have 2 coordinate directories
        coord_files = list(output_root.rglob("obi_one_coordinate.json"))
        assert len(coord_files) == 2

    def test_execute_populates_single_configs(self, tmp_path):
        output_root = tmp_path / "scan_output"
        config = make_config(file_format=["gz", "bz2"])
        scan = make_grid_scan(config, output_root=output_root)
        scan.execute()

        assert len(scan.single_configs) == 2

    def test_execute_no_multi_values(self, tmp_path):
        output_root = tmp_path / "scan_output"
        config = make_config()
        scan = make_grid_scan(config, output_root=output_root)
        scan.execute()

        assert len(scan.single_configs) == 1

    def test_execute_with_zero_index_option(self, tmp_path):
        output_root = tmp_path / "scan_output"
        config = make_config(file_format=["gz", "bz2"])
        scan = GridScanGenerationTask(
            form=config,
            output_root=output_root,
            coordinate_directory_option="ZERO_INDEX",
        )
        scan.execute()

        assert (output_root / "0").exists()
        assert (output_root / "1").exists()


class TestCoupledScanExecute:
    def test_coupled_execute(self, tmp_path):
        output_root = tmp_path / "coupled_output"
        config = make_config(
            file_format=["gz", "bz2"],
            file_name=["out1", "out2"],
        )
        scan = make_coupled_scan(config, output_root=output_root)
        scan.execute()

        assert len(scan.single_configs) == 2

    def test_coupled_no_multi_values(self, tmp_path):
        output_root = tmp_path / "coupled_output"
        config = make_config()
        scan = make_coupled_scan(config, output_root=output_root)
        scan.execute()

        assert len(scan.single_configs) == 1
