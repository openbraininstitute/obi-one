from itertools import product
import copy
import os
import json
from pydantic import PrivateAttr

from .multi_template import MultiTemplate
from .simulation import Simulation

class SimulationCampaign(MultiTemplate):
    template_simulation: Simulation

    _simulations: list[Simulation] = PrivateAttr(default=[])

    @property
    def simulations(self):

        if len(self._simulations) > 0: return self._simulations

        for coord in self.template_simulation.generate_grid_scan_coords():

            coord_simulation = copy.deepcopy(self.template_simulation)

            for param in coord:
                keys = param[0]
                val = param[1]

                current_level = coord_simulation
                for i, key in enumerate(keys):

                    if isinstance(current_level, MultiTemplate):

                        if i == len(keys) - 1:
                            current_level.__dict__[key] = val
                        else:
                            current_level = current_level.__dict__[key]
                
                    elif isinstance(current_level, dict):
                        current_level = current_level[key]

            self._simulations.append(coord_simulation)
        
        return self._simulations


    def write_simulation_sonata_configs(self, output_dir):

        os.makedirs(output_dir, exist_ok=True)

        for idx, simulation in enumerate(self.simulations):
            config = simulation.sonata_config()
            config_path = os.path.join(output_dir, f"simulation_config_{idx}.json")
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
