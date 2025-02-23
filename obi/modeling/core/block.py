from pydantic import BaseModel, PrivateAttr

class Block(BaseModel):
    """
    """
    _multiple_value_parameters: dict = PrivateAttr(default={})
    
    def multiple_value_parameters(self, category_name, block_key='') -> dict:
        
        """
        Iterate through all attributes of the Block
        """
        for key, value in self.__dict__.items():
            if isinstance(value, list) and len(value) > 1:

                if block_key != '':
                    self._multiple_value_parameters[f"{category_name}.{block_key}.{key}"] = {
                        "coord_param_keys": [category_name, block_key, key],
                        "coord_param_values": value
                    }
                else:
                    self._multiple_value_parameters[f"{category_name}.{key}"] = {
                        "coord_param_keys": [category_name, key],
                        "coord_param_values": value
                    }

        return self._multiple_value_parameters
    
    def enforce_no_lists(self):
        """
        Raise a ValueError if any attribute is a list.
        """
        for key, value in self.__dict__.items():
            if isinstance(value, list):
                raise ValueError(f"Attribute '{key}' must not be a list.")