from typing import ClassVar

from obi_one.core.block import Block
from obi_one.core.form import Form
from obi_one.core.path import NamedPath
from obi_one.core.single import SingleCoordinateMixin


class MorphologyContainerizationsForm(Form):
    """ """

    single_coord_class_name: ClassVar[str] = "MorphologyContainerization"
    name: ClassVar[str] = "Morphology Containerization"
    description: ClassVar[str] = (
        "Creates a circuit with containerized morphologies instead of individual morphology files"
    )

    class Initialize(Block):
        circuit_path: NamedPath | list[NamedPath]
        hoc_template_old: str
        hoc_template_new: str

    initialize: Initialize


import datetime
import json
import logging
import os
import shutil
import traceback
from importlib.metadata import version
from typing import ClassVar

import h5py
import numpy as np
import tqdm
from bluepysnap import Circuit
from morph_tool import convert


class MorphologyContainerization(MorphologyContainerizationsForm, SingleCoordinateMixin):
    """Creates a circuit with containerized morphologies instead of individual morphology files,
    which involves the following steps:
    (1) Copy circuit to output location
    (2) Convert morphologies to .h5, if not yet existing (from .swc or .asc)
    (3) Merge individual .h5 morphologies into an .h5 container
    (4) Update the circuit config, pointing to the .h5 container
    (5) Update .hoc files so that they will work with .h5 containers
    (6) Delete all individual morphologies
    (7) Check containerized morphologies
    Important: The original circuit won't be modified! The circuit will be copied
               to the output location where all operations take place.
    """

    CONTAINER_FILENAME: ClassVar[str] = "merged-morphologies.h5"

    @staticmethod
    def _filter_ext(file_list, ext):
        """Filter file list based on file extension."""
        return list(filter(lambda f: os.path.splitext(f)[1].lower() == f".{ext}", file_list))

    @staticmethod
    def _check_morphologies(circuit_config):
        """Check modified circuit by loading some .h5 morphologies from each node population."""
        c = Circuit(circuit_config)
        for npop in c.nodes.population_names:
            nodes = c.nodes[npop]
            if nodes.type == "biophysical":
                for nid in nodes.ids()[[0, -1]]:  # First/last node ID
                    try:
                        morph = nodes.morph.get(
                            nid, transform=True, extension="h5"
                        )  # Will throw an error if not accessible
                    except:
                        return False  # Error
        return True  # All successful

    @staticmethod
    def _find_hoc_proc(proc_name, hoc_code):
        """Find a procedure with a given name in hoc code."""
        start_idx = hoc_code.find(f"proc {proc_name}")
        assert start_idx >= 0, f"ERROR: '{proc_name}' not found!"
        counter = 0
        has_first = False
        for _idx in range(start_idx, len(hoc_code)):
            if hoc_code[_idx] == "{":
                counter += 1
                has_first = True
            elif hoc_code[_idx] == "}":
                counter -= 1
            if has_first and counter == 0:
                end_idx = _idx
                break
        return start_idx, end_idx, hoc_code[start_idx : end_idx + 1]

    @staticmethod
    def _find_hoc_header(hoc_code):
        """Find the header section in hoc code."""
        start_idx = hoc_code.find("/*")  # First occurrence
        assert start_idx == 0, "ERROR: Header not found!"
        end_idx = hoc_code.find("*/")  # First occurrence
        assert end_idx > 0, "ERROR: Header not found!"
        return start_idx, end_idx, hoc_code[start_idx : end_idx + 2]

    def _update_hoc_files(self, hoc_folder):
        """Update hoc files in a folder from code of an old to code from a new template."""
        # TODO: CHECK IF .HOC FILE IS ALREADY NEW VERSION??
        # Extract code to be replaced from hoc templates
        with open(self.initialize.hoc_template_old) as f:
            tmpl_old = f.read()
        with open(self.initialize.hoc_template_new) as f:
            tmpl_new = f.read()

        proc_name = "load_morphology"
        _, _, hoc_code_old = self._find_hoc_proc(proc_name, tmpl_old)
        _, _, hoc_code_new = self._find_hoc_proc(proc_name, tmpl_new)

        # Replace code in hoc files
        for _file in tqdm.tqdm(os.listdir(hoc_folder), desc="Updating .hoc files"):
            if os.path.splitext(_file)[1].lower() != ".hoc":
                continue
            hoc_file = os.path.join(hoc_folder, _file)
            with open(hoc_file) as f:
                hoc = f.read()
            assert hoc.find(hoc_code_old) >= 0, "ERROR: Old HOC code to replace not found!"
            hoc_new = hoc.replace(hoc_code_old, hoc_code_new)
            _, _, header = self._find_hoc_header(hoc)
            module_name = self.__module__.split(".")[0]
            header_new = header.replace(
                "*/",
                f"Updated '{proc_name}' based on '{os.path.split(self.initialize.hoc_template_new)[1]}' by {module_name}({version(module_name)}) at {datetime.datetime.now()}\n*/",
            )
            hoc_new = hoc_new.replace(header, header_new)
            with open(hoc_file, "w") as f:
                f.write(hoc_new)

    def run(self) -> None:
        try:
            print(f"Running morphology containerization for '{self.initialize.circuit_path}'")

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

            # Iterate over node populations to find all morphologies, convert them if needed, and merge them into a .h5 container
            hoc_folders_updated = []  # Keep track of updated folders (in case of different ones for different populations)
            morph_folders_to_delete = []  # Keep track of morphology folders (to be deleted afterwards)
            global_morph_entry = None  # Keep track wheter or not the circuit config has a global component entry for morphologies
            for npop in node_populations:
                nodes = c.nodes[npop]
                if nodes.type != "biophysical":
                    continue
                morph_names = np.unique(nodes.get(properties="morphology"))
                print(
                    f"> {len(morph_names)} unique morphologies in population '{npop}' ({nodes.size})"
                )

                # Check morphology folders
                morph_folders = {}
                for _morph_ext in ["h5", "asc", "swc"]:
                    try:
                        morph_folder = nodes.morph.get_morphology_dir(_morph_ext)
                        assert os.path.exists(morph_folder), (
                            f"ERROR: {_morph_ext} morphology folder does not exist!"
                        )
                        assert len(self._filter_ext(os.listdir(morph_folder), _morph_ext)) > 0, (
                            f"ERROR: {_morph_ext} morphology folder does not contain morphologies!"
                        )
                        if morph_folder not in morph_folders_to_delete:
                            morph_folders_to_delete.append(morph_folder)
                    except:
                        morph_folder = None
                    morph_folders[_morph_ext] = morph_folder

                # If .h5 morphologies not existing, run .asc/.swc to .h5 conversion
                h5_folder = morph_folders["h5"]
                if h5_folder is None:
                    for _morph_ext in ["asc", "swc"]:
                        inp_folder = morph_folders[_morph_ext]
                        if inp_folder is not None:
                            break
                    assert inp_folder is not None, "ERROR: No morphologies found to convert to .h5!"
                    h5_folder = os.path.join(os.path.split(inp_folder)[0], "_h5_morphologies_tmp_")
                    os.makedirs(h5_folder, exist_ok=True)

                    for _m in tqdm.tqdm(morph_names, desc=f"Converting .{_morph_ext} to .h5"):
                        src_file = os.path.join(inp_folder, _m + f".{_morph_ext}")
                        dest_file = os.path.join(h5_folder, _m + ".h5")
                        if not os.path.exists(dest_file):
                            convert(src_file, dest_file)

                # Merge into .h5 container
                if h5_folder not in morph_folders_to_delete:
                    morph_folders_to_delete.append(h5_folder)
                h5_container = os.path.join(os.path.split(h5_folder)[0], self.CONTAINER_FILENAME)
                with h5py.File(h5_container, "a") as f_container:
                    skip_counter = 0
                    for _m in tqdm.tqdm(morph_names, desc="Merging .h5 into container"):
                        with h5py.File(os.path.join(h5_folder, _m + ".h5")) as f_h5:
                            if _m in f_container:
                                skip_counter += 1
                            else:
                                f_h5.copy(f_h5, f_container, name=_m)
                print(
                    f"Merged {len(morph_names) - skip_counter} morphologies into container ({skip_counter} already existed)"
                )

                # Update the circuit config so that it points to the .h5 container file,
                # keeping the original global/local config file structure as similar as it was before
                # (but removing all other references to the original morphology folders)
                cname, cext = os.path.splitext(circuit_config)
                # shutil.copy(circuit_config, cname + "__BAK__" + cext)  # Save original config file

                with open(circuit_config) as f:
                    cfg_dict = json.load(f)

                if (
                    global_morph_entry is None
                ):  # Check if there is a global entry for morphologies (initially not set)
                    global_morph_entry = False
                    if "components" in cfg_dict:
                        if "morphologies_dir" in cfg_dict["components"]:
                            if len(cfg_dict["components"]["morphologies_dir"]) > 0:
                                base_path = os.path.split(
                                    cfg_dict["components"]["morphologies_dir"]
                                )[0]
                                cfg_dict["components"]["morphologies_dir"] = ""  # Remove .swc path
                                global_morph_entry = True
                        if "alternate_morphologies" in cfg_dict["components"]:
                            if (
                                "neurolucida-asc"
                                in cfg_dict["components"]["alternate_morphologies"]
                            ):
                                if (
                                    len(
                                        cfg_dict["components"]["alternate_morphologies"][
                                            "neurolucida-asc"
                                        ]
                                    )
                                    > 0
                                ):
                                    base_path = os.path.split(
                                        cfg_dict["components"]["alternate_morphologies"][
                                            "neurolucida-asc"
                                        ]
                                    )[0]
                                    cfg_dict["components"]["alternate_morphologies"][
                                        "neurolucida-asc"
                                    ] = ""  # Remove .asc path
                                    global_morph_entry = True
                            if "h5v1" in cfg_dict["components"]["alternate_morphologies"]:
                                if (
                                    len(cfg_dict["components"]["alternate_morphologies"]["h5v1"])
                                    > 0
                                ):
                                    base_path = os.path.split(
                                        cfg_dict["components"]["alternate_morphologies"]["h5v1"]
                                    )[0]
                                    cfg_dict["components"]["alternate_morphologies"]["h5v1"] = (
                                        ""  # Remove .h5 path
                                    )
                                    global_morph_entry = True
                        if global_morph_entry:
                            # Set .h5 container path globally
                            h5_file = os.path.join(base_path, self.CONTAINER_FILENAME)
                            cfg_dict["components"]["alternate_morphologies"] = {"h5v1": h5_file}

                if not global_morph_entry:  # Set individually per population
                    for _ndict in cfg_dict["networks"]["nodes"]:
                        if nodes.name in _ndict["populations"]:
                            _pop = _ndict["populations"][nodes.name]
                            base_path = None
                            if "morphologies_dir" in _pop:
                                if len(_pop["morphologies_dir"]) > 0:
                                    base_path = os.path.split(_pop["morphologies_dir"])[0]
                                    _pop["morphologies_dir"] = ""  # Remove .swc path
                            if "alternate_morphologies" in _pop:
                                if "neurolucida-asc" in _pop["alternate_morphologies"]:
                                    base_path = os.path.split(
                                        _pop["alternate_morphologies"]["neurolucida-asc"]
                                    )[0]
                                    _pop["alternate_morphologies"]["neurolucida-asc"] = (
                                        ""  # Remove .asc path
                                    )
                                if "h5v1" in _pop["alternate_morphologies"]:
                                    base_path = os.path.split(
                                        _pop["alternate_morphologies"]["h5v1"]
                                    )[0]
                                    _pop["alternate_morphologies"]["h5v1"] = ""  # Remove .h5 path
                            assert base_path is not None, (
                                f"ERROR: Morphology path for population '{nodes.name}' unknown!"
                            )
                            h5_file = os.path.join(base_path, self.CONTAINER_FILENAME)
                            _pop["alternate_morphologies"] = {"h5v1": h5_file}
                            break
                else:
                    pass  # Skip, should be already set

                with open(circuit_config, "w") as f:
                    json.dump(cfg_dict, f, indent=2)

                # Update hoc files (in place)
                hoc_folder = nodes.config["biophysical_neuron_models_dir"]
                if hoc_folder not in hoc_folders_updated:
                    self._update_hoc_files(hoc_folder)
                    hoc_folders_updated.append(hoc_folder)

            # Clean up morphology folders with individual morphologies
            print(f"Cleaning morphology folders: {morph_folders_to_delete}")
            for _folder in morph_folders_to_delete:
                shutil.rmtree(_folder)

            # Reload and check morphologies in modified circuit
            assert self._check_morphologies(circuit_config), (
                "ERROR: Morphology check not successful!"
            )
            print("Morphology containerization DONE")

        except Exception as e:
            traceback.print_exception(e)
