import datetime
import json
import logging
import os
import shutil
from importlib.metadata import version
from pathlib import Path
from typing import ClassVar

import bluepysnap as snap
import entitysdk.client
import h5py
import numpy as np
import tqdm
from bluepysnap import BluepySnapError
from morph_tool import convert
from morphio import MorphioError

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.library.circuit import Circuit

L = logging.getLogger(__name__)


class MorphologyContainerizationScanConfig(ScanConfig):
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

    single_coord_class_name: ClassVar[str] = "MorphologyContainerizationSingleConfig"
    name: ClassVar[str] = "Morphology Containerization"
    description: ClassVar[str] = (
        "Creates a circuit with containerized morphologies instead of individual morphology files"
    )

    class Initialize(Block):
        circuit: Circuit | list[Circuit]
        hoc_template_old: str
        hoc_template_new: str

    initialize: Initialize


class MorphologyContainerizationSingleConfig(
    MorphologyContainerizationScanConfig, SingleConfigMixin
):
    pass


class MorphologyContainerizationTask(Task):
    config: MorphologyContainerizationSingleConfig

    CONTAINER_FILENAME: ClassVar[str] = "merged-morphologies.h5"
    NO_MORPH_NAME: ClassVar[str] = "_NONE"

    @staticmethod
    def _filter_ext(file_list: list, ext: str) -> list:
        """Filter file list based on file extension."""
        return list(filter(lambda f: Path(f).suffix.lower() == f".{ext}", file_list))

    @classmethod
    def _load_node_population(
        cls, c: snap.Circuit, npop: str
    ) -> (snap.nodes.NodePopulation, np.ndarray):
        nodes = c.nodes[npop]
        if nodes.type != "biophysical":
            morph_names = None
        else:
            morph_names = np.unique(nodes.get(properties="morphology"))
            if cls.NO_MORPH_NAME in morph_names:
                L.info(
                    f"WARNING: Biophysical population '{npop}' has neurons without \
                        morphologies!"
                )
                morph_names = morph_names[morph_names != cls.NO_MORPH_NAME]
                if len(morph_names) == 0:
                    msg = f"ERROR: Biophysical population '{npop}' does not have any morphologies!"
                    raise ValueError(msg)
            L.info(
                f"> {len(morph_names)} unique morphologies in population '{npop}' \
                    ({nodes.size})"
            )
        return nodes, morph_names

    @staticmethod
    def _check_morph_folders(
        nodes: snap.nodes.NodePopulation, morph_folders_to_delete: list
    ) -> list:
        """Check existence and contents of morphology folders."""
        morph_folders = {}
        for _morph_ext in ["h5", "asc", "swc"]:
            try:
                morph_folder = nodes.morph.get_morphology_dir(_morph_ext)
            except BluepySnapError:
                # Path not defined in circuit config
                morph_folder = None

            if morph_folder is not None and not Path(morph_folder).exists():
                # Morphology folder does not exist
                morph_folder = None

            if (
                morph_folder is not None
                and len(
                    MorphologyContainerizationTask._filter_ext(
                        Path(morph_folder).iterdir(), _morph_ext
                    )
                )
                == 0
            ):
                # Morphology folder does not contain morphologies
                morph_folder = None

            if morph_folder is not None and morph_folder not in morph_folders_to_delete:
                morph_folders_to_delete.append(morph_folder)

            morph_folders[_morph_ext] = morph_folder

        return morph_folders

    @staticmethod
    def _convert_to_h5(morph_folders: dict, morph_names: list) -> Path:
        """If .h5 morphologies not existing, run .asc/.swc to .h5 conversion."""
        h5_folder = morph_folders["h5"]
        if h5_folder is None:
            for _morph_ext in ["asc", "swc"]:
                inp_folder = morph_folders[_morph_ext]
                if inp_folder is not None:
                    break
            if inp_folder is None:
                msg = "ERROR: No morphologies found to convert to .h5!"
                raise ValueError(msg)
            h5_folder = Path(os.path.split(inp_folder)[0]) / "_h5_morphologies_tmp_"
            Path(h5_folder).mkdir(parents=True, exist_ok=True)

            for _m in tqdm.tqdm(morph_names, desc=f"Converting .{_morph_ext} to .h5"):
                src_file = Path(inp_folder) / (_m + f".{_morph_ext}")
                dest_file = Path(h5_folder) / (_m + ".h5")
                if not Path(dest_file).exists():
                    convert(src_file, dest_file)
        return h5_folder

    def _merge_into_h5_container(self, h5_folder: Path, morph_names: list) -> Path:
        """Merge .h5 morphologies into .h5 container."""
        if h5_folder is None:
            msg = "ERROR: .h5 container folder undefined!"
            raise ValueError(msg)
        h5_container = Path(os.path.split(h5_folder)[0]) / self.CONTAINER_FILENAME
        with h5py.File(h5_container, "a") as f_container:
            skip_counter = 0
            for _m in tqdm.tqdm(morph_names, desc="Merging .h5 into container"):
                with h5py.File(Path(h5_folder) / (_m + ".h5")) as f_h5:
                    if _m in f_container:
                        skip_counter += 1
                    else:
                        f_h5.copy(f_h5, f_container, name=_m)
        L.info(
            f"Merged {len(morph_names) - skip_counter} morphologies into container \
                ({skip_counter} already existed)"
        )
        return h5_container

    @classmethod
    def _set_global_morph_entry(cls, *, global_morph_entry: bool, cfg_dict: dict) -> bool:
        """Check and set path if there is a global entry for morphologies (initially not set)."""
        if global_morph_entry is not None:
            return global_morph_entry

        global_morph_entry = False
        if "components" in cfg_dict:
            if (
                "morphologies_dir" in cfg_dict["components"]
                and len(cfg_dict["components"]["morphologies_dir"]) > 0
            ):
                base_path = os.path.split(cfg_dict["components"]["morphologies_dir"])[0]
                cfg_dict["components"]["morphologies_dir"] = ""  # Remove .swc path
                global_morph_entry = True
            if "alternate_morphologies" in cfg_dict["components"]:
                if (
                    "neurolucida-asc" in cfg_dict["components"]["alternate_morphologies"]
                    and len(cfg_dict["components"]["alternate_morphologies"]["neurolucida-asc"]) > 0
                ):
                    base_path = os.path.split(
                        cfg_dict["components"]["alternate_morphologies"]["neurolucida-asc"]
                    )[0]
                    cfg_dict["components"]["alternate_morphologies"]["neurolucida-asc"] = (
                        ""  # Remove .asc path
                    )
                    global_morph_entry = True
                if (
                    "h5v1" in cfg_dict["components"]["alternate_morphologies"]
                    and len(cfg_dict["components"]["alternate_morphologies"]["h5v1"]) > 0
                ):
                    base_path = os.path.split(
                        cfg_dict["components"]["alternate_morphologies"]["h5v1"]
                    )[0]
                    cfg_dict["components"]["alternate_morphologies"]["h5v1"] = ""  # Remove .h5 path
                    global_morph_entry = True
            if global_morph_entry:
                # Set .h5 container path globally
                h5_file = Path(base_path) / cls.CONTAINER_FILENAME
                cfg_dict["components"]["alternate_morphologies"] = {"h5v1": str(h5_file)}
        return global_morph_entry

    @classmethod
    def _set_morph_entries_per_population(
        cls, *, global_morph_entry: bool, cfg_dict: dict, nodes: snap.nodes.NodePopulation
    ) -> None:
        """Set morphology entries individually per population."""
        if global_morph_entry is None:
            msg = "ERROR: Global morphology entry flag undefined!"
            raise ValueError(msg)

        if global_morph_entry:
            # Skip, should be already set
            return

        for _ndict in cfg_dict["networks"]["nodes"]:
            if nodes.name in _ndict["populations"]:
                pop = _ndict["populations"][nodes.name]
                base_path = None
                if "morphologies_dir" in pop and len(pop["morphologies_dir"]) > 0:
                    base_path = os.path.split(pop["morphologies_dir"])[0]
                    pop["morphologies_dir"] = ""  # Remove .swc path
                if "alternate_morphologies" in pop:
                    if "neurolucida-asc" in pop["alternate_morphologies"]:
                        base_path = os.path.split(pop["alternate_morphologies"]["neurolucida-asc"])[
                            0
                        ]
                        pop["alternate_morphologies"]["neurolucida-asc"] = ""  # Remove .asc path
                    if "h5v1" in pop["alternate_morphologies"]:
                        base_path = os.path.split(pop["alternate_morphologies"]["h5v1"])[0]
                        pop["alternate_morphologies"]["h5v1"] = ""  # Remove .h5 path
                if base_path is None:
                    msg = f"ERROR: Morphology path for population '{nodes.name}' unknown!"
                    raise ValueError(msg)
                h5_file = Path(base_path) / cls.CONTAINER_FILENAME
                pop["alternate_morphologies"] = {"h5v1": str(h5_file)}
                break

    @staticmethod
    def _check_morphologies(circuit_config: Path) -> bool:
        """Check modified circuit by loading some .h5 morphologies from each node population."""
        c = snap.Circuit(circuit_config)
        for npop in c.nodes.population_names:
            nodes = c.nodes[npop]
            if nodes.type == "biophysical":
                node_morphs = nodes.get(properties="morphology")
                node_ids = node_morphs[
                    node_morphs != MorphologyContainerizationTask.NO_MORPH_NAME
                ].index
                for nid in node_ids[[0, -1]]:  # First/last node ID (with actual morphology!!)
                    try:
                        _ = nodes.morph.get(
                            nid, transform=True, extension="h5"
                        )  # Will throw an error if not accessible
                    except (MorphioError, ValueError):
                        return False  # Error
        return True  # All successful

    @staticmethod
    def _find_hoc_proc(proc_name: str, hoc_code: str) -> (int, int, str):
        """Find a procedure with a given name in hoc code."""
        start_idx = hoc_code.find(f"proc {proc_name}")
        if start_idx < 0:
            msg = f"ERROR: '{proc_name}' not found!"
            raise ValueError(msg)
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
    def _find_hoc_header(hoc_code: str) -> (int, int, str):
        """Find the header section in hoc code."""
        start_idx = hoc_code.find("/*")  # First occurrence
        if start_idx != 0:
            msg = "ERROR: Header not found!"
            raise ValueError(msg)
        end_idx = hoc_code.find("*/")  # First occurrence
        if end_idx <= 0:
            msg = "ERROR: Header not found!"
            raise ValueError(msg)
        return start_idx, end_idx, hoc_code[start_idx : end_idx + 2]

    def _update_hoc_files(self, hoc_folder: str) -> None:
        """Update hoc files in a folder from code of an old to code from a new template."""
        # Extract code to be replaced from hoc templates
        tmpl_old = Path(self.config.initialize.hoc_template_old).read_text(encoding="utf-8")
        tmpl_new = Path(self.config.initialize.hoc_template_new).read_text(encoding="utf-8")

        proc_name = "load_morphology"
        _, _, hoc_code_old = self._find_hoc_proc(proc_name, tmpl_old)
        _, _, hoc_code_new = self._find_hoc_proc(proc_name, tmpl_new)

        # Replace code in hoc files
        for _file in tqdm.tqdm(Path(hoc_folder).iterdir(), desc="Updating .hoc files"):
            if Path(_file).suffix.lower() != ".hoc":
                continue
            hoc_file = Path(hoc_folder) / _file
            hoc = Path(hoc_file).read_text(encoding="utf-8")
            if hoc.find(hoc_code_new) > 0:
                L.info(f"New code version already found - Skipping update of '{_file}'!")
                continue  # Already new code version
            if hoc.find(hoc_code_old) < 0:
                msg = "ERROR: Old HOC code to replace not found!"
                raise ValueError(msg)
            hoc_new = hoc.replace(hoc_code_old, hoc_code_new)
            _, _, header = self._find_hoc_header(hoc)
            module_name = self.__module__.split(".")[0]
            header_new = header.replace(
                "*/",
                f"Updated '{proc_name}' based on \
                    '{os.path.split(self.config.initialize.hoc_template_new)[1]}' \
                        by {module_name}({version(module_name)}) at \
                        {datetime.datetime.now(tz=datetime.UTC)}\n*/",
            )
            hoc_new = hoc_new.replace(header, header_new)
            Path(hoc_file).write_text(hoc_new, encoding="utf-8")

    def _update_hoc_folder(
        self, nodes: snap.nodes.NodePopulation, hoc_folders_updated: list
    ) -> str:
        hoc_folder = nodes.config["biophysical_neuron_models_dir"]
        if not Path(hoc_folder).exists():
            L.info("WARNING: Biophysical neuron models dir missing!")
        elif hoc_folder not in hoc_folders_updated:
            self._update_hoc_files(hoc_folder)
            hoc_folders_updated.append(hoc_folder)
        return hoc_folder

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
    ) -> None:
        L.info(f"Running morphology containerization for '{self.config.initialize.circuit}'")

        # Set logging level to WARNING to prevent large debug output from morph_tool.convert()
        logging.getLogger("morph_tool").setLevel(logging.WARNING)

        # Copy contents of original circuit folder to output_root
        input_path, input_config = os.path.split(self.config.initialize.circuit.path)
        output_path = self.config.coordinate_output_root
        circuit_config = Path(output_path) / input_config
        if Path(circuit_config).exists():
            msg = "ERROR: Output circuit already exists!"
            raise ValueError(msg)
        L.info("Copying circuit to output folder...")
        shutil.copytree(input_path, output_path, dirs_exist_ok=True)
        L.info("...DONE")

        # Load circuit at new location
        c = snap.Circuit(circuit_config)
        node_populations = c.nodes.population_names

        # Iterate over node populations to find all morphologies, convert them if needed,
        # and merge them into a .h5 container

        # Keep track of updated folders (in case of different ones for different populations)
        hoc_folders_updated = []

        # Keep track of morphology folders (to be deleted afterwards)
        morph_folders_to_delete = []

        # Keep track wheter the circuit config has a global component entry for morphologies
        global_morph_entry = None

        for npop in node_populations:
            # Load node population & morphologies
            nodes, morph_names = self._load_node_population(c, npop)
            if morph_names is None:
                continue

            # Check morphology folders
            morph_folders = self._check_morph_folders(nodes, morph_folders_to_delete)

            # If .h5 morphologies not existing, run .asc/.swc to .h5 conversion
            h5_folder = self._convert_to_h5(morph_folders, morph_names)
            if h5_folder not in morph_folders_to_delete:
                morph_folders_to_delete.append(h5_folder)

            # Merge into .h5 container
            self._merge_into_h5_container(h5_folder, morph_names)

            # Update the circuit config so that it points to the .h5 container file,
            # keeping the original global/local config file structure as similar as it was
            # before (but removing all other references to the original morphology folders)

            # Save original config file
            # cname, cext = os.path.splitext(circuit_config)  # noqa: ERA001
            # shutil.copy(circuit_config, cname + "__BAK__" + cext)  # noqa: ERA001

            with Path(circuit_config).open(encoding="utf-8") as f:
                cfg_dict = json.load(f)

            # Check and set if there is a global entry for morphologies (initially not set)
            global_morph_entry = self._set_global_morph_entry(
                global_morph_entry=global_morph_entry, cfg_dict=cfg_dict
            )

            # Otherwise, set individually per population
            self._set_morph_entries_per_population(
                global_morph_entry=global_morph_entry, cfg_dict=cfg_dict, nodes=nodes
            )

            with Path(circuit_config).open("w", encoding="utf-8") as f:
                json.dump(cfg_dict, f, indent=2)

            # Update hoc files (in place)
            self._update_hoc_folder(nodes, hoc_folders_updated)

        # Clean up morphology folders with individual morphologies
        L.info(f"Cleaning morphology folders: {morph_folders_to_delete}")
        for _folder in morph_folders_to_delete:
            shutil.rmtree(_folder)

        # Reload and check morphologies in modified circuit
        if not self._check_morphologies(circuit_config):
            msg = "ERROR: Morphology check not successful!"
            raise ValueError(msg)
        L.info("Morphology containerization DONE")
