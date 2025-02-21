from pydantic import BaseModel, field_validator, PrivateAttr
from itertools import product

from obi.modeling.core.block import Block

class Form(BaseModel):
    """
    """
    _multi_params: dict = PrivateAttr(default={})
    _sonata_config: dict = PrivateAttr(default={})
    
    
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


    def generate_grid_scan_coords(self) -> list:

        all_tuples = []
        for key, value in self.multi_params.items():
            tups = []
            for k, v in zip([value["coord_param_keys"] for i in range(len(value['coord_param_values']))], value['coord_param_values']):
                tups.append((k, v))

            all_tuples.append(tups)

        coords = [coord for coord in product(*all_tuples)]

        return coords
    
    def generate_coupled_scan_coords(self) -> list:
        previous_len = None
        for key, value in self.multi_params.items():

            current_len = len(value['coord_param_values'])
            if previous_len is not None and current_len != previous_len:
                raise ValueError("All multi-parameters must have the same number of values.")

            previous_len = current_len

        n_coords = current_len

        coords = []
        for coord_i in range(n_coords):
            coupled_coord = []
            for key, value in self.multi_params.items():
                coupled_coord.append((value["coord_param_keys"], value["coord_param_values"][coord_i]))

            coords.append(tuple(coupled_coord))

        return coords


    
    def cast_to_single_instance(self):
        class_to_cast_to = self.single_version_class()
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
    
