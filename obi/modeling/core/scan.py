from pydantic import PrivateAttr, ValidationError
from obi.modeling.core.single import SingleCoordinateMixin, SingleCoordinateScanParams
from obi.modeling.core.block import Block, MultiValueScanParam, SingleValueScanParam
from obi.modeling.core.base import OBIBaseModel
from importlib.metadata import version
import os, copy, json
from collections import OrderedDict
from obi.modeling.unions.unions_form import FormUnion


class Scan(OBIBaseModel):
    """
    - Takes a Form & output_root as input
    - Creates multi-dimensional parameter scans through calls to generate and run
    - Includes several intermediate functions for computing multi-dimensional parameter scans:
        i.e. multiple_value_parameters, coordinate_parameters, coordinate_instances
    """

    form: FormUnion
    output_root: str
    coordinate_directory_option: str = "NAME_EQUALS_VALUE"
    _multiple_value_parameters: list = None
    _coordinate_parameters: list = PrivateAttr(default=[])
    _coordinate_instances: list = PrivateAttr(default=[])


    def multiple_value_parameters(self, display=False) -> list[MultiValueScanParam]:
        """
        - Iterates through Blocks of self.form to find "multi value parameters" 
            (i.e. parameters with list values of length greater than 1)
        - Returns a list of MultiValueScanParam objects
        """
        
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


    def coordinate_parameters(self, display=False) -> list[SingleCoordinateScanParams]:
        """
        Must be implemented by a subclass of Scan
        """
        raise NotImplementedError("Subclasses must implement this method")


    
    def coordinate_instances(self, display=False) -> list[SingleCoordinateMixin]:
        """
        Coordinate instance
        - Returns a list of "coordinate instances" by:
            - Iterating through self.coordinate_parameters()
            - Creating a single "coordinate instance" for each single coordinate parameter

        - Each "coordinate instance" is created by:
            - Making a deep copy of the form
            - Editing the multi value parameters (lists) to have the values of the single coordinate parameters
                (i.e. timestamps.timestamps_1.interval = [1.0, 5.0] -> timestamps.timestamps_1.interval = 1.0)
            - Casting the form to its single_coord_class_name type 
                (i.e. SimulationsForm -> Simulation)
        """

        self._coordinate_instances = []

        # Iterate through coordinate_parameters
        for idx, single_coordinate_scan_params in enumerate(self.coordinate_parameters()):

            # Make a deep copy of self.form
            single_coordinate_form = copy.deepcopy(self.form)
            
            # Iterate through the parameters in the single_coordinate_parameters tuple
            # Change the value of the multi parameter from a list to the single value of the coordinate
            for scan_param in single_coordinate_scan_params.scan_params:

                level_0_val = single_coordinate_form.__dict__[scan_param.location_list[0]]

                # If the first level is a Block
                if isinstance(level_0_val, Block):
                    level_0_val.__dict__[scan_param.location_list[1]] = scan_param.value

                # If the first level is a category dictionary
                if isinstance(level_0_val, dict):
                    level_1_val = level_0_val[scan_param.location_list[1]]
                    if isinstance(level_1_val, Block):
                        level_1_val.__dict__[scan_param.location_list[2]] = scan_param.value
                    else:
                        raise ValueError("Non Block options should not be used here.")
    
            try:
                # Cast the form to its single_coord_class_name type
                coordinate_instance = single_coordinate_form.cast_to_single_coord()

                # Set the variables of the coordinate instance related to the scan
                coordinate_instance.idx = idx
                coordinate_instance.single_coordinate_scan_params = single_coordinate_scan_params

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
    

    
    def generate(self):
        """
        Description
        """

        # Iterate through self.coordinate_instances()
        for coordinate_instance in self.coordinate_instances():

            # Check if coordinate instance has function "generate"
            if hasattr(coordinate_instance, 'generate'):

                # Set scan_output_root
                coordinate_instance.scan_output_root = self.output_root

                # Create the coordinate_output_root directory
                coordinate_instance.coordinate_directory_option = self.coordinate_directory_option
                os.makedirs(coordinate_instance.coordinate_output_root, exist_ok=True)

                # Call the coordinate_instance's generate() function
                coordinate_instance.generate()

                # Serialize the coordinate instance
                coordinate_instance.serialize(os.path.join(coordinate_instance.coordinate_output_root, "generate_coordinate_instance.json"))

            else:
                # Raise an error if generate() not implemented for the coordinate instance
                raise NotImplementedError(f"Function \"generate\" not implemented for type:{type(coordinate_instance)}")

        # Serialize the scan
        self.serialize(os.path.join(self.output_root, "generate_scan_config.json"))

        # Create a bbp_workflow_campaign_config
        self.create_bbp_workflow_campaign_config(os.path.join(self.output_root, "bbp_workflow_campaign_config.json"))

   
    def run(self):
        """
        Description
        """

        # Iterate through self.coordinate_instances()
        for coordinate_instance in self.coordinate_instances():

            # Check if coordinate instance has function "run"
            if hasattr(coordinate_instance, 'run'):

                # Set scan_output_root
                coordinate_instance.scan_output_root = self.output_root

                # Create the coordinate_output_root directory
                coordinate_instance.coordinate_directory_option = self.coordinate_directory_option
                os.makedirs(coordinate_instance.coordinate_output_root, exist_ok=True)

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

    
   
    def serialize(self, output_path=''):
        """
        Serialize a Scan object
        - type name added to each subobject of type
            inheriting from OBIBaseModel for future deserialization
        """
   
        # Dict representation of the scan object
        model_dump = self.model_dump()

        # Add the OBI version
        model_dump["obi_version"] = version("obi")
        
        # Order keys in dict
        model_dump = OrderedDict(model_dump)
        model_dump.move_to_end('output_root', last=False)
        model_dump.move_to_end('type', last=False)
        model_dump.move_to_end('obi_version', last=False)

        # Order the keys in subdict "form"
        model_dump["form"] = OrderedDict(model_dump["form"])
        model_dump["form"].move_to_end('type', last=False)

        # Create the directory and write dict to json file
        if output_path != '':
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w") as json_file:
                json.dump(model_dump, json_file, indent=4)

        return model_dump
  
    def create_bbp_workflow_campaign_config(self, output_path):
        """
        Description
        """

        # Dictionary intialization
        campaign_config = {"dims": [], "attrs": {}, "data": [], "coords": {}, "name": ""}

        # dims
        campaign_config['dims'] = [multi_param.location_str for multi_param in self.multiple_value_parameters()]

        
        multi_value_parameters = self.multiple_value_parameters()
        if len(multi_value_parameters):
            # dims
            campaign_config['dims'] = [multi_param.location_str for multi_param in self.multiple_value_parameters()]

            # coords
            for multi_param in multi_value_parameters:
                sub_d = {multi_param.location_str: {
                                        "dims": [multi_param.location_str],
                                        "attrs": {},
                                        "data": multi_param.values
                                    }
                        }
                campaign_config["coords"].update(sub_d)
        else:
            campaign_config['dims'] = ["single_coordinate"]
            campaign_config["coords"] = {
                                    "single_coordinate": {
                                        "dims": ["single_coordinate"],
                                        "attrs": {},
                                        "data": [self.form.single_coord_scan_default_subpath]
                                    }
                                }


        # data
        campaign_config["data"] = [[["a", "b"], ["c", "d"]], [["e", "f"], ["g", "h"]]]

        # Write json to file
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as json_file:
            json.dump(campaign_config, json_file, indent=4)


    def display_coordinate_parameters(self):
        """
        Description
        """
        print("\nCOORDINATE PARAMETERS (Reimplement)")
        for single_coordinate_parameters in self._coordinate_parameters:
            single_coordinate_parameters.display_parameters()


    def save(self):

        coordinate_instance_entities = []
        for coordinate_instance in self.coordinate_instances():
            coordinate_instance_entity = coordinate_instance.save_single()
            coordinate_instance_entities.append(coordinate_instance_entity)

        self.form.save_collection(coordinate_instance_entities)



from itertools import product
class GridScan(Scan):
    """
    Description
    """
    
    def coordinate_parameters(self, display=False) -> list[SingleCoordinateScanParams]:
        """
        Description
        """
        single_values_by_multi_value = []
        multi_value_parameters = self.multiple_value_parameters()
        if len(multi_value_parameters):
            for multi_value in multi_value_parameters:
                single_values = []
                for value in multi_value.values:
                    single_values.append(SingleValueScanParam(location_list=multi_value.location_list, value=value))
                single_values_by_multi_value.append(single_values)

            self._coordinate_parameters = []
            for scan_params in product(*single_values_by_multi_value):
                self._coordinate_parameters.append(SingleCoordinateScanParams(scan_params=scan_params))

        else:
            self._coordinate_parameters = [SingleCoordinateScanParams(nested_coordinate_subpath_str=self.form.single_coord_scan_default_subpath)]
                
        # Optionally display the coordinate parameters
        if display: self.display_coordinate_parameters()

        # Return the coordinate parameters
        return self._coordinate_parameters


class CoupledScan(Scan):
    """
    Description
    """

    def coordinate_parameters(self, display=False) -> list:
        """
        Description
        """
        
        previous_len = -1

        for multi_value in self.multiple_value_parameters():
            current_len = len(multi_value.values)
            if previous_len != -1 and current_len != previous_len:
                raise ValueError("All multi parameters must have the same number of values.")

            previous_len = current_len

        n_coords = current_len

        self._coordinate_parameters = []
        for coord_i in range(n_coords):
            scan_params = []
            for multi_value in self.multiple_value_parameters():
                scan_params.append(SingleValueScanParam(location_list=multi_value.location_list, value=multi_value.values[coord_i]))
            self._coordinate_parameters.append(SingleCoordinateScanParams(scan_params=scan_params))

        if display: self.display_coordinate_parameters()

        return self._coordinate_parameters
