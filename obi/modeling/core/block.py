from pydantic import PrivateAttr
from obi.modeling.core.base import OBIBaseModel
from typing import Any


def nested_param_short(nested_param_list):
    nested_param_short = ''
    for i, s in enumerate(nested_param_list):
        nested_param_short = nested_param_short + f"{s}"
        if i < len(nested_param_list) - 1:
            nested_param_short = nested_param_short + '.'
    return nested_param_short

class MultiValueLocationPair(OBIBaseModel):
    location_list: list = []
    multi_values: list[Any] = [None]
    location_str: str = ""

    def __init__(self, **data):
        super().__init__(**data)
        self.location_str = nested_param_short(self.location_list)

    # def __init__(self):
    #     

    # self.location_str = nested_param_short(location_list)



class Block(OBIBaseModel):
    """
    """
    # _multiple_value_parameters: dict = PrivateAttr(default={})
    _multiple_value_parameters: list[MultiValueLocationPair] = PrivateAttr(default=[])
    
    # def multiple_value_parameters(self, category_name, block_key='') -> dict:
        
    #     # Iterate through all attributes of the Block
    #     for key, value in self.__dict__.items():
    #         if isinstance(value, list) and len(value) > 1:

    #             if block_key != '':
    #                 self._multiple_value_parameters[f"{category_name}.{block_key}.{key}"] = {
    #                     "coord_param_keys": [category_name, block_key, key],
    #                     "coord_param_values": value
    #                 }
    #             else:
    #                 self._multiple_value_parameters[f"{category_name}.{key}"] = {
    #                     "coord_param_keys": [category_name, key],
    #                     "coord_param_values": value
    #                 }

    #     return self._multiple_value_parameters



    def multiple_value_parameters(self, category_name, block_key='') -> list[MultiValueLocationPair]:

        
        for key, value in self.__dict__.items():

            if isinstance(value, list) and len(value) > 1:
                multi_values = value
                if block_key != '':
                    self._multiple_value_parameters.append(MultiValueLocationPair(multi_values=multi_values, location_list=[category_name, block_key, key]))
                else:
                    self._multiple_value_parameters.append(MultiValueLocationPair(multi_values=multi_values, location_list=[category_name, key]))

        return self._multiple_value_parameters

    
    def enforce_no_lists(self):
        """
        Raise a ValueError if any attribute is a list.
        """
        for key, value in self.__dict__.items():
            if isinstance(value, list):
                raise ValueError(f"Attribute '{key}' must not be a list.")
