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


class ScanParameter(OBIBaseModel):
    location_list: list = []
    location_str: str = ""

    def __init__(self, **data):
        super().__init__(**data)
        self.location_str = nested_param_short(self.location_list)

class MultiValueScanParameter(ScanParameter):
    values: list[Any] = [None]
    
class SingleValueScanParameter(ScanParameter):
    value: Any


class Block(OBIBaseModel):
    """
    """
    _multiple_value_parameters: list[MultiValueScanParameter] = PrivateAttr(default=[])
    
    def multiple_value_parameters(self, category_name, block_key='') -> list[MultiValueScanParameter]:

        self._multiple_value_parameters = []
        
        for key, value in self.__dict__.items():

            if isinstance(value, list) and len(value) > 1:
                multi_values = value
                if block_key != '':
                    self._multiple_value_parameters.append(MultiValueScanParameter(location_list=[category_name, block_key, key], values=multi_values))
                else:
                    self._multiple_value_parameters.append(MultiValueScanParameter(location_list=[category_name, key], values=multi_values))

        return self._multiple_value_parameters

    
    def enforce_no_lists(self):
        """
        Raise a ValueError if any attribute is a list.
        """
        for key, value in self.__dict__.items():
            if isinstance(value, list):
                raise ValueError(f"Attribute '{key}' must not be a list.")
