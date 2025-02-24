from pydantic import BaseModel, field_validator, PrivateAttr
from importlib.metadata import version
import json
from obi.modeling.core.block import Block

class Form(BaseModel):
    """
    """
    _sonata_config: dict = PrivateAttr(default={})

    _single_coord_class_name: str = ""

    def cast_to_single_coord(self):
        module = __import__(self.__module__)
        class_to_cast_to = getattr(module, self._single_coord_class_name)
        single_coord = class_to_cast_to.model_construct(**self.__dict__)
        return single_coord

    def __str__(self):
        return self.__repr__()

    def dump_model_to_json_with_package_version(self, output_path):
        model_dump = self.model_dump()
        model_dump["obi_version"] = version("obi")
        with open(output_path, "w") as json_file:
            json.dump(model_dump, json_file, indent=4)


class SingleTypeMixin:
    """Mixin to enforce no lists in all Blocks and Blocks in Category dictionaries."""

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
    
