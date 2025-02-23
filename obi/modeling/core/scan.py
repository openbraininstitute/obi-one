from pydantic import BaseModel, PrivateAttr, ValidationError
from .form import Form, Block

import os, copy, json
class Scan(BaseModel):

    form: Form = None
    _multiple_value_parameters: dict = PrivateAttr(default={})
    _coords = PrivateAttr(default=[])
    _coordinate_instances: list = PrivateAttr(default=[])


    @property
    def multiple_value_parameters(self) -> dict:
        
        """
        Iterate through all attributes of the Form
        """
        for attr_name, attr_value in self.form.__dict__.items():

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
                    Call the multiple_value_parameters method of the Block instance
                    """                    
                    self._multiple_value_parameters.update(block.multiple_value_parameters(category_name=category_name, block_key=block_key))


            """
            Else if the attribute is a Block instance, call the multiple_value_parameters method of the Block instance
            """
            if isinstance(attr_value, Block):
                category_name = attr_name
                category_block = attr_value
                self._multiple_value_parameters.update(category_block.multiple_value_parameters(category_name=category_name))

                            
        return self._multiple_value_parameters

    @property
    def coordinate_instances(self) -> list[Form]:

        if len(self._coordinate_instances) > 0: return self._coordinate_instances

        for coord in self.coordinate_parameters():

            coord_form = copy.deepcopy(self.form)
            
            for param in list(coord):
                
                keys = param[0]
                val = param[1]

                level_0_val = coord_form.__dict__[keys[0]]

                if isinstance(level_0_val, Block):
                    level_0_val.__dict__[keys[1]] = val

                if isinstance(level_0_val, dict):
                    level_1_val = level_0_val[keys[1]]
                    if isinstance(level_1_val, Block):
                        level_1_val.__dict__[keys[2]] = val
                    else:
                        # This should already by checked elsewhere (in future, if not done already)
                        print("Validation Error:", "Non Block options should not be used here.")  
    
            try:
                coord_instance = coord_form.cast_to_single_coord()
                self._coordinate_instances.append(coord_instance)
                
            except ValidationError as e:
                print("Validation Error:", e)

        return self._coordinate_instances
    

    def write_configs(self, output_dir, prefix="simulation_config_"):

        os.makedirs(output_dir, exist_ok=True)
        for idx, coord_instance in enumerate(self.coordinate_instances):
            config = coord_instance.generate_config()

            config_path = os.path.join(output_dir, f"{prefix}{idx}.json")
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)


from itertools import product
class GridScan(Scan):

    def coordinate_parameters(self) -> list:

        all_tuples = []
        for key, value in self.multiple_value_parameters.items():
            tups = []
            for k, v in zip([value["coord_param_keys"] for i in range(len(value['coord_param_values']))], value['coord_param_values']):
                tups.append((k, v))

            all_tuples.append(tups)

        coords = [coord for coord in product(*all_tuples)]

        return coords


class CoupledScan(Scan):

    def coordinate_parameters(self) -> list:
        previous_len = None
        for key, value in self.multiple_value_parameters.items():

            current_len = len(value['coord_param_values'])
            if previous_len is not None and current_len != previous_len:
                raise ValueError("All multi-parameters must have the same number of values.")

            previous_len = current_len

        n_coords = current_len

        coords = []
        for coord_i in range(n_coords):
            coupled_coord = []
            for key, value in self.multiple_value_parameters.items():
                coupled_coord.append((value["coord_param_keys"], value["coord_param_values"][coord_i]))

            coords.append(tuple(coupled_coord))

        return coords
