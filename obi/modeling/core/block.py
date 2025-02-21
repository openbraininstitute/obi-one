from pydantic import BaseModel, PrivateAttr

class Block(BaseModel):
    """
    """
    _multi_params: dict = PrivateAttr(default={})
    
    def multi_params(self, category_name, block_key='') -> dict:
        
        """
        Iterate through all attributes of the Block
        """
        for key, value in self.__dict__.items():
            if isinstance(value, list) and len(value) > 1:

                if block_key != '':
                    self._multi_params[f"{category_name}.{block_key}.{key}"] = {
                        "coord_param_keys": [category_name, block_key, key],
                        "coord_param_values": value
                    }
                else:
                    self._multi_params[f"{category_name}.{key}"] = {
                        "coord_param_keys": [category_name, key],
                        "coord_param_values": value
                    }

        return self._multi_params
    
    def enforce_no_lists(self):
        """
        Raise a ValueError if any attribute is a list.
        """
        for key, value in self.__dict__.items():
            if isinstance(value, list):
                raise ValueError(f"Attribute '{key}' must not be a list.")