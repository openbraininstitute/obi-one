from pydantic import BaseModel, field_validator, PrivateAttr
from itertools import product


class SubTemplate(BaseModel):
    """
    """
    _multi_params: dict = PrivateAttr(default={})
    
    def multi_params(self, category_name, subtemplate_key='') -> dict:
        
        """
        Iterate through all attributes of the SubTemplate
        """
        for key, value in self.__dict__.items():
            if isinstance(value, list) and len(value) > 1:

                if subtemplate_key != '':
                    self._multi_params[f"{category_name}.{subtemplate_key}.{key}"] = {
                        "coord_param_keys": [category_name, subtemplate_key, key],
                        "coord_param_values": value
                    }
                else:
                    self._multi_params[f"{category_name}.{key}"] = {
                        "coord_param_keys": [category_name, key],
                        "coord_param_values": value
                    }

        return self._multi_params
    
    def enforce_no_lists(self):
        for key, value in self.__dict__.items():
            if isinstance(value, list):
                raise ValueError(f"Attribute '{key}' must not be a list.")


class Template(BaseModel):
    """
    """
    _multi_params: dict = PrivateAttr(default={})
    _sonata_config: dict = PrivateAttr(default={})
    
    
    @property
    def multi_params(self) -> dict:
        
        """
        Iterate through all attributes of the Template
        """
        for attr_name, attr_value in self.__dict__.items():

            """
            Check if the attribute is a dictionary of SubTemplate instances
            """
            if isinstance(attr_value, dict) and all(isinstance(dict_val, SubTemplate) for dict_key, dict_val in attr_value.items()):

                category_name = attr_name; category_subtemplates_dict = attr_value
                
                """
                If so iterate through the dictionary's SubTemplate instances
                """
                for subtemplate_key, subtemplate in category_subtemplates_dict.items():

                    """
                    Call the multi_params method of the SubTemplate instance
                    """                    
                    self._multi_params.update(subtemplate.multi_params(category_name=category_name, subtemplate_key=subtemplate_key))


            """
            Else if the attribute is a SubTemplate instance, call the multi_params method of the SubTemplate instance
            """
            if isinstance(attr_value, SubTemplate):
                category_name = attr_name
                category_subtemplate = attr_value
                self._multi_params.update(category_subtemplate.multi_params(category_name=category_name))

                            
        return self._multi_params


    def generate_grid_scan_coords(self) -> list:

        all_tuples = []
        for key, value in self.multi_params.items():
            tups = []
            for k, v in zip([value["coord_param_keys"] for i in range(len(value['coord_param_values']))], value['coord_param_values']):
                tups.append((k, v))

            all_tuples.append(tups)

        coords = [coord for coord in product(*all_tuples)]
        return coords
    
    def cast_to_single_instance(self):
        class_to_cast_to = self.single_version_class()
        single_instance = class_to_cast_to.model_validate(self.model_dump())
        return single_instance
    

class SingleTypeMixin:
    """Mixin to enforce no lists in all SubTemplates and SubTemplates in Category dictionaries."""

    @field_validator("*", mode="before")
    @classmethod
    def enforce_single_type(cls, value):

        if isinstance(value, dict):  # Check for nested dictionaries containing SubTemplate instances
            for key, dict_value in value.items():
                if isinstance(dict_value, SubTemplate):  # Recursively validate SubTemplate objects
                    subtemplate = dict_value
                    subtemplate.enforce_no_lists()
                        
        if isinstance(value, SubTemplate):  # Validate SubTemplate objects
            subtemplate = value
            value.enforce_no_lists()
                
        return value
    
