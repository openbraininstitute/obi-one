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

import json
import shutil
import traceback
import tqdm

# def copy_directory(source_dir, destination_dir):

#     if os.path.exists(source_dir):

#         os.makedirs(destination_dir, exist_ok=True)
#         os.system(f"cp -r {source_dir} {destination_dir}")

from bluepysnap import Circuit
class CircuitExtraction(CircuitExtractions, SingleCoordinateMixin):
    """"""
    pass

    def run(self) -> str:

        try:

            # Create subcircuit
            print(f"Extracting subcircuit '{self.initialize.circuit_path}'")
            split_population.split_subcircuit(self.coordinate_output_root,
                                            self.initialize.node_set,
                                            self.initialize.circuit_path.path,
                                            True,
                                            False)

            ### nbS1-O1 ###
            
            # # Custom edit of the circuit config
            # with open(self.initialize.circuit_path.path, 'r') as original_circuit_config_file:
            #     original_circuit_config = json.load(original_circuit_config_file)

            #     original_circuit_config_copy = original_circuit_config.copy()
            #     original_circuit_config_copy['networks']['edges'][0]['edges_file'] = "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical/edges.h5"
            #     original_circuit_config_copy['networks']['edges'][3]['edges_file'] = "external_S1nonbarrel_neurons__S1nonbarrel_neurons__chemical/external_S1nonbarrel_neurons__S1nonbarrel_neurons__chemical.h5"
            #     original_circuit_config_copy['networks']['nodes'].pop(3)
                

            #     with open(self.coordinate_output_root + "/circuit_config.json", 'w') as config_file:
            #         json.dump(original_circuit_config_copy, config_file, indent=4)

            
            # # Copy subcircuit morphologies
            # original_circuit = Circuit(self.initialize.circuit_path.path)
            # new_circuit_path = self.coordinate_output_root + "circuit_config.json"
            # new_circuit = Circuit(new_circuit_path)
            # for pop_name, pop in new_circuit.nodes.items():

            #     if pop.config['type'] == 'biophysical':

            #         print(pop_name, len(pop.get()))

            #         if 'morphology' in pop.property_names:

            #             h5_morphologies_dir = pop.config['morphologies_dir'] + "/h5/"
            #             ascii_morphologies_dir = pop.config['morphologies_dir'] + "/ascii/"
            #             os.makedirs(h5_morphologies_dir, exist_ok=True)
            #             os.makedirs(ascii_morphologies_dir, exist_ok=True)

            #             for morphology_name in pop.get()['morphology'].unique():

            #                 os.system(f"cp {original_circuit.nodes[pop_name].config['morphologies_dir']}/h5/{morphology_name}.h5 {h5_morphologies_dir}{morphology_name}.h5")
            #                 os.system(f"cp {original_circuit.nodes[pop_name].config['morphologies_dir']}/ascii/{morphology_name}.asc {ascii_morphologies_dir}{morphology_name}.asc")
                            
            #         print(pop.property_names)
            #         if 'biophysical_neuron_models_dir' in pop.config:
            #             print("Copying biophysical_neuron_models")

            #             source_dir = original_circuit.nodes[pop_name].config['biophysical_neuron_models_dir']
            #             dest_dir = os.path.join(self.coordinate_output_root, "emodels_hoc")

            #             os.system(f"cp -r {source_dir} {dest_dir}")


            ### nbS1-O1-beta ###

            # Custom edit of the circuit config
            def rebase_config(config_dict, old_base, new_base):
                for key, value in config_dict.items():
                    if isinstance(value, str):
                        if value == old_base:
                            config_dict[key] = ""
                        else:
                            config_dict[key] = value.replace(old_base, new_base)
                    elif isinstance(value, dict):
                        rebase_config(value, old_base, new_base)
                    elif isinstance(value, list):
                        for _v in value:
                            rebase_config(_v, old_base, new_base)

            old_base = os.path.split(self.initialize.circuit_path.path)[0]
            alt_base = old_base  # Alternative old base
            for _sfix in ["-ER", "-DD", "-BIP", "-OFF", "-POS"]:
                alt_base = alt_base.removesuffix(_sfix)  # Quick fix to deal with symbolic links in base circuit
            new_base = "$BASE_DIR"
            new_circuit_path = self.coordinate_output_root + "circuit_config.json"
            # shutil.copyfile(new_circuit_path, os.path.splitext(new_circuit_path)[0] + ".BAK")

            with open(new_circuit_path, "r") as config_file:
                config_dict = json.load(config_file)
            rebase_config(config_dict, old_base, new_base)
            rebase_config(config_dict, alt_base, new_base)  # Quick fix to deal with symbolic links in base circuit
            with open(new_circuit_path, "w") as config_file:
                json.dump(config_dict, config_file, indent=4)

            # Copy subcircuit morphologies and e-models
            original_circuit = Circuit(self.initialize.circuit_path.path)
            new_circuit = Circuit(new_circuit_path)
            for pop_name, pop in new_circuit.nodes.items():

                if pop.config['type'] == 'biophysical':
                    print(f"Copying morphologies for population '{pop_name}' ({pop.size})")
                    if 'morphology' in pop.property_names:
                        ascii_morphologies_dir = pop.config["alternate_morphologies"]["neurolucida-asc"]
                        os.makedirs(ascii_morphologies_dir, exist_ok=True)
                        orig_ascii_morphologies_dir = original_circuit.nodes[pop_name].config["alternate_morphologies"]["neurolucida-asc"]

                        morphology_list = pop.get(properties="morphology").unique()
                        for morphology_name in tqdm.tqdm(morphology_list):
                            shutil.copyfile(os.path.join(orig_ascii_morphologies_dir, f"{morphology_name}.asc"),
                                            os.path.join(ascii_morphologies_dir, f"{morphology_name}.asc"))

                    if "biophysical_neuron_models_dir" in pop.config:
                        print(f"Copying biophysical_neuron_models for population '{pop_name}' ({pop.size})")

                        source_dir = original_circuit.nodes[pop_name].config["biophysical_neuron_models_dir"]
                        dest_dir = os.path.join(self.coordinate_output_root, os.path.split(source_dir)[1])

                        shutil.copytree(source_dir, dest_dir)

            # Copy mod files
            mod_folder = "mod"
            source_dir = os.path.join(os.path.split(self.initialize.circuit_path.path)[0], mod_folder)
            if os.path.exists(source_dir):
                print(f"Copying mod files")
                dest_dir = os.path.join(self.coordinate_output_root, mod_folder)
                shutil.copytree(source_dir, dest_dir)

            print("Extraction DONE")

        except Exception as e:
            if str(e) == "Unable to synchronously create group (name already exists)":
                print("Error:", f"Subcircuit {self.initialize.node_set} already exists. Subcircuit must be deleted before running the extraction.")
            else:
                # print(f"Error: {e}")
                traceback.print_exception(e)
            return

    def save_single(self):
        circuit_entity = SaveCircuitEntity(config_path=self.coordinate_output_root + "circuit_config.json")
        return circuit_entity
        
        
