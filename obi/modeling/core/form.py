from pydantic import field_validator, PrivateAttr
from importlib.metadata import version
import json, os
from collections import OrderedDict

from obi.modeling.core.block import Block
from obi.modeling.core.base import OBIBaseModel

class Form(OBIBaseModel):
    """
    """
    _sonata_config: dict = PrivateAttr(default={})
    _single_coord_class_name: str = ""
    # coordinate_parameters: tuple = ()

    def cast_to_single_coord(self):
        module = __import__(self.__module__)
        class_to_cast_to = getattr(module, self._single_coord_class_name)
        single_coord = class_to_cast_to.model_construct(**self.__dict__)
        return single_coord



class SingleTypeMixin:
    """Mixin to enforce no lists in all Blocks and Blocks in Category dictionaries."""

    idx: int = -1
    scan_output_root: str = ""
    _coordinate_output_root: str = ""
    single_coordinate_scan_parameters: None

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

        print(self._coordinate_output_root)
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