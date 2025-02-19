from typing import Any, List, Union, Dict
from pydantic import BaseModel, ValidationError, field_validator, PrivateAttr

from itertools import product
class MultiTemplate(BaseModel):
    """
    """
    _multi_params: dict = PrivateAttr(default={})  # Private storage
    _sonata_config: dict = PrivateAttr(default={})
    
    
    @property
    def multi_params(self) -> dict:
        
        for attr_name, attr_value in self.__dict__.items():

            if isinstance(attr_value, dict) and all(isinstance(dict_val, MultiTemplate) for dict_key, dict_val in attr_value.items()):
                for dict_key, dict_val in attr_value.items():
                    for key, value in dict_val.__dict__.items():
                        if not isinstance(value, BaseModel) and isinstance(value, list) and len(value) > 1:
                            self._multi_params[f"{attr_name}.{dict_key}.{key}"] = {
                                "coord_param_keys": [attr_name, dict_key, key],
                                "coord_param_values": value
                            }
                            
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
    
    def cast_to_single_instance(self):
        class_to_cast_to = self.single_version_class()
        single_instance = class_to_cast_to.model_validate(self.model_dump())
        return single_instance
    

class SingleTypeMixin:
    """Mixin to enforce only single float values for all fields."""

    @field_validator("*", mode="before")
    @classmethod
    def enforce_single_type(cls, value):
        """Ensure all fields contain only single floats (no lists)."""

        # print("enforce_single_type", value)

        if isinstance(value, list):
            raise ValueError("Lists are not allowed for this class.")
        if isinstance(value, dict):  # Check for nested dictionaries containing BaseModel instances
            for key, dict_value in value.items():
                if isinstance(dict_value, BaseModel):  # Recursively validate BaseModel objects
                    for field, field_value in dict_value.model_dump().items():
                        if isinstance(field_value, list):
                            raise ValueError(f"Nested dictionary attribute '{key}.{field}' must not be a list.")
        if isinstance(value, BaseModel):  # Validate Pydantic objects
            for field, field_value in value.model_dump().items():
                if isinstance(field_value, list):
                    raise ValueError(f"Nested attribute '{field}' must not be a list.")
                
        return value