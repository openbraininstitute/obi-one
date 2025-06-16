from typing import ClassVar
from pydantic import model_validator

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference

from typing import get_args, get_origin

import types



class Form(OBIBaseModel):
    """A Form is a configuration for single or multi-dimensional parameter scans.

    A Form is composed of Blocks, which either appear at the root level
    or within dictionaries of Blocks where the dictionary is takes a Union of Block types.
    """

    name: ClassVar[str] = "Add a name class' name variable"
    description: ClassVar[str] = """Add a description to the class' description variable"""
    single_coord_class_name: ClassVar[str] = ""

    _block_mapping: dict = None

    @classmethod
    def empty_config(cls):
        # Here you use model_construct or build custom behavior
        return cls.model_construct()
    
    def validated_config(self):
        return self.__class__.model_validate(self.model_dump())
    

    @property
    def block_mapping(self) -> dict:
        """Returns a mapping of block class names to block_dict_name and reference_type."""

        if self._block_mapping is None:
            # Get type annotations of the instance's class
            annotations = self.__class__.__annotations__

            self._block_mapping = {}
            for attr_name, attr_value in self.__dict__.items():
                # Check if it's a dictionary of Block instances
                if isinstance(attr_value, dict) and all(
                    isinstance(v, Block) for v in attr_value.values()
                ):
                    # Get the annotated type of this attribute (e.g., dict[str, TimestampsUnion])
                    annotated_type = annotations.get(attr_name)

                    field_info = self.__pydantic_fields__[attr_name]
                    reference_type = None

                    if field_info.json_schema_extra and "reference_type" in field_info.json_schema_extra:
                        reference_type = field_info.json_schema_extra["reference_type"]
                    else: 
                        raise ValueError(
                            f"Attribute '{attr_name}' does not have a 'reference_type' in json_schema_extra."
                        )

                    if annotated_type and get_origin(annotated_type) is dict:
                        value_type = get_args(annotated_type)[1]  # dict[key_type, value_type]

                        if hasattr(types, "UnionType") and isinstance(value_type, types.UnionType):
                            classes = [arg for arg in get_args(value_type)]
                        else:
                            classes = [value_type]

                    for block_class in classes:
                        if block_class.__name__ in self._block_mapping:
                            # If the block class is already in the mapping, append the new block
                            raise ValueError(
                                f"Block class {block_class.__name__} already exists in the mapping. \
                                    This suggests that the same block class is used in multiple dictionaries."
                            )
                        else:
                            # Initialize a new dictionary for this block class
                            self._block_mapping[block_class.__name__] = {
                                "block_dict_name": attr_name,
                                "reference_type": reference_type,
                            }

        return self._block_mapping



    

    def fill_block_reference_for_block(self, block: Block):
        """Fill the block reference with the actual Block object it references."""

        for block_attr_name, block_attr_value in block.__dict__.items():
            # If the Block instance has a `BlockReference` attribute, set it the object it references
            if isinstance(block_attr_value, BlockReference):
                block_reference = block_attr_value

                if block_reference.block_dict_name != "" and block_reference.block_name != "":
                    block_reference.block = self.__dict__[block_reference.block_dict_name][block_reference.block_name]
                elif block_reference.block_dict_name == "" and block_reference.block_name != "":
                    # If the block_dict_name is empty, we assume the block_name is a direct reference to a Block instance
                    if block_reference.block_name == "neuron_set_extra":
                        block_reference.block = self.__dict__[block_reference.block_name]
                else:
                    raise ValueError("BlockReference must have a non-empty block_dict_name and block_name.")
        

    @model_validator(mode="after")
    def fill_block_references(self):

        for attr_name, attr_value in self.__dict__.items():
            # Check if the attribute is a dictionary of Block instances
            if isinstance(attr_value, dict) and all(
                isinstance(dict_val, Block) for dict_key, dict_val in attr_value.items()
            ):
                category_blocks_dict = attr_value

                # If so iterate through the dictionary's Block instances
                for _, block in category_blocks_dict.items():
                    self.fill_block_reference_for_block(block)
            
            elif isinstance(attr_value, Block):
                block = attr_value
                self.fill_block_reference_for_block(block)

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
