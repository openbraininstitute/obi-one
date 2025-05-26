from typing import ClassVar, Literal

from obi_one.core.block import Block
from obi_one.core.form import Form
from obi_one.core.path import NamedPath
from obi_one.core.single import SingleCoordinateMixin


class MorphologyDecontainerizationsForm(Form):
    """ """

    single_coord_class_name: ClassVar[str] = "MorphologyDecontainerization"
    name: ClassVar[str] = "Morphology Decontainerization"
    description: ClassVar[str] = (
        "Creates a circuit with individual morphology files instead of containerized morphologies"
    )

    class Initialize(Block):
        circuit_path: NamedPath | list[NamedPath]
        output_format: Literal["h5", "asc", "swc"] | list[Literal["h5", "asc", "swc"]] = "h5"

    initialize: Initialize


import json
import logging
import os
import shutil
import traceback
from typing import ClassVar

import h5py
import numpy as np
import tqdm
from bluepysnap import Circuit
from morph_tool import convert


class MorphologyDecontainerization(MorphologyDecontainerizationsForm, SingleCoordinateMixin):
    """Creates a circuit with individual morphology files instead of containerized morphologies,
    which involves the following steps:
    (1) Copy circuit to output location
    (2) Extract individual .h5 morphologies from an .h5 container
    (3) Convert .h5 morphologies to specified output format (.swc or .asc; skip if .h5)
    (4) Update the circuit config, pointing to the individual morphology folder
    (5) Delete .h5 container and .h5 files if that's not the specified output format
    (7) Check loading individual morphologies
    Important: The original circuit won't be modified! The circuit will be copied
               to the output location where all operations take place.
    """

    @staticmethod
    def _check_morphologies(circuit_config, extension):
        """Check modified circuit by loading some morphologies from each node population."""
        c = Circuit(circuit_config)
        for npop in c.nodes.population_names:
            nodes = c.nodes[npop]
            if nodes.type == "biophysical":
                all_nids = nodes.ids()
                if len(all_nids) < 20:
                    nid_list = all_nids  # Check all node IDs
                    print(f"Checking all morphologies in population '{npop}'")
                else:
                    nid_list = all_nids[[0, -1]]  # Check first/last node ID only
                    print(f"Checking first/last morphologies in population '{npop}'")
                for nid in nid_list:
                    try:
                        morph = nodes.morph.get(
                            nid, transform=True, extension=extension
                        )  # Will throw an error if not accessible
                    except:
                        return False  # Error
        return True  # All successful

    def run(self) -> None:
        try:
            print(f"Running morphology decontainerization for '{self.initialize.circuit_path}'")

            # Set logging level to WARNING to prevent a lot of debug output from morph_tool.convert()
            logging.getLogger("morph_tool").setLevel(logging.WARNING)

            # Copy contents of original circuit folder to output_root
            input_path, input_config = os.path.split(self.initialize.circuit_path.path)
            output_path = self.coordinate_output_root
            circuit_config = os.path.join(output_path, input_config)
            assert not os.path.exists(circuit_config), "ERROR: Output circuit already exists!"
            print("Copying circuit to output folder...")
            shutil.copytree(input_path, output_path, dirs_exist_ok=True)
            print("...DONE")

            # Load circuit at new location
            c = Circuit(circuit_config)
            node_populations = c.nodes.population_names

            # Iterate over node populations, find all morphologies and extract them from the .h5 container
            morph_folders_to_delete = []
            morph_containers_to_delete = []
            global_morph_entry = None
            for npop in node_populations:
                nodes = c.nodes[npop]
                if nodes.type != "biophysical":
                    continue
                morph_names = np.unique(nodes.get(properties="morphology"))
                print(
                    f"> {len(morph_names)} unique morphologies in population '{npop}' ({nodes.size})"
                )

                h5_container = nodes.morph._get_morphology_base(
                    "h5"
                )  # FIXME: Should not use private function!!
                assert os.path.splitext(h5_container)[1].lower() == ".h5", (
                    "ERROR: .h5 morphology path is not a container!"
                )
                h5_folder = os.path.join(os.path.split(h5_container)[0], "h5")
                target_folder = os.path.join(
                    os.path.split(h5_container)[0], self.initialize.output_format
                )
                os.makedirs(h5_folder, exist_ok=True)
                os.makedirs(target_folder, exist_ok=True)

                # Extract from .h5 container
                with h5py.File(h5_container, "r") as f_container:
                    skip_counter = 0
                    for _m in tqdm.tqdm(
                        morph_names, desc="Extracting/converting from .h5 container"
                    ):
                        _h5_file = os.path.join(h5_folder, _m + ".h5")
                        if os.path.exists(_h5_file):
                            skip_counter += 1
                        else:
                            # Create individual .h5 morphology file
                            with h5py.File(_h5_file, "w") as f_h5:
                                # Copy all groups/datasets into root of the file
                                for _key in f_container[_m].keys():
                                    f_container.copy(f_container[f"{_m}/{_key}"], f_h5)
                            # Convert to required output format
                            if self.initialize.output_format != "h5":
                                src_file = os.path.join(h5_folder, _m + ".h5")
                                dest_file = os.path.join(
                                    target_folder, _m + f".{self.initialize.output_format}"
                                )
                                if not os.path.exists(dest_file):
                                    convert(src_file, dest_file)
                print(
                    f"Extracted/converted {len(morph_names) - skip_counter} morphologies from .h5 container ({skip_counter} already existed)"
                )
                if h5_container not in morph_containers_to_delete:
                    morph_containers_to_delete.append(h5_container)
                if self.initialize.output_format != "h5":
                    if h5_folder not in morph_folders_to_delete:
                        morph_folders_to_delete.append(h5_folder)

                # Update the circuit config so that it points to the individual morphology folder,
                # keeping the original global/local config file structure as similar as it was before
                # (but removing all other references to the original morphology folders)
                cname, cext = os.path.splitext(circuit_config)
                # shutil.copy(circuit_config, cname + "__BAK__" + cext)  # Save original config file

                with open(circuit_config) as f:
                    cfg_dict = json.load(f)

                assert "manifest" in cfg_dict and "$BASE_DIR" in cfg_dict["manifest"], (
                    "ERROR: $BASE_DIR not defined!"
                )
                assert (
                    cfg_dict["manifest"]["$BASE_DIR"] == "."
                    or cfg_dict["manifest"]["$BASE_DIR"] == "./"
                ), "ERROR: $BASE_DIR is not corcuit root directory!"
                root_path = os.path.split(circuit_config)[0]
                rel_target_folder = os.path.join(
                    "$BASE_DIR", os.path.relpath(target_folder, root_path)
                )

                # Check if there is a global entry for morphologies (initially not set)
                if global_morph_entry is None:
                    global_morph_entry = False
                    if "components" in cfg_dict:
                        if "alternate_morphologies" in cfg_dict["components"]:
                            if "h5v1" in cfg_dict["components"]["alternate_morphologies"]:
                                if (
                                    len(cfg_dict["components"]["alternate_morphologies"]["h5v1"])
                                    > 0
                                ):
                                    global_morph_entry = True

                    if global_morph_entry:  # Set morphology path globally
                        if self.initialize.output_format == "h5":
                            cfg_dict["components"]["alternate_morphologies"] = {
                                "h5v1": rel_target_folder
                            }
                            if "morphologies_dir" in cfg_dict["components"]:
                                cfg_dict["components"]["morphologies_dir"] = ""
                        elif self.initialize.output_format == "asc":
                            cfg_dict["components"]["alternate_morphologies"] = {
                                "neurolucida-asc": rel_target_folder
                            }
                            if "morphologies_dir" in cfg_dict["components"]:
                                cfg_dict["components"]["morphologies_dir"] = ""
                        else:
                            cfg_dict["components"]["morphologies_dir"] = rel_target_folder
                            if "alternate_morphologies" in cfg_dict["components"]:
                                cfg_dict["components"]["alternate_morphologies"] = {}
                if not global_morph_entry:  # Set individually per population
                    for _ndict in cfg_dict["networks"]["nodes"]:
                        if nodes.name in _ndict["populations"]:
                            _pop = _ndict["populations"][nodes.name]
                            base_path = None
                            if self.initialize.output_format == "h5":
                                _pop["alternate_morphologies"] = {"h5v1": h5_folder}
                                if "morphologies_dir" in _pop:
                                    _pop["morphologies_dir"] = ""
                            elif self.initialize.output_format == "asc":
                                _pop["alternate_morphologies"] = {
                                    "neurolucida-asc": rel_target_folder
                                }
                                if "morphologies_dir" in _pop:
                                    _pop["morphologies_dir"] = ""
                            else:
                                _pop["morphologies_dir"] = rel_target_folder
                                if "alternate_morphologies" in _pop:
                                    _pop["alternate_morphologies"] = {}
                            break
                else:
                    pass  # Skip, should be already set

                with open(circuit_config, "w") as f:
                    json.dump(cfg_dict, f, indent=2)

            # Clean up morphology folders with individual morphologies
            print(f"Cleaning morphology container(s): {morph_containers_to_delete}")
            for _file in morph_containers_to_delete:
                os.remove(_file)
            print(f"Cleaning morphology folder(s): {morph_folders_to_delete}")
            for _folder in morph_folders_to_delete:
                shutil.rmtree(_folder)

            # Reload and check morphologies in modified circuit
            assert self._check_morphologies(circuit_config, self.initialize.output_format), (
                "ERROR: Morphology check not successful!"
            )
            print("Morphology decontainerization DONE")

        except Exception as e:
            traceback.print_exception(e)
