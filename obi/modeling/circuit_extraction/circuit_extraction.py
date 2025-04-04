from obi.modeling.core.form import Form
from obi.modeling.core.block import Block
from obi.modeling.core.single import SingleCoordinateMixin
from obi.modeling.core.db import SaveCircuitEntity, SaveCircuitCollectionEntity
from obi.modeling.core.path import NamedPath

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

from bluepysnap import Circuit
class CircuitExtraction(CircuitExtractions, SingleCoordinateMixin):
    """"""
    pass

    def run(self) -> str:

        try:

            # Create subcircuit
            split_population.split_subcircuit(self.coordinate_output_root,
                                            self.initialize.node_set,
                                            self.initialize.circuit_path.path,
                                            True,
                                            False)

            # Custom edit of the circuit config
            with open(self.initialize.circuit_path.path, 'r') as original_circuit_config_file:
                original_circuit_config = json.load(original_circuit_config_file)

                original_circuit_config_copy = original_circuit_config.copy()
                original_circuit_config_copy['networks']['edges'][0]['edges_file'] = "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical/edges.h5"
                original_circuit_config_copy['networks']['edges'][3]['edges_file'] = "external_S1nonbarrel_neurons__S1nonbarrel_neurons__chemical/external_S1nonbarrel_neurons__S1nonbarrel_neurons__chemical.h5"
                original_circuit_config_copy['networks']['nodes'].pop(3)
                

                with open(self.coordinate_output_root + "/circuit_config.json", 'w') as config_file:
                    json.dump(original_circuit_config_copy, config_file, indent=4)

            
            # Copy subcircuit morphologies
            original_circuit = Circuit(self.initialize.circuit_path.path)
            new_circuit_path = self.coordinate_output_root + "circuit_config.json"
            new_circuit = Circuit(new_circuit_path)
            for pop_name, pop in new_circuit.nodes.items():

                if pop.config['type'] == 'biophysical':

                    print(pop_name, len(pop.get()))

                    if 'morphology' in pop.property_names:

                        h5_morphologies_dir = pop.config['morphologies_dir'] + "/h5/"
                        ascii_morphologies_dir = pop.config['morphologies_dir'] + "/ascii/"
                        os.makedirs(h5_morphologies_dir, exist_ok=True)
                        os.makedirs(ascii_morphologies_dir, exist_ok=True)

                        for morphology_name in pop.get()['morphology'].unique():

                            os.system(f"cp {original_circuit.nodes[pop_name].config['morphologies_dir']}/h5/{morphology_name}.h5 {h5_morphologies_dir}{morphology_name}.h5")
                            os.system(f"cp {original_circuit.nodes[pop_name].config['morphologies_dir']}/ascii/{morphology_name}.asc {ascii_morphologies_dir}{morphology_name}.asc")
                            
                    print(pop.property_names)
                    if 'biophysical_neuron_models_dir' in pop.config:
                        print("Copying biophysical_neuron_models")

                        # Copy hoc files
                        source_dir = original_circuit.nodes[pop_name].config['biophysical_neuron_models_dir']
                        dest_dir = os.path.join(self.coordinate_output_root, "emodels_hoc")
                        os.system(f"cp -r {source_dir} {dest_dir}")

                        # Copy mod files                    
                        source_dir, file_name = os.path.split(self.initialize.circuit_path.path)
                        source_dir = os.path.join(source_dir, "mod")
                        dest_dir = os.path.join(self.coordinate_output_root, "mod")
                        os.system(f"cp -r {source_dir} {dest_dir}")




        except Exception as e:
            if str(e) == "Unable to synchronously create group (name already exists)":
                print("Error:", f"Subcircuit {self.initialize.node_set} already exists. Subcircuit must be deleted before running the extraction.")
            else:
                print(f"Error: {e}")
            return

    def save_single(self):
        circuit_entity = SaveCircuitEntity(config_path=self.coordinate_output_root + "circuit_config.json")
        return circuit_entity
        
        
