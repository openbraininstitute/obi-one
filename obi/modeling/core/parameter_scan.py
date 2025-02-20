from pydantic import BaseModel, PrivateAttr, ValidationError
from .template import Template, SubTemplate


# def set_value_in_subtemplate(subtemplate: SubTemplate, key, value):
#     # print(subtemplate)
#     print(subtemplate.__dict__[key])
#     # subtemplate.__dict__[key] = value


import os, copy, json
class ParameterScan(BaseModel):

    template_instance: Template = None
    _coords = PrivateAttr(default=[])
    _coord_instances: list = PrivateAttr(default=[])

    def coord_instances_from_coords(self) -> list[Template]:

        for coord in self._coords:

            coord_template_instance = copy.deepcopy(self.template_instance)
            
            for param in list(coord):
                
                keys = param[0]
                val = param[1]

                level_0_val = coord_template_instance.__dict__[keys[0]]

                if isinstance(level_0_val, SubTemplate):
                    level_0_val.__dict__[keys[1]] = val

                if isinstance(level_0_val, dict):
                    level_1_val = level_0_val[keys[1]]
                    if isinstance(level_1_val, SubTemplate):
                        level_1_val.__dict__[keys[2]] = val
                    else:
                        # This should already by checked elsewhere (in future, if not done already)
                        print("Validation Error:", "Non SubTemplate options should not be used here.")  
    
            try:
                coord_instance = coord_template_instance.cast_to_single_instance()
                self._coord_instances.append(coord_instance)
                
            except ValidationError as e:
                print("Validation Error:", e)

        return self._coord_instances
    

    def write_configs(self, output_dir, prefix="simulation_config_"):

        os.makedirs(output_dir, exist_ok=True)
        for idx, coord_instance in enumerate(self.coord_instances):
            config = coord_instance.generate_config()

            config_path = os.path.join(output_dir, f"{prefix}{idx}.json")
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)


class GridParameterScan(ParameterScan):

    @property
    def coord_instances(self) -> list[Template]:

        if len(self._coord_instances) > 0: return self._coord_instances
            
        self._coords = self.template_instance.generate_grid_scan_coords()
        self._coord_instances = self.coord_instances_from_coords()

        return self._coord_instances
        

class CoupledCoordsParameterScan(ParameterScan):

    @property
    def coord_instances(self) -> list[Template]:

        if len(self._coord_instances) > 0: return self._coord_instances

        self._coords = self.template_instance.generate_coupled_scan_coords()
        self._coord_instances = self.coord_instances_from_coords()

        return self._coord_instances
