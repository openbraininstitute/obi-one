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

import json
import shutil
import traceback
import tqdm

from bluepysnap import Circuit
class CircuitExtraction(CircuitExtractions, SingleCoordinateMixin):
    """
    """
    @staticmethod
    def _filter_ext(file_list, ext):
        return list(filter(lambda f: os.path.splitext(f)[1].lower() == f".{ext}", file_list))

    def run(self) -> str:

        try:

            # Create subcircuit
            print(f"Extracting subcircuit from '{self.initialize.circuit_path}'")
            split_population.split_subcircuit(self.coordinate_output_root,
                                            self.initialize.node_set,
                                            self.initialize.circuit_path.path,
                                            True,
                                            False)

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
            if alt_base != old_base:  # Quick fix to deal with symbolic links in base circuit
                rebase_config(config_dict, alt_base, new_base)
            with open(new_circuit_path, "w") as config_file:
                json.dump(config_dict, config_file, indent=4)

            # Copy subcircuit morphologies and e-models
            original_circuit = Circuit(self.initialize.circuit_path.path)
            new_circuit = Circuit(new_circuit_path)
            for pop_name, pop in new_circuit.nodes.items():

                if pop.config['type'] == 'biophysical':
                    print(f"Copying morphologies for population '{pop_name}' ({pop.size})")
                    if 'morphology' in pop.property_names:
                        morphology_list = pop.get(properties="morphology").unique()

                        src_morph_dirs = {}
                        dest_morph_dirs = {}
                        for _morph_ext in ["swc", "asc", "h5"]:
                            try:
                                morph_folder = original_circuit.nodes[pop_name].morph.get_morphology_dir(_morph_ext)
                                assert os.path.exists(morph_folder), f"ERROR: {_morph_ext} morphology folder does not exist!"
                                assert len(self._filter_ext(os.listdir(morph_folder), _morph_ext)) > 0, f"ERROR: {_morph_ext} morphology folder does not contain morphologies!"
                                dest_morph_dirs[_morph_ext] = pop.morph.get_morphology_dir(_morph_ext)
                                src_morph_dirs[_morph_ext] = morph_folder
                            except:
                                morph_folder = None

                        for _morph_ext in src_morph_dirs.keys():
                            os.makedirs(dest_morph_dirs[_morph_ext], exist_ok=True)
                            for morphology_name in tqdm.tqdm(morphology_list, desc=f"Copying .{_morph_ext} morphologies"):
                                src_file = os.path.join(src_morph_dirs[_morph_ext], f"{morphology_name}.{_morph_ext}")
                                dest_file = os.path.join(dest_morph_dirs[_morph_ext], f"{morphology_name}.{_morph_ext}")
                                assert os.path.exists(src_file), f"ERROR: Morphology '{src_file}' missing!"
                                if not os.path.exists(dest_file):
                                    shutil.copyfile(src_file, dest_file)

                    if "biophysical_neuron_models_dir" in pop.config:  # Even if defined globally, shows up under pop.config
                        print(f"Copying biophysical_neuron_models for population '{pop_name}' ({pop.size})")

                        source_dir = original_circuit.nodes[pop_name].config["biophysical_neuron_models_dir"]
                        dest_dir = pop.config["biophysical_neuron_models_dir"]

                        shutil.copytree(source_dir, dest_dir, dirs_exist_ok=True)

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
                traceback.print_exception(e)
            return

    def save_single(self):
        circuit_entity = SaveCircuitEntity(config_path=self.coordinate_output_root + "circuit_config.json")
        return circuit_entity
        
        
