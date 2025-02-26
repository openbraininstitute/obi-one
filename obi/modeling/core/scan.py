from pydantic import PrivateAttr, ValidationError
from obi.modeling.core.form import Form
from obi.modeling.core.single import SingleTypeMixin, SingleCoordinateScanParameters
from obi.modeling.core.block import Block, MultiValueScanParameter, SingleValueScanParameter
from obi.modeling.core.base import OBIBaseModel
from importlib.metadata import version
import os, copy, json
from collections import OrderedDict

"""
Scan class:
- Takes a Form & output_root as input

- Has several intermediate functions for computing a multi-dimensional parameter scan:
    - multiple_value_parameters()
    - coordinate_parameters()
    - coordinate_instances()

- Creates a multi-dimensional parameter scan through calls to:
    - generate(), 
    - run() 
    - generate_and_run()

- Within the multi-dimensional parameter scan...
"""
class Scan(OBIBaseModel):

    form: Form
    output_root: str
    _multiple_value_parameters: list = None
    _coordinate_parameters: list = PrivateAttr(default=[])
    _coordinate_instances: list = PrivateAttr(default=[])


    """
    Multi value parameters:
    - Iterates through the Blocks of self.form to find "multi value parameters" 
        (i.e. parameters with list values of length greater than 1).
        
    - Rewrite description
    """
    def multiple_value_parameters(self, display=False) -> list[MultiValueScanParameter]:
        
        self._multiple_value_parameters = []

        # Iterate through all attributes of the Form
        for attr_name, attr_value in self.form.__dict__.items():

            # Check if the attribute is a dictionary of Block instances
            if isinstance(attr_value, dict) and all(isinstance(dict_val, Block) for dict_key, dict_val in attr_value.items()):

                category_name = attr_name; category_blocks_dict = attr_value
                
                # If so iterate through the dictionary's Block instances
                for block_key, block in category_blocks_dict.items():

                    # Call the multiple_value_parameters method of the Block instance
                    block_multi_value_parameters = block.multiple_value_parameters(category_name=category_name, block_key=block_key)
                    if len(block_multi_value_parameters): self._multiple_value_parameters.extend(block_multi_value_parameters)


            # Else if the attribute is a Block instance, call the _multiple_value_parameters method of the Block instance
            if isinstance(attr_value, Block):
                block_name = attr_name
                block = attr_value
                block_multi_value_parameters = block.multiple_value_parameters(category_name=block_name)
                if len(block_multi_value_parameters): self._multiple_value_parameters.extend(block_multi_value_parameters)

        # Optionally display the multiple_value_parameters             
        if display:
            print("\nMULTIPLE VALUE PARAMETERS")
            for multi_value in self._multiple_value_parameters:
                print(f"{multi_value.location_str}: {multi_value.values}")

        # Return the multiple_value_parameters
        return self._multiple_value_parameters


    """
    Coordinate parameters
    - Must be implemented by a subclass of Scan

    - Rewrite description
    """
    def coordinate_parameters(self, display=False) -> list:
        raise NotImplementedError("Subclasses must implement this method")


    """
    Coordinate instance
    - Returns a list of "coordinate instances" by:
        - Iterating through self.coordinate_parameters()
        - Creating a single "coordinate instance" for each single coordinate parameter

    - Each "coordinate instance" is created by:
        - Making a deep copy of the form
        - Editing the multi value parameters (lists) to have the values of the single coordinate parameters
            (i.e. timestamps.timestamps_1.interval = [1.0, 5.0] -> timestamps.timestamps_1.interval = 1.0)
        - Casting the form to its _single_coord_class_name type 
            (i.e. SimulationsForm -> Simulation)
    """
    def coordinate_instances(self, display=False) -> list[Form]:

        self._coordinate_instances = []

        # Iterate through coordinate_parameters
        for idx, single_coordinate_scan_parameters in enumerate(self.coordinate_parameters()):

            # Make a deep copy of self.form
            single_coordinate_form = copy.deepcopy(self.form)
            
            # Iterate through the parameters in the single_coordinate_parameters tuple
            # Change the value of the multi parameter from a list to the single value of the coordinate
            for single_value_scan_parameter in single_coordinate_scan_parameters.single_value_scan_parameters_list:

                level_0_val = single_coordinate_form.__dict__[single_value_scan_parameter.location_list[0]]

                # If the first level is a Block
                if isinstance(level_0_val, Block):
                    level_0_val.__dict__[single_value_scan_parameter.location_list[1]] = single_value_scan_parameter.value

                # If the first level is a category dictionary
                if isinstance(level_0_val, dict):
                    level_1_val = level_0_val[single_value_scan_parameter.location_list[1]]
                    if isinstance(level_1_val, Block):
                        level_1_val.__dict__[single_value_scan_parameter.location_list[2]] = single_value_scan_parameter.value
                    else:
                        raise ValueError("Non Block options should not be used here.")
    
            try:
                # Cast the form to its _single_coord_class_name type
                coordinate_instance = single_coordinate_form.cast_to_single_coord()

                # Set the variables of the coordinate instance related to the scan
                coordinate_instance.idx = idx
                coordinate_instance.single_coordinate_scan_parameters = single_coordinate_scan_parameters

                # Append the coordinate instance to self._coordinate_instances
                self._coordinate_instances.append(coordinate_instance)
                
            except ValidationError as e:
                raise ValidationError(e)

        # Optionally display the coordinate instances
        if display: 
            print("\nCOORDINATE INSTANCES")
            for coordinate_instance in self._coordinate_instances:
                print(coordinate_instance)

        # Return self._coordinate_instances
        return self._coordinate_instances
    

    """
    Generate
    - Checks if generate() implemented for the coordinate_instances
    - Calls generate() for each instance of self.coordinate_instances()
    - Serializes each instance to json
    - Serializes the Scan
    - Create a bbp_workflow_campaign_config
    """
    def generate(self):

        # Iterate through self.coordinate_instances()
        for coordinate_instance in self.coordinate_instances():

            # Check if coordinate instance has function "generate"
            if hasattr(coordinate_instance, 'generate'):

                # Set scan_output_root
                coordinate_instance.scan_output_root = self.output_root

                # Call the coordinate_instance's generate() function
                coordinate_instance.generate()

                # # Serialize the coordinate instance
                # coordinate_instance.serialize(os.path.join(coordinate_instance.coordinate_output_root, "generate_coordinate_instance.json"))

            else:
                # Raise an error if generate() not implemented for the coordinate instance
                raise NotImplementedError(f"Function \"generate\" not implemented for type:{type(coordinate_instance)}")

        # Serialize the scan
        self.serialize(os.path.join(self.output_root, "generate_scan_config.json"))

        # Create a bbp_workflow_campaign_config
        self.create_bbp_workflow_campaign_config(os.path.join(self.output_root, "bbp_workflow_campaign_config.json"))

    """
    Run
    - Checks if run() implemented for the coordinate_instances
    - Calls run() for each instance of self.coordinate_instances()
    - Serializes each instance to json
    - Serializes the Scan
    - Create a bbp_workflow_campaign_config
    """  
    def run(self):

        # Iterate through self.coordinate_instances()
        for coordinate_instance in self.coordinate_instances():

            # Check if coordinate instance has function "run"
            if hasattr(coordinate_instance, 'run'):

                # Set scan_output_root
                coordinate_instance.scan_output_root = self.output_root

                # Call the coordinate_instance's run() function
                coordinate_instance.run()

                # Serialize the coordinate instance
                coordinate_instance.serialize(os.path.join(coordinate_instance.coordinate_output_root, "run_coordinate_instance.json"))

            else:
                 # Raise an error if run() not implemented for the coordinate instance
                raise NotImplementedError(f"Function \"run\" function not implemented for type:{type(coordinate_instance)}")

        # Serialize the scan
        self.serialize(os.path.join(self.output_root, "run_scan_config.json"))

        # Create a bbp_workflow_campaign_config
        self.create_bbp_workflow_campaign_config(os.path.join(self.output_root, "bbp_workflow_campaign_config.json"))

    
    """
    Serializes the scan, by:
    - Calling model_dump (returns model_dump dict) on the Pydantic Scan object (self)
    - Setting the obi_version in model_dump dict
    - Ordering keys in the model_dump dict, and form sub dict for improved readibility
    - Writing the dictionary to a json file

    Note that as Scan, Form and Block classes are child classes of OBIBaseModel, model_dump adds the obi_class name
    to each subdictionary representing these classes, for future deserialization
    """
    def serialize(self, output_path):
   
        # Get a dictionary representation of the scan
        model_dump = self.model_dump(serialize_as_any=True)

        # Add the obi version
        model_dump["obi_version"] = version("obi")
        
        # Order the keys in model_dump
        model_dump = OrderedDict(model_dump)
        model_dump.move_to_end('output_root', last=False)
        model_dump.move_to_end('obi_class', last=False)
        model_dump.move_to_end('obi_version', last=False)

        # Order the keys in model_dump["form"]
        model_dump["form"] = OrderedDict(model_dump["form"])
        model_dump["form"].move_to_end('obi_class', last=False)

        # Create the directory and write the model_dump dict to a json file
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as json_file:
            json.dump(model_dump, json_file, indent=4)


    """
    Create bbp-workflow campaign config
    """
    def create_bbp_workflow_campaign_config(self, output_path):

        campaign_config = {
            "dims": [],
            "attrs": {},
            "data": [],
            "coords": {},
            "name": ""
        }

        campaign_config['dims'] = [multi_param.location_str for multi_param in self.multiple_value_parameters()]

        for multi_param in self.multiple_value_parameters():

            sub_d = {multi_param.location_str: {
                                    "dims": [multi_param.location_str],
                                    "attrs": {},
                                    "data": multi_param.values
                                 }
                    }

            campaign_config["coords"].update(sub_d)

            campaign_config["data"] = [[["a", "b"], ["c", "d"]], [["e", "f"], ["g", "h"]]]


        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as json_file:
            json.dump(campaign_config, json_file, indent=4)


    """
    Function for displaying the coordinate parameters
    """
    def display_coordinate_parameters(self):
 
        print("\nCOORDINATE PARAMETERS (Reimplement)")

        # for single_coordinate_parameters in self._coordinate_parameters:
        #     output = f""
        #     for j, parameter in enumerate(single_coordinate_parameters):
                
        #         output = nested_param_short(parameter[0])
        #         output = output + ": " + str(parameter[1])
        #         if j < len(single_coordinate_parameters) - 1:
        #             output = output + ", "
        #     print(output)


