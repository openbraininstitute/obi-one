from typing import ClassVar
from pydantic import model_validator

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference


class Form(OBIBaseModel):
    """A Form is a configuration for single or multi-dimensional parameter scans.

    A Form is composed of Blocks, which either appear at the root level
    or within dictionaries of Blocks where the dictionary is takes a Union of Block types.
    """

    name: ClassVar[str] = "Add a name class' name variable"
    description: ClassVar[str] = """Add a description to the class' description variable"""
    single_coord_class_name: ClassVar[str] = ""


    @model_validator(mode="after")
    def fill_block_references(self):

        for attr_name, attr_value in self.__dict__.items():
            # Check if the attribute is a dictionary of Block instances
            if isinstance(attr_value, dict) and all(
                isinstance(dict_val, Block) for dict_key, dict_val in attr_value.items()
            ):
                category_blocks_dict = attr_value

                # If so iterate through the dictionary's Block instances
                for block_key, block in category_blocks_dict.items():
                    for block_attr_name, block_attr_value in block.__dict__.items():
                        # If the Block instance has a `BlockReference` attribute, set it the object it references
                        if isinstance(block_attr_value, BlockReference):
                            block_reference = block_attr_value
                            block_reference.block = self.__dict__[block_reference.block_dict_name][block_reference.block_name]
            
            elif isinstance(attr_value, Block):
                for block_attr_name, block_attr_value in attr_value.__dict__.items():
                    # If the Block instance has a `BlockReference` attribute, set it the object it references
                    if isinstance(block_attr_value, BlockReference):
                        block_reference = block_attr_value
                        block_reference.block = self.__dict__[block_reference.block_dict_name][block_reference.block_name]

        return self


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
