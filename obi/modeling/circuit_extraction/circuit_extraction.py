from obi.modeling.core.form import Form
from obi.modeling.core.block import Block
from obi.modeling.core.single import SingleCoordinateMixin
from obi.modeling.core.db import SaveCircuitEntity, SaveCircuitCollectionEntity
from obi.modeling.core.base import NamedPath

class CircuitExtractions(Form):
    """
    """

    _single_coord_class_name: str = "CircuitExtraction"

    class Initialize(Block):
        circuit_path: NamedPath | list[NamedPath]
        node_set: str | list[str]

    initialize: Initialize

    def save_collection(self, circuit_entities):
        SaveCircuitCollectionEntity(circuits=circuit_entities)
        


import os
from brainbuilder.utils.sonata import split_population
from importlib.metadata import version


import os
import json
def copy_directory(source_dir, destination_dir):

    if os.path.exists(source_dir):

        os.makedirs(destination_dir, exist_ok=True)
        os.system(f"cp -r {source_dir} {destination_dir}")

class CircuitExtraction(CircuitExtractions, SingleCoordinateMixin):
    """"""
    pass

    def run(self) -> str:

        try:
            print(self.coordinate_output_root)
            split_population.split_subcircuit(self.coordinate_output_root,
                                            self.initialize.node_set,
                                            self.initialize.circuit_path.path,
                                            True,
                                            False)
            

            with open(self.coordinate_output_root + "circuit_config.json", 'r') as config_file:
                config = json.load(config_file)

                for nodes_dict in config['networks']['nodes']:
                    for population_key, population_dict in nodes_dict['populations'].items():

                        # if 'morphologies_dir' in population_dict:                
                        #     print("Copying morphologies")
                            # copy_directory(population_dict['morphologies_dir'], os.path.join(self.coordinate_output_root, "morphologies"))
                        if 'biophysical_neuron_models_dir' in population_dict:
                            print("Copying biophysical_neuron_models")
                            copy_directory(population_dict['biophysical_neuron_models_dir'], os.path.join(self.coordinate_output_root, "emodels_hoc"))

            with open(self.initialize.circuit_path, 'r') as original_circuit_config_file:
                original_circuit_config = json.load(original_circuit_config_file)

                original_circuit_config_copy = original_circuit_config.copy()
                original_circuit_config_copy['networks']['edges'][0]['edges_file'] = "external_S1nonbarrel_neurons__S1nonbarrel_neurons__chemical/external_S1nonbarrel_neurons__S1nonbarrel_neurons__chemical.h5"
                original_circuit_config_copy['networks']['edges'][3]['edges_file'] = "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical/edges.h5"

                with open(self.coordinate_output_root + "/circuit_config.json", 'w') as config_file:
                    json.dump(original_circuit_config_copy, config_file, indent=4)



            


        except Exception as e:
            if str(e) == "Unable to synchronously create group (name already exists)":
                print("Error:", f"Subcircuit {self.initialize.node_set} already exists. Subcircuit must be deleted before running the extraction.")
            else:
                print(f"Error: {e}")
            return

    def save_single(self):
        circuit_entity = SaveCircuitEntity(config_path=self.coordinate_output_root + "circuit_config.json")
        return circuit_entity
        
        
