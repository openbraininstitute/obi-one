from typing import ClassVar

from obi_one.core.base import OBIBaseModel


class Form(OBIBaseModel):
    """A Form is a configuration for single or multi-dimensional parameter scans.

    A Form is composed of Blocks, which either appear at the root level
    or within dictionaries of Blocks where the dictionary is takes a Union of Block types.
    """

    name: ClassVar[str] = "Add a name class' name variable"
    description: ClassVar[str] = """Add a description to the class' description variable"""
    single_coord_class_name: ClassVar[str] = ""

    def cast_to_single_coord(self) -> OBIBaseModel:
        """Cast the form to a single coordinate object."""
        module = __import__(self.__module__)
        class_to_cast_to = getattr(module, self.single_coord_class_name)
        single_coord = class_to_cast_to.model_construct(**self.__dict__)
        single_coord.type = self.single_coord_class_name
        return single_coord

    @property
    def single_coord_scan_default_subpath(self) -> str:
        return self.single_coord_class_name + "/"

    class Config:
        json_encoders = {}



from obi_one.core.block import Block
import json
def block_encoder(obj):

    if isinstance(obj, Block):

        block_dict = obj.__dict__.copy()
        for attr_name, attr_value in obj.__dict__.items():

            if isinstance(attr_value, Block):
                block_dict[attr_name] = attr_value.simulation_level_name
            else:
                block_dict[attr_name] = attr_value

        return block_dict
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

Form.Config.json_encoders.update({
    Block: block_encoder
})
