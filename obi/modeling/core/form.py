from pydantic import BaseModel, field_validator, PrivateAttr
from obi.modeling.core.block import Block

class Form(BaseModel):
    """
    """
    _multi_params: dict = PrivateAttr(default={})
    _sonata_config: dict = PrivateAttr(default={})

    _single_coord_class_name: str = ""

    def single_coord_class(self):
        module = __import__(self.__module__)
        return getattr(module, self._single_coord_class_name)
    
    
    @property
    def multi_params(self) -> dict:
        
        """
        Iterate through all attributes of the Form
        """
        for attr_name, attr_value in self.__dict__.items():

            """
            Check if the attribute is a dictionary of Block instances
            """
            if isinstance(attr_value, dict) and all(isinstance(dict_val, Block) for dict_key, dict_val in attr_value.items()):

                category_name = attr_name; category_blocks_dict = attr_value
                
                """
                If so iterate through the dictionary's Block instances
                """
                for block_key, block in category_blocks_dict.items():

                    """
                    Call the multi_params method of the Block instance
                    """                    
                    self._multi_params.update(block.multi_params(category_name=category_name, block_key=block_key))


            """
            Else if the attribute is a Block instance, call the multi_params method of the Block instance
            """
            if isinstance(attr_value, Block):
                category_name = attr_name
                category_block = attr_value
                self._multi_params.update(category_block.multi_params(category_name=category_name))

                            
        return self._multi_params
        
    
    def cast_to_single_instance(self):
        class_to_cast_to = self.single_coord_class()
        single_instance = class_to_cast_to.model_construct(**self.__dict__)
        return single_instance
    

class SingleTypeMixin:
    """Mixin to enforce no lists in all Blocks and Blocks in Category dictionaries."""

    @field_validator("*", mode="before")
    @classmethod
    def enforce_single_type(cls, value):

        if isinstance(value, dict):  # Check for nested dictionaries containing Block instances
            for key, dict_value in value.items():
                if isinstance(dict_value, Block):  # Recursively validate Block objects
                    block = dict_value
                    block.enforce_no_lists()
                        
        if isinstance(value, Block):  # Validate Block objects
            block = value
            value.enforce_no_lists()
                
        return value
    
