from pydantic import PrivateAttr, ValidationError
from obi.modeling.core.form import Form, Block
from obi.modeling.core.base import OBIBaseModel
from obi.modeling.core.form import nested_param_short
from importlib.metadata import version
import os, copy, json
from collections import OrderedDict

class Scan(OBIBaseModel):

    form: Form
    output_root: str
    _multiple_value_parameters: dict = PrivateAttr(default={})
    _coordinate_parameters: list = PrivateAttr(default=[])
    _coordinate_instances: list = PrivateAttr(default=[])

    def multiple_value_parameters(self, display=False) -> dict:
        
        self._multiple_value_parameters = {}

        # Iterate through all attributes of the Form
        for attr_name, attr_value in self.form.__dict__.items():

            # Check if the attribute is a dictionary of Block instances
            if isinstance(attr_value, dict) and all(isinstance(dict_val, Block) for dict_key, dict_val in attr_value.items()):

                category_name = attr_name; category_blocks_dict = attr_value
                
                # If so iterate through the dictionary's Block instances
                for block_key, block in category_blocks_dict.items():

                    # Call the multiple_value_parameters method of the Block instance
                    self._multiple_value_parameters.update(block.multiple_value_parameters(category_name=category_name, block_key=block_key))


            # Else if the attribute is a Block instance, call the multiple_value_parameters method of the Block instance
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
                
                output = nested_param_short(parameter[0])
                output = output + ": " + str(parameter[1])
                if j < len(single_coordinate_parameters) - 1:
                    output = output + ", "
            print(output)


    def coordinate_instances(self, display=False) -> list[Form]:

        self._coordinate_instances = []

        for idx, single_coordinate_parameters in enumerate(self.coordinate_parameters()):

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
                        raise ValueError("Non Block options should not be used here.")
    
            try:
                coordinate_instance = single_coordinate_form.cast_to_single_coord()
                coordinate_instance.idx = idx
                coordinate_instance.coordinate_parameters = single_coordinate_parameters
                self._coordinate_instances.append(coordinate_instance)
                
            except ValidationError as e:
                raise ValidationError(e)

        if display: 
            print("\nCOORDINATE INSTANCES")
            for coordinate_instance in self._coordinate_instances:
                print(coordinate_instance)

        return self._coordinate_instances
    
    def generate(self):

        os.makedirs(self.output_root, exist_ok=True)
        for coordinate_instance in self.coordinate_instances():

            if hasattr(coordinate_instance, 'generate'):
                coordinate_instance.scan_output_root = self.output_root
                coordinate_instance.generate()
                coordinate_instance.dump_coordinate_instance_to_json_with_package_version(os.path.join(coordinate_instance.coordinate_output_root, "generate_coordinate_instance.json"))
            else:
                raise NotImplementedError(f"Function \"generate\" not implemented for type:{type(coordinate_instance)}")

        self.dump_scan_to_json_with_package_version(os.path.join(self.output_root, "generate_scan_config.json"))
        self.create_bbp_workflow_campaign_config(os.path.join(self.output_root, "bbp_workflow_campaign_config.json"))

    def run(self):

        for coordinate_instance in self.coordinate_instances():
            if hasattr(coordinate_instance, 'run'):
                coordinate_instance.scan_output_root = self.output_root
                coordinate_instance.run()
                coordinate_instance.dump_coordinate_instance_to_json_with_package_version(os.path.join(coordinate_instance.coordinate_output_root, "run_coordinate_instance.json"))
            else:
                raise NotImplementedError(f"Function \"run\" function not implemented for type:{type(coordinate_instance)}")

        self.dump_scan_to_json_with_package_version(os.path.join(self.output_root, "run_scan_config.json"))
        self.create_bbp_workflow_campaign_config(os.path.join(self.output_root, "bbp_workflow_campaign_config.json"))

    def generate_and_run(self):
        self.generate()
        self.run()


    def dump_scan_to_json_with_package_version(self, output_path):
   
        model_dump = self.model_dump(serialize_as_any=True)
        model_dump["obi_version"] = version("obi")

        model_dump["form"]

        model_dump = OrderedDict(model_dump)

        model_dump.move_to_end('output_root', last=False)
        model_dump.move_to_end('obi_class', last=False)
        model_dump.move_to_end('obi_version', last=False)

        model_dump["form"] = OrderedDict(model_dump["form"])
        model_dump["form"].move_to_end('obi_class', last=False)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as json_file:
            json.dump(model_dump, json_file, indent=4)


    def create_bbp_workflow_campaign_config(self, output_path):

        campaign_config = {
            "dims": [],
            "attrs": {},
            "data": [],
            "coords": {},
            "name": ""
        }

        campaign_config['dims'] = [param_key for param_key in self.multiple_value_parameters()]


        for param_key, param_dict in self.multiple_value_parameters().items():

            sub_d = {param_key: {
                                    "dims": [param_key],
                                    "attrs": {},
                                    "data": param_dict["coord_param_values"]
                                 }
                    }

            campaign_config["coords"].update(sub_d)

            campaign_config["data"] = [[["a", "b"], ["c", "d"]], [["e", "f"], ["g", "h"]]]


        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as json_file:
            json.dump(campaign_config, json_file, indent=4)



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
