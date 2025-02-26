from obi.modeling.core.block import Block, SingleValueScanParameter
from obi.modeling.core.base import OBIBaseModel

from pydantic import field_validator
from importlib.metadata import version
import json, os
from collections import OrderedDict


class SingleCoordinateScanParameters(OBIBaseModel):
    single_value_scan_parameters_list: list[SingleValueScanParameter]
    nested_coordinate_subpath_str: str = ''

    @property
    def nested_param_value_subpath(self):
        self.nested_coordinate_subpath_str = ""
        for single_value_scan_parameter in self.single_value_scan_parameters_list:
            self.nested_coordinate_subpath_str = self.nested_coordinate_subpath_str + f"{single_value_scan_parameter.location_str}={single_value_scan_parameter.value}/"
        return self.nested_coordinate_subpath_str


class SingleTypeMixin:
    """Mixin to enforce no lists in all Blocks and Blocks in Category dictionaries."""

    idx: int = -1
    scan_output_root: str = ""
    _coordinate_output_root: str = ""
    single_coordinate_scan_parameters: SingleCoordinateScanParameters = None

    @field_validator("*", mode="before")
    @classmethod
    def enforce_single_type(cls, value):

        if isinstance(value, dict):  # For Block instances in 1st level dictionaries
            for key, dict_value in value.items():
                if isinstance(dict_value, Block):
                    block = dict_value
                    block.enforce_no_lists() # Enforce no lists
                        
        if isinstance(value, Block):  # For Block instances at the 1st level
            block = value
            value.enforce_no_lists() # Enforce no lists
                
        return value

    @property
    def coordinate_output_root(self):

        if self._coordinate_output_root == "":
            self._coordinate_output_root = os.path.join(self.scan_output_root, self.single_coordinate_scan_parameters.nested_param_value_subpath)

            # Old index based directories
            # if self._coordinate_output_root == "":
            # self._coordinate_output_root = os.path.join(self.scan_output_root, f"{self.idx}")

        return self._coordinate_output_root

    @coordinate_output_root.setter
    def coordinate_output_root(self, value):
        self._coordinate_output_root = value
            

    def serialize(self, output_path):

        model_dump = self.model_dump(serialize_as_any=True)
        model_dump = OrderedDict(model_dump)
        model_dump["obi_version"] = version("obi")
        model_dump["obi_class"] = self.__class__.__name__
        model_dump["coordinate_output_root"] = self.coordinate_output_root

        model_dump.move_to_end('scan_output_root', last=False)
        model_dump.move_to_end('coordinate_output_root', last=False)
        model_dump.move_to_end('idx', last=False)
        model_dump.move_to_end('obi_class', last=False)
        model_dump.move_to_end('obi_version', last=False)
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as json_file:
            json.dump(model_dump, json_file, indent=4)