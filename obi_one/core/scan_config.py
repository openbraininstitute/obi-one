import types
from typing import ClassVar, get_args, get_origin

import entitysdk
from pydantic import model_validator

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference
from obi_one.core.exception import OBIONEError
from obi_one.scientific.unions.block_references import AllBlockReferenceTypes


def get_all_annotations(cls: type) -> dict[str, type]:
    """Collect annotations from a class and all its parent classes."""
    annotations = {}
    for base in reversed(cls.__mro__):  # reversed so base class first, then subclasses override
        annotations.update(getattr(base, "__annotations__", {}))
    return annotations


class ScanConfig(OBIBaseModel, extra="forbid"):
    """A ScanConfig is a configuration for single or multi-dimensional parameter scans.

    A ScanConfig is composed of Blocks, which either appear at the root level
    or within dictionaries of Blocks where the dictionary is takes a Union of Block types.
    """

    name: ClassVar[str] = "Add a name class' name variable"
    description: ClassVar[str] = """Add a description to the class' description variable"""
    single_coord_class_name: ClassVar[str] = ""

    _block_mapping: dict = None

    _campaign: None = None

    @property
    def campaign(
        self,
    ) -> (
        entitysdk.models.SimulationCampaign | None
    ):  # Would be better to be "Entity | None" but Entity not currently exposed by entitysdk
        return self._campaign

    @classmethod
    def empty_config(cls) -> "ScanConfig":
        # Here you use model_construct or build custom behavior
        return cls.model_construct()

    def validated_config(self) -> "ScanConfig":
        return self.__class__.model_validate(self.model_dump())

    @property
    def block_mapping(self) -> dict:
        """Returns a mapping of block class names to block_dict_name and reference_type."""
        if self._block_mapping is None:
            # Get type annotations of the instance's class
            annotations = get_all_annotations(self.__class__)

            # Initialize an empty mapping
            self._block_mapping = {}

            # Iterate through the ScanConfig's attributes
            for attr_name, attr_value in self.__dict__.items():
                # Get the annotated type of this attribute
                # i.e. dict[str, typing.Annotated[SingleTimestamp | ...)
                annotated_type = annotations.get(attr_name)

                # Check if it's a dictionary of Block instances
                if (
                    isinstance(attr_value, dict)
                    and all(isinstance(v, Block) for v in attr_value.values())
                    and annotated_type is not None
                    and get_origin(annotated_type) is dict
                ):
                    # Check that the attribute has a variable: reference_type
                    field_info = self.__pydantic_fields__[attr_name]
                    if (
                        field_info.json_schema_extra
                        and "reference_type" in field_info.json_schema_extra
                    ):
                        reference_type = field_info.json_schema_extra["reference_type"]
                    else:
                        msg = (
                            f"Attribute '{attr_name}' does not have a 'reference_type'"
                            " in json_schema_extra."
                        )
                        raise ValueError(msg)

                    # Get the type of the dictionary's values
                    # i.e. typing.Annotated[SingleTimestamp | ...
                    dictionary_value_type = get_args(annotated_type)[1]

                    # Get the value inside the annotation
                    # i.e. SingleTimestamp | ... OR SingleTimestamp
                    inside_annotation_type = get_args(dictionary_value_type)[0]

                    # Create a list of classes inside the annotation
                    # If it's a Union, get all classes inside it
                    # Otherwise, just use the single class
                    if isinstance(inside_annotation_type, types.UnionType):
                        classes = list(get_args(inside_annotation_type))
                    else:
                        classes = [inside_annotation_type]

                    # Iterate through the classes and add them to the mapping
                    for block_class in classes:
                        # If the block class is already in the mapping, raise an error
                        if block_class.__name__ in self._block_mapping:
                            msg = (
                                f"Block class {block_class.__name__} already exists in the mapping."
                                " This suggests that the same block class is used in multiple"
                                " dictionaries."
                            )
                            raise ValueError(msg)

                        # Otherwise initialize a new dictionary for this block class in the mapping
                        self._block_mapping[block_class.__name__] = {
                            "block_dict_name": attr_name,
                            "reference_type": reference_type,
                        }

        return self._block_mapping

    def fill_block_reference_for_block(self, block: Block) -> None:
        """Fill the block reference with the actual Block object it references."""
        for block_attr_value in block.__dict__.values():
            # If the Block instance has a `BlockReference` attribute,
            # set it to the object it references
            if isinstance(block_attr_value, BlockReference):
                block_reference = block_attr_value

                if block_reference.block_dict_name and block_reference.block_name:
                    block_reference.block = self.__dict__[block_reference.block_dict_name][
                        block_reference.block_name
                    ]
                elif not block_reference.block_dict_name and block_reference.block_name:
                    # If the block_dict_name is empty, we assume the block_name
                    # is a direct reference to a Block instance
                    if block_reference.block_name == "neuron_set_extra":
                        block_reference.block = self.__dict__[block_reference.block_name]
                else:
                    msg = "BlockReference must have a non-empty block_dict_name and block_name."
                    raise ValueError(msg)

    @model_validator(mode="after")
    def fill_block_references_and_names(self) -> "ScanConfig":
        for attr_value in self.__dict__.values():
            # Check if the attribute is a dictionary of Block instances
            if isinstance(attr_value, dict) and all(
                isinstance(dict_val, Block) for dict_key, dict_val in attr_value.items()
            ):
                category_blocks_dict = attr_value

                # If so iterate through the dictionary's Block instances
                for key, block in category_blocks_dict.items():
                    self.fill_block_reference_for_block(block)
                    block.set_block_name(key)

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

    def add(self, block: Block, name: str = "") -> None:
        block_dict_name = self.block_mapping[block.__class__.__name__]["block_dict_name"]
        reference_type_name = self.block_mapping[block.__class__.__name__]["reference_type"]

        if name in self.__dict__.get(block_dict_name):
            msg = f"Block with name '{name}' already exists in '{block_dict_name}'!"
            raise OBIONEError(msg)

        # Find the class in AllReferenceTypes whose name matches reference_type_name
        reference_type = next(
            (cls for cls in AllBlockReferenceTypes if cls.__name__ == reference_type_name),
            None,
        )
        if reference_type is None:
            msg = f"Reference type '{reference_type_name}' not found in AllReferenceTypes."
            raise OBIONEError(msg)

        ref = reference_type(block_dict_name=block_dict_name, block_name=name)
        block.set_ref(ref)
        block.set_block_name(name)
        self.__dict__[block_dict_name][name] = block

    def set(self, block: Block, name: str = "") -> None:
        """Sets a block in the form."""
        self.__dict__[name] = block