"""
GridScan class:
    - Inherits from Scan
    - Rewrite description
"""
from itertools import product
class GridScan(Scan):
    
    """
    coordinate_parameters implementation
    """
    def coordinate_parameters(self, display=False) -> list:
        """
        Rewrite description
        """
        single_values_by_multi_value = []
        for multi_value in self.multiple_value_parameters():
            single_values = []
            for value in multi_value.values:
                single_values.append(SingleValueScanParameter(location_list=multi_value.location_list, value=value))
            single_values_by_multi_value.append(single_values)

        self._coordinate_parameters = []
        for single_value_scan_parameters_list in product(*single_values_by_multi_value):
            self._coordinate_parameters.append(SingleCoordinateScanParameters(single_value_scan_parameters_list=single_value_scan_parameters_list))
                
        # Optionally display the coordinate parameters
        if display: self.display_coordinate_parameters()

        # Return the coordinate parameters
        return self._coordinate_parameters

"""
CoupledScan class:
    - Inherits from Scan
    - Implements coordinate_parameters which iterates through multiple_value_parameters dictionary to create:
        coordinate_parameters list
    - Rewrite description
"""
class CoupledScan(Scan):

    def coordinate_parameters(self, display=False) -> list:
        
        previous_len = -1

        for multi_value in self.multiple_value_parameters():
            current_len = len(multi_value.values)
            if previous_len != -1 and current_len != previous_len:
                raise ValueError("All multi parameters must have the same number of values.")

            previous_len = current_len

        n_coords = current_len

        self._coordinate_parameters = []
        for coord_i in range(n_coords):
            single_value_scan_parameters_list = []
            for multi_value in self.multiple_value_parameters():
                single_value_scan_parameters_list.append(SingleValueScanParameter(location_list=multi_value.location_list, value=multi_value.values[coord_i]))
            self._coordinate_parameters.append(SingleCoordinateScanParameters(single_value_scan_parameters_list=single_value_scan_parameters_list))

        if display: self.display_coordinate_parameters()

        return self._coordinate_parameters
