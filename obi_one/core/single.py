import json
import os
from collections import OrderedDict
from importlib.metadata import version
from pathlib import Path

from pydantic import field_validator

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.param import SingleValueScanParam


class SingleCoordinateScanParams(OBIBaseModel):
    scan_params: list[SingleValueScanParam] = []
    nested_coordinate_subpath_str: Path = Path()

    @property
    def nested_param_name_and_value_subpath(self) -> Path:
        if len(self.scan_params):
            self.nested_coordinate_subpath_str = ""
            for scan_param in self.scan_params:
                self.nested_coordinate_subpath_str = (
                    self.nested_coordinate_subpath_str
                    + f"{scan_param.location_str}={scan_param.value}/"
                )
            return Path(self.nested_coordinate_subpath_str)
        return Path(self.nested_coordinate_subpath_str)

    @property
    def nested_param_value_subpath(self) -> Path:
        if len(self.scan_params):
            self.nested_coordinate_subpath_str = ""
            for scan_param in self.scan_params:
                self.nested_coordinate_subpath_str = (
                    self.nested_coordinate_subpath_str + f"{scan_param.value}/"
                )
            return Path(self.nested_coordinate_subpath_str)
        return Path(self.nested_coordinate_subpath_str)

    def display_parameters(self):
        output = ""

        if len(self.scan_params) == 0:
            print("No coordinate parameters.")
        else:
            for j, scan_param in enumerate(self.scan_params):
                output = output + scan_param.location_str + ": " + str(scan_param.value)
                if j < len(self.scan_params) - 1:
                    output = output + ", "
            print(output)


class SingleCoordinateMixin:
    """Mixin to enforce no lists in all Blocks and Blocks in Category dictionaries."""

    idx: int = -1
    scan_output_root: Path = Path()
    coordinate_output_root: Path = Path()
    _coordinate_directory_option: str = "NAME_EQUALS_VALUE"
    single_coordinate_scan_params: SingleCoordinateScanParams = None

    @field_validator("*", mode="before")
    @classmethod
    def enforce_single_type(cls, value):
        if isinstance(value, dict):  # For Block instances in 1st level dictionaries
            for key, dict_value in value.items():
                if isinstance(dict_value, Block):
                    block = dict_value
                    block.enforce_no_lists()  # Enforce no lists

        if isinstance(value, Block):  # For Block instances at the 1st level
            block = value
            value.enforce_no_lists()  # Enforce no lists

        return value

    def initialize_coordinate_output_root(
        self, scan_output_root: Path, coordinate_directory_option: str = "NAME_EQUALS_VALUE"
    ):
        """Initialize the output root paths for the scan and coordinate directories."""
        self.scan_output_root = scan_output_root

        self._coordinate_directory_option = coordinate_directory_option

        if self._coordinate_directory_option == "NAME_EQUALS_VALUE":
            self.coordinate_output_root = (
                self.scan_output_root
                / self.single_coordinate_scan_params.nested_param_name_and_value_subpath
            )

        elif self._coordinate_directory_option == "VALUE":
            self.coordinate_output_root = (
                self.scan_output_root
                / self.single_coordinate_scan_params.nested_param_value_subpath
            )
        elif self._coordinate_directory_option == "ZERO_INDEX":
            self.coordinate_output_root = self.scan_output_root / f"{self.idx}"
        else:
            raise ValueError(
                f"Invalid coordinate_directory_option: {self._coordinate_directory_option}"
            )

        # Create the coordinate_output_root directory
        os.makedirs(self.coordinate_output_root, exist_ok=True)

    def serialize(self, output_path):
        # Important to use model_dump_json() instead of model_dump()
        # so OBIBaseModel's custom encoder is used to seri
        # PosixPaths as strings
        model_dump = self.model_dump_json()

        # Now load it back into a dict to do some additional modifications
        model_dump = OrderedDict(json.loads(model_dump))

        model_dump["obi_one_version"] = version("obi-one")
        model_dump.move_to_end("scan_output_root", last=False)
        model_dump.move_to_end("coordinate_output_root", last=False)
        model_dump.move_to_end("idx", last=False)
        model_dump.move_to_end("type", last=False)
        model_dump.move_to_end("obi_one_version", last=False)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as json_file:
            json.dump(model_dump, json_file, indent=4)
