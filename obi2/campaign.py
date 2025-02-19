from pydantic import BaseModel, PrivateAttr, ValidationError
from .template import Template, SubTemplate

import copy
class Campaign(BaseModel):

    template_instance: Template = None

    _coord_instances: list = PrivateAttr(default=[])

    @property
    def coord_instances(self) -> list[Template]:

        if len(self._coord_instances) > 0: return self._coord_instances

        for coord in self.template_instance.generate_grid_scan_coords():

            coord_template_instance = copy.deepcopy(self.template_instance)

            for param in coord:
                keys = param[0]
                val = param[1]

                current_level = coord_template_instance
                for i, key in enumerate(keys):

                    if isinstance(current_level, SubTemplate):

                        if i == len(keys) - 1:
                            current_level.__dict__[key] = val
                        else:
                            current_level = current_level.__dict__[key]
                
                    elif isinstance(current_level, dict):
                        current_level = current_level[key]


            try:
                coord_instance = coord_template_instance.cast_to_single_instance()
                self._coord_instances.append(coord_instance)
                
            except ValidationError as e:
                print("Validation Error:", e)

        return self._coord_instances