from obi.modeling.core.form import Form
from obi.modeling.core.block import Block
from obi.modeling.core.single import SingleCoordinateMixin
from obi.modeling.core.base import NamedPath

class MorphologyContainerizationsForm(Form):
    """
    """

    _single_coord_class_name = "MorphologyContainerization"

    class Initialize(Block):
        circuit_path: NamedPath | list[NamedPath]
        hoc_template_old: str
        hoc_template_new: str

    initialize: Initialize


import datetime
import h5py
import json
import numpy as np
import os
import shutil
import tqdm
import traceback
from bluepysnap import Circuit
from importlib.metadata import version
from morph_tool import convert
from typing import ClassVar

class MorphologyContainerization(MorphologyContainerizationsForm, SingleCoordinateMixin):
    """
    """

    CONTAINER_FILENAME: ClassVar[str] = "merged-morphologies.h5"

    @staticmethod
    def _find_hoc_proc(proc_name, hoc_code):
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
        start_idx = hoc_code.find("/*")  # First occurrence
        assert start_idx == 0, "ERROR: Header not found!"
        end_idx = hoc_code.find("*/")  # First occurrence
        assert end_idx > 0, "ERROR: Header not found!"
        return start_idx, end_idx, hoc_code[start_idx : end_idx + 2]

    def _update_hoc_files(self, hoc_folder):
        # TODO: CHECK IF ALREADY NEW VERSION??
        # Extract code to be replaced from hoc templates
        with open(self.initialize.hoc_template_old, "r") as f:
            tmpl_old = f.read()
        with open(self.initialize.hoc_template_new, "r") as f:
            tmpl_new = f.read()

        proc_name = "load_morphology"
        _, _, hoc_code_old = self._find_hoc_proc(proc_name, tmpl_old)
        _, _, hoc_code_new = self._find_hoc_proc(proc_name, tmpl_new)

        # Replace code in hoc files
        for _file in tqdm.tqdm(os.listdir(hoc_folder), desc="Updating .hoc files"):
            if os.path.splitext(_file)[1].lower() != ".hoc":
                continue
            hoc_file = os.path.join(hoc_folder, _file)
            with open(hoc_file, "r") as f:
                hoc = f.read()
            assert hoc.find(hoc_code_old) >= 0, "ERROR: Old HOC code to replace not found!"
            hoc_new = hoc.replace(hoc_code_old, hoc_code_new)
            _, _, header = self._find_hoc_header(hoc)
            module_name = self.__module__.split('.')[0]
            header_new = header.replace("*/", f"Updated '{proc_name}' based on '{os.path.split(self.initialize.hoc_template_new)[1]}' by {module_name}({version(module_name)}) at {datetime.datetime.now()}\n*/")
            hoc_new = hoc_new.replace(header, header_new)
            with open(hoc_file, "w") as f:
                f.write(hoc_new)

    def run(self) -> None:

        try:
            print(f"Info: Running morphology containerization for '{self.initialize.circuit_path}'")

            # Copy contents of original circuit folder to output_root
            input_path, input_config = os.path.split(self.initialize.circuit_path.path)
            output_path = self.coordinate_output_root
            circuit_config = os.path.join(output_path, input_config)
            assert not os.path.exists(circuit_config), "ERROR: Output circuit already exists!"
            print("Copying circuit to output folder...")
            shutil.copytree(input_path, output_path, dirs_exist_ok=True)
            print("...DONE")

            c = Circuit(circuit_config)
            node_populations = c.nodes.population_names
            hoc_folders_updated = []  # Keep track of updated folders (in case of different ones for different populations)
            morph_folders_to_delete = []  # Keep track of morphology folders (to be deleted afterwards)
            for npop in node_populations:
                nodes = c.nodes[npop]
                if nodes.type != "biophysical":
                    continue
                morph_names = np.unique(nodes.get(properties="morphology"))
                print(f"> {len(morph_names)} unique morphologies in population '{npop}' ({nodes.size})")

                # Check morphology folders
                morph_folders = {}
                for _morph_ext in ["h5", "asc", "swc"]:
                    try:
                        morph_folder = nodes.morph.get_morphology_dir(_morph_ext)
                        assert os.path.exists(morph_folder), f"ERROR: {_morph_ext} morphology folder does not exist!"
                        assert len(os.listdir(morph_folder)) > 0, f"ERROR: {_morph_ext} morphology folder is empty!"
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
                if h5_folder not in morph_folders:
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
                print(f"INFO: Merged {len(morph_names) - skip_counter} morphologies into container ({skip_counter} already existed)")

                # Update circuit config
                cname, cext = os.path.splitext(circuit_config)
                # shutil.copy(circuit_config, cname + "__BAK__" + cext)  # Save original config file

                with open(circuit_config, "r") as f:
                    cfg_dict = json.load(f)

                # TODO: Fix for hippocampus
                if "components" in cfg_dict:
                    if "morphologies_dir" in cfg_dict["components"]:
                        if len(cfg_dict["components"]["morphologies_dir"]) > 0:
                            global_morph_dir = True
                for _ndict in cfg_dict["networks"]["nodes"]:
                    if nodes.name in _ndict["populations"]:
                        _pop = _ndict["populations"][nodes.name]
                        _pop["alternate_morphologies"]["h5v1"] = os.path.join(os.path.split(_pop["alternate_morphologies"]["neurolucida-asc"])[0], self.CONTAINER_FILENAME)
                        break

                with open(circuit_config, "w") as f:
                    json.dump(cfg_dict, f, indent=2)

                # Update hoc files (in place)
                hoc_folder = nodes.config["biophysical_neuron_models_dir"]
                if hoc_folder not in hoc_folders_updated:
                    self._update_hoc_files(hoc_folder)
                    hoc_folders_updated.append(hoc_folder)

            # Cleanup morphology folders
            # TODO
            # for _folder in morph_folders_to_delete:
            #     print(f"Deleting morphology")
            #     shutil.rmtree(_folder)

        except Exception as e:
            traceback.print_exception(e)
