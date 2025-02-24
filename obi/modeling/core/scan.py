from pydantic import BaseModel, PrivateAttr, ValidationError
from .form import Form, Block

import os, copy, json
class Scan(BaseModel):

    form: Form = None
    _multiple_value_parameters: dict = PrivateAttr(default={})
    _coordinate_parameters: list = PrivateAttr(default=[])
    _coordinate_instances: list = PrivateAttr(default=[])


    # @property
    def multiple_value_parameters(self, display=False) -> dict:
        

        self._multiple_value_parameters = {}

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

                            
        if display:
            print("\nMULTIPLE VALUE PARAMETERS")
            for k, d in self._multiple_value_parameters.items():
                print(f"{k}: {d['coord_param_values']}")

        return self._multiple_value_parameters


    def display_coordinate_parameters(self):
 
        print("\nCOORDINATE PARAMETERS")

        for single_coordinate_parameters in self._coordinate_parameters:
            output = f""
            for j, parameter in enumerate(single_coordinate_parameters):
                
                for i, s in enumerate(parameter[0]):
                    output = output + f"{s}"
                    if i < len(parameter[0]) - 1:
                        output = output + "."

                output = output + ": " + str(parameter[1])
                if j < len(single_coordinate_parameters) - 1:
                    output = output + ", "
            print(output)


    def coordinate_instances(self, display=False) -> list[Form]:

        self._coordinate_instances = []

        for single_coordinate_parameters in self.coordinate_parameters():

            single_coordinate_form = copy.deepcopy(self.form)
            
            for param in list(single_coordinate_parameters):
                
                keys = param[0]
                val = param[1]

                level_0_val = single_coordinate_form.__dict__[keys[0]]

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
                coordinate_instance = single_coordinate_form.cast_to_single_coord()
                self._coordinate_instances.append(coordinate_instance)
                
            except ValidationError as e:
                print("Validation Error:", e)

        if display: 
            print("\nCOORDINATE INSTANCES")
            for coordinate_instance in self._coordinate_instances:
                print(coordinate_instance)

        return self._coordinate_instances
    

    def generate(self, output_dir):

        os.makedirs(output_dir, exist_ok=True)
        for idx, coordinate_instance in enumerate(self.coordinate_instances()):
            coordinate_instance.generate(output_dir, idx=idx)

    # def run(self, output_dir, prefix="")



from itertools import product
class GridScan(Scan):

    def coordinate_parameters(self, display=False) -> list:

        all_tuples = []
        for key, value in self.multiple_value_parameters().items():
            tups = []
            for k, v in zip([value["coord_param_keys"] for i in range(len(value['coord_param_values']))], value['coord_param_values']):
                tups.append((k, v))

            all_tuples.append(tups)

        self._coordinate_parameters = [coord for coord in product(*all_tuples)]
        
        if display: self.display_coordinate_parameters()

        return self._coordinate_parameters


class CoupledScan(Scan):

    def coordinate_parameters(self, display=False) -> list:
        previous_len = None
        for key, value in self.multiple_value_parameters().items():

            current_len = len(value['coord_param_values'])
            if previous_len is not None and current_len != previous_len:
                raise ValueError("All multi-parameters must have the same number of values.")

            previous_len = current_len

        n_coords = current_len

        self._coordinate_parameters = []
        for coord_i in range(n_coords):
            coupled_coord = []
            for key, value in self.multiple_value_parameters().items():
                coupled_coord.append((value["coord_param_keys"], value["coord_param_values"][coord_i]))

            self._coordinate_parameters.append(tuple(coupled_coord))

        if display: self.display_coordinate_parameters()

        return self._coordinate_parameters
