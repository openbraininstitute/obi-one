from pydantic import PrivateAttr
from obi_one.modeling.core.base import OBIBaseModel
from typing import Any


def nested_param_short(nested_param_list):
    nested_param_short = ''
    for i, s in enumerate(nested_param_list):
        nested_param_short = nested_param_short + f"{s}"
        if i < len(nested_param_list) - 1:
            nested_param_short = nested_param_short + '.'
    return nested_param_short


class ScanParam(OBIBaseModel):
    location_list: list = []
    _location_str: str = ""

    @property
    def location_str(self):
        return nested_param_short(self.location_list)

class MultiValueScanParam(ScanParam):
    values: list[Any] = [None]
    
class SingleValueScanParam(ScanParam):
    value: Any


class Block(OBIBaseModel):
    """
    """
    _multiple_value_parameters: list[MultiValueScanParam] = PrivateAttr(default=[])
    
    def multiple_value_parameters(self, category_name, block_key='') -> list[MultiValueScanParam]:

        self._multiple_value_parameters = []
        
        for key, value in self.__dict__.items():

            if isinstance(value, list): # and len(value) > 1:
                multi_values = value
                if block_key != '':
                    self._multiple_value_parameters.append(MultiValueScanParam(location_list=[category_name, block_key, key], values=multi_values))
                else:
                    self._multiple_value_parameters.append(MultiValueScanParam(location_list=[category_name, key], values=multi_values))

        return self._multiple_value_parameters

    
    def enforce_no_lists(self):
        """
        Raise a ValueError if any attribute is a list.
        """
        for key, value in self.__dict__.items():
            if isinstance(value, list):
                raise ValueError(f"Attribute '{key}' must not be a list.")
