from pydantic import BaseModel, PrivateAttr
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
                                "simulation_param_keys": [attr_name, dict_key, key],
                                "simulation_param_values": value
                            }
                            
        return self._multi_params


    def generate_grid_scan_coords(self) -> list:

        all_tuples = []
        for key, value in self.multi_params.items():
            tups = []
            for k, v in zip([value["simulation_param_keys"] for i in range(len(value['simulation_param_values']))], value['simulation_param_values']):
                tups.append((k, v))

            all_tuples.append(tups)

        coords = [coord for coord in product(*all_tuples)]
        return coords