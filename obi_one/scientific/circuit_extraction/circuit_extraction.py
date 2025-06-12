from typing import ClassVar

from obi_one.core.block import Block
from obi_one.core.form import Form
from obi_one.core.single import SingleCoordinateMixin
from obi_one.scientific.circuit.circuit import Circuit
from obi_one.scientific.circuit.neuron_sets import NeuronSet
from obi_one.scientific.unions.unions_neuron_sets import NeuronSetUnion


class CircuitExtractions(Form):
    """ """

    single_coord_class_name: ClassVar[str] = "CircuitExtraction"
    name: ClassVar[str] = "Circuit Extraction"
    description: ClassVar[str] = (
        "Extracts a sub-circuit of a SONATA circuit as defined by a node set. The output circuit will contain all morphologies, hoc files, and mod files that are required to simulate the extracted circuit."
    )
    
    class Initialize(Block):
        circuit: Circuit | list[Circuit]
        run_validation: bool = False

    initialize: Initialize
    neuron_set: NeuronSetUnion

    def save_collection(self, circuit_entities):
        pass
        """
        Should save the collaction object here
        """


import json
import os
import shutil
import traceback

import bluepysnap as snap
import bluepysnap.circuit_validation
import h5py
import tqdm
from brainbuilder.utils.sonata import split_population


class CircuitExtraction(CircuitExtractions, SingleCoordinateMixin):
    """Extracts a sub-circuit of a SONATA circuit as defined by a node set. The output circuit will contain
    all morphologies, hoc files, and mod files that are required to simulate the extracted circuit.
    """

    @staticmethod
    def _filter_ext(file_list, ext):
        return list(filter(lambda f: os.path.splitext(f)[1].lower() == f".{ext}", file_list))

    def run(self) -> str:
        try:
            # Add neuron set to SONATA circuit object
            # (will raise an error in case already existing)
            nset_name = self.neuron_set.__class__.__name__
            nset_def = self.neuron_set.get_node_set_definition(
                self.initialize.circuit, self.initialize.circuit.default_population_name
            )
            sonata_circuit = self.initialize.circuit.sonata_circuit
            NeuronSet.add_node_set_to_circuit(
                sonata_circuit, {nset_name: nset_def}, overwrite_if_exists=False
            )

            # Create subcircuit using "brainbuilder"
            print(f"Extracting subcircuit from '{self.initialize.circuit.name}'")
            split_population.split_subcircuit(
                self.coordinate_output_root,
                nset_name,
                sonata_circuit,
                True,
                False,
            )

            # Custom edit of the circuit config so that all paths are relative to the new base directory
            # (in case there were absolute paths in the original config)
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

            old_base = os.path.split(self.initialize.circuit.path)[0]

            # Quick fix to deal with symbolic links in base circuit (not usually required)
            # alt_base = old_base  # Alternative old base
            # for _sfix in ["-ER", "-DD", "-BIP", "-OFF", "-POS"]:
            #     alt_base = alt_base.removesuffix(_sfix)

            new_base = "$BASE_DIR"
            new_circuit_path = os.path.join(self.coordinate_output_root, "circuit_config.json")
            # shutil.copyfile(new_circuit_path, os.path.splitext(new_circuit_path)[0] + ".BAK")  # Create backup before modifying

            with open(new_circuit_path) as config_file:
                config_dict = json.load(config_file)
            rebase_config(config_dict, old_base, new_base)
            # if alt_base != old_base:  # Quick fix to deal with symbolic links in base circuit
            # rebase_config(config_dict, alt_base, new_base)
            with open(new_circuit_path, "w") as config_file:
                json.dump(config_dict, config_file, indent=4)

            # Copy subcircuit morphologies and e-models (separately per node population)
            original_circuit = self.initialize.circuit.sonata_circuit
            new_circuit = snap.Circuit(new_circuit_path)
            for pop_name, pop in new_circuit.nodes.items():
                if pop.config["type"] == "biophysical":
                    # Copying morphologies of any (supported) format
                    if "morphology" in pop.property_names:
                        print(f"Copying morphologies for population '{pop_name}' ({pop.size})")
                        morphology_list = pop.get(properties="morphology").unique()

                        src_morph_dirs = {}
                        dest_morph_dirs = {}
                        for _morph_ext in ["swc", "asc", "h5"]:
                            try:
                                morph_folder = original_circuit.nodes[
                                    pop_name
                                ].morph._get_morphology_base(_morph_ext)
                                # FIXME: Should not use private function!! But required to get path even if h5 container.

                                assert os.path.exists(morph_folder), (
                                    f"ERROR: {_morph_ext} morphology folder/container does not exist!"
                                )

                                if os.path.isdir(morph_folder):
                                    assert (
                                        len(self._filter_ext(os.listdir(morph_folder), _morph_ext))
                                        > 0
                                    ), (
                                        f"ERROR: {_morph_ext} morphology folder does not contain morphologies!"
                                    )

                                dest_morph_dirs[_morph_ext] = pop.morph._get_morphology_base(
                                    _morph_ext
                                )  # FIXME: Should not use private function!!
                                src_morph_dirs[_morph_ext] = morph_folder
                            except:
                                morph_folder = None

                        assert len(src_morph_dirs) > 0, (
                            "ERROR: No morphologies of any supported format found!"
                        )
                        for _morph_ext in src_morph_dirs:
                            if _morph_ext == "h5" and os.path.isfile(src_morph_dirs[_morph_ext]):
                                # FIXME: If there is only one neuron extracted, consider removing the container!!
                                # Copy containerized morphologies into new container
                                os.makedirs(
                                    os.path.split(dest_morph_dirs[_morph_ext])[0], exist_ok=True
                                )
                                src_container = src_morph_dirs[_morph_ext]
                                dest_container = dest_morph_dirs[_morph_ext]
                                with h5py.File(src_container) as f_src:
                                    with h5py.File(dest_container, "a") as f_dest:
                                        skip_counter = 0
                                        for morphology_name in tqdm.tqdm(
                                            morphology_list,
                                            desc=f"Copying containerized .{_morph_ext} morphologies",
                                        ):
                                            if morphology_name in f_dest:
                                                skip_counter += 1
                                            else:
                                                f_src.copy(
                                                    f_src[morphology_name],
                                                    f_dest,
                                                    name=morphology_name,
                                                )
                                print(
                                    f"Copied {len(morphology_list) - skip_counter} morphologies into container ({skip_counter} already existed)"
                                )
                            else:
                                # Copy morphology files
                                os.makedirs(dest_morph_dirs[_morph_ext], exist_ok=True)
                                for morphology_name in tqdm.tqdm(
                                    morphology_list, desc=f"Copying .{_morph_ext} morphologies"
                                ):
                                    src_file = os.path.join(
                                        src_morph_dirs[_morph_ext],
                                        f"{morphology_name}.{_morph_ext}",
                                    )
                                    dest_file = os.path.join(
                                        dest_morph_dirs[_morph_ext],
                                        f"{morphology_name}.{_morph_ext}",
                                    )
                                    assert os.path.exists(src_file), (
                                        f"ERROR: Morphology '{src_file}' missing!"
                                    )
                                    if not os.path.exists(dest_file):
                                        # Copy only, if not yet existing (could happen for shared morphologies among populations)
                                        shutil.copyfile(src_file, dest_file)

                    # Copy .hoc file directory (Even if defined globally, shows up under pop.config)
                    if "biophysical_neuron_models_dir" in pop.config:
                        hoc_file_list = [
                            _hoc.split(":")[-1] + ".hoc"
                            for _hoc in pop.get(properties="model_template").unique()
                        ]
                        print(
                            f"Copying {len(hoc_file_list)} biophysical neuron models (.hoc) for population '{pop_name}' ({pop.size})"
                        )

                        source_dir = original_circuit.nodes[pop_name].config[
                            "biophysical_neuron_models_dir"
                        ]
                        dest_dir = pop.config["biophysical_neuron_models_dir"]
                        os.makedirs(dest_dir, exist_ok=True)

                        for _hoc_file in hoc_file_list:
                            src_file = os.path.join(source_dir, _hoc_file)
                            dest_file = os.path.join(dest_dir, _hoc_file)
                            assert os.path.exists(src_file), (
                                f"ERROR: HOC file '{src_file}' missing!"
                            )
                            if not os.path.exists(dest_file):
                                # Copy only, if not yet existing (could happen for shared hoc files among populations)
                                shutil.copyfile(src_file, dest_file)

            # Copy .mod files, if any
            mod_folder = "mod"
            source_dir = os.path.join(os.path.split(self.initialize.circuit.path)[0], mod_folder)
            if os.path.exists(source_dir):
                print("Copying mod files")
                dest_dir = os.path.join(self.coordinate_output_root, mod_folder)
                shutil.copytree(source_dir, dest_dir)

            # Run circuit validation
            if self.initialize.run_validation:
                errors = snap.circuit_validation.validate(new_circuit_path, skip_slow=True)
                assert len(errors) == 0, f"Circuit validation error(s) found: {errors}"
                print("No validation errors found!")

            print("Extraction DONE")

        except Exception as e:
            if str(e) == "Unable to synchronously create group (name already exists)":
                print(
                    "Error:",
                    f"Subcircuit {self.neuron_set} already exists. Subcircuit must be deleted before running the extraction.",
                )
            else:
                traceback.print_exception(e)
            return

    def save(self):
        pass
        """
        Currently should return a created entity
        """
