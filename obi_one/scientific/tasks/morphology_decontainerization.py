import json
import logging
import os
import shutil
from pathlib import Path
from typing import ClassVar, Literal

import bluepysnap as snap
import entitysdk.client
import h5py
import numpy as np
import tqdm
from morph_tool import convert
from morphio import MorphioError

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.library.circuit import Circuit

N_NEURONS_FOR_CHECK = 20

L = logging.getLogger(__name__)


class MorphologyDecontainerizationScanConfig(ScanConfig):
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

    single_coord_class_name: ClassVar[str] = "MorphologyDecontainerizationSingleConfig"
    name: ClassVar[str] = "Morphology Decontainerization"
    description: ClassVar[str] = (
        "Creates a circuit with individual morphology files instead of containerized morphologies"
    )

    class Initialize(Block):
        circuit: Circuit | list[Circuit]
        output_format: Literal["h5", "asc", "swc"] | list[Literal["h5", "asc", "swc"]] = "h5"

    initialize: Initialize


class MorphologyDecontainerizationSingleConfig(
    MorphologyDecontainerizationScanConfig, SingleConfigMixin
):
    pass


class MorphologyDecontainerizationTask(Task):
    config: MorphologyDecontainerizationSingleConfig

    def _copy_circuit_folder(self) -> Path:
        input_path, input_config = os.path.split(self.config.initialize.circuit.path)
        output_path = self.config.coordinate_output_root
        circuit_config = Path(output_path) / input_config
        if Path(circuit_config).exists():
            msg = "ERROR: Output circuit already exists!"
            raise ValueError(msg)
        L.info("Copying circuit to output folder...")
        shutil.copytree(input_path, output_path, dirs_exist_ok=True)
        L.info("...DONE")
        return circuit_config

    def _load_node_population(
        self, c: snap.Circuit, npop: str
    ) -> (snap.nodes.NodePopulation, np.ndarray, str, Path, Path):
        nodes = c.nodes[npop]
        if nodes.type != "biophysical":
            morph_names = None
            h5_container = None
            h5_folder = None
            target_folder = None
        else:
            morph_names = np.unique(nodes.get(properties="morphology"))
            L.info(
                f"> {len(morph_names)} unique morphologies in population '{npop}' \
                    ({nodes.size})"
            )

            h5_container = nodes.morph._get_morphology_base(  # noqa: SLF001
                "h5"
            )  # TODO: Should not use private function!!
            if Path(h5_container).suffix.lower() != ".h5":
                msg = "ERROR: .h5 morphology path is not a container!"
                raise ValueError(msg)
            h5_folder = Path(os.path.split(h5_container)[0]) / "h5"
            target_folder = (
                Path(os.path.split(h5_container)[0]) / self.config.initialize.output_format
            )

            h5_folder.mkdir(parents=True, exist_ok=True)
            target_folder.mkdir(parents=True, exist_ok=True)
        return nodes, morph_names, h5_container, h5_folder, target_folder

    @staticmethod
    def _check_morphologies(circuit_config: str, extension: str) -> bool:
        """Check modified circuit by loading some morphologies from each node population."""
        c = snap.Circuit(circuit_config)
        for npop in c.nodes.population_names:
            nodes = c.nodes[npop]
            if nodes.type == "biophysical":
                all_nids = nodes.ids()
                if len(all_nids) < N_NEURONS_FOR_CHECK:
                    nid_list = all_nids  # Check all node IDs
                    L.info(f"Checking all morphologies in population '{npop}'")
                else:
                    nid_list = all_nids[[0, -1]]  # Check first/last node ID only
                    L.info(f"Checking first/last morphologies in population '{npop}'")
                for nid in nid_list:
                    try:
                        _ = nodes.morph.get(
                            nid, transform=True, extension=extension
                        )  # Will throw an error if not accessible
                    except (MorphioError, ValueError):
                        return False  # Error
        return True  # All successful

    def _extract_from_h5_container(
        self,
        h5_container: str,
        morph_names: list,
        h5_folder: Path,
        target_folder: Path,
        morph_containers_to_delete: list,
        morph_folders_to_delete: list,
    ) -> None:
        with h5py.File(h5_container, "r") as f_container:
            skip_counter = 0
            for _m in tqdm.tqdm(morph_names, desc="Extracting/converting from .h5 container"):
                h5_file = Path(h5_folder) / (_m + ".h5")
                if Path(h5_file).exists():
                    skip_counter += 1
                else:
                    # Create individual .h5 morphology file
                    with h5py.File(h5_file, "w") as f_h5:
                        # Copy all groups/datasets into root of the file
                        for _key in f_container[_m]:
                            f_container.copy(f_container[f"{_m}/{_key}"], f_h5)
                    # Convert to required output format
                    if self.config.initialize.output_format != "h5":
                        src_file = Path(h5_folder) / (_m + ".h5")
                        dest_file = Path(target_folder) / (
                            _m + f".{self.config.initialize.output_format}"
                        )
                        if not Path(dest_file).exists():
                            convert(src_file, dest_file)
        L.info(
            f"Extracted/converted {len(morph_names) - skip_counter} morphologies \
                from .h5 container ({skip_counter} already existed)"
        )
        if h5_container not in morph_containers_to_delete:
            morph_containers_to_delete.append(h5_container)
        if (
            self.config.initialize.output_format != "h5"
            and h5_folder not in morph_folders_to_delete
        ):
            morph_folders_to_delete.append(h5_folder)

    @staticmethod
    def _check_config(cfg_dict: dict) -> None:
        if "manifest" not in cfg_dict or "$BASE_DIR" not in cfg_dict["manifest"]:
            msg = "ERROR: $BASE_DIR not defined!"
            raise ValueError(msg)
        if cfg_dict["manifest"]["$BASE_DIR"] != "." and cfg_dict["manifest"]["$BASE_DIR"] != "./":
            msg = "ERROR: $BASE_DIR is not circuit root directory!"
            raise ValueError(msg)

    @staticmethod
    def _check_global_morph_entry(cfg_dict: dict) -> bool:
        if (
            "components" in cfg_dict
            and "alternate_morphologies" in cfg_dict["components"]
            and "h5v1" in cfg_dict["components"]["alternate_morphologies"]
            and len(cfg_dict["components"]["alternate_morphologies"]["h5v1"]) > 0
        ):
            global_morph_entry = True
        else:
            global_morph_entry = False
        return global_morph_entry

    def _set_global_morph_entry(self, cfg_dict: dict, rel_target_folder: Path) -> None:
        if self.config.initialize.output_format == "h5":
            cfg_dict["components"]["alternate_morphologies"] = {"h5v1": str(rel_target_folder)}
            if "morphologies_dir" in cfg_dict["components"]:
                cfg_dict["components"]["morphologies_dir"] = ""
        elif self.config.initialize.output_format == "asc":
            cfg_dict["components"]["alternate_morphologies"] = {
                "neurolucida-asc": str(rel_target_folder)
            }
            if "morphologies_dir" in cfg_dict["components"]:
                cfg_dict["components"]["morphologies_dir"] = ""
        else:
            cfg_dict["components"]["morphologies_dir"] = str(rel_target_folder)
            if "alternate_morphologies" in cfg_dict["components"]:
                cfg_dict["components"]["alternate_morphologies"] = {}

    def _set_population_morph_entry(
        self,
        nodes: snap.nodes.NodePopulation,
        cfg_dict: dict,
        h5_folder: Path,
        rel_target_folder: Path,
    ) -> None:
        for _ndict in cfg_dict["networks"]["nodes"]:
            if nodes.name in _ndict["populations"]:
                pop = _ndict["populations"][nodes.name]
                if self.config.initialize.output_format == "h5":
                    pop["alternate_morphologies"] = {"h5v1": str(h5_folder)}
                    if "morphologies_dir" in pop:
                        pop["morphologies_dir"] = ""
                elif self.config.initialize.output_format == "asc":
                    pop["alternate_morphologies"] = {"neurolucida-asc": str(rel_target_folder)}
                    if "morphologies_dir" in pop:
                        pop["morphologies_dir"] = ""
                else:
                    pop["morphologies_dir"] = str(rel_target_folder)
                    if "alternate_morphologies" in pop:
                        pop["alternate_morphologies"] = {}
                break

    def _set_morph_entry(
        self,
        circuit_config: str,
        target_folder: Path,
        nodes: snap.nodes.NodePopulation,
        *,
        global_morph_entry: bool,
        cfg_dict: dict,
        h5_folder: Path,
    ) -> bool:
        root_path = os.path.split(circuit_config)[0]
        rel_target_folder = Path("$BASE_DIR") / os.path.relpath(target_folder, root_path)

        if global_morph_entry is None:
            global_morph_entry = MorphologyDecontainerizationTask._check_global_morph_entry(
                cfg_dict
            )

            if global_morph_entry:  # Set morphology path globally
                self._set_global_morph_entry(cfg_dict, rel_target_folder)

        if not global_morph_entry:  # Set individually per population
            self._set_population_morph_entry(nodes, cfg_dict, h5_folder, rel_target_folder)

        return global_morph_entry

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
    ) -> None:
        L.info(f"Running morphology decontainerization for '{self.config.initialize.circuit}'")

        # Set logging level to WARNING to prevent large debug output from morph_tool.convert()
        logging.getLogger("morph_tool").setLevel(logging.WARNING)

        # Copy contents of original circuit folder to output_root
        circuit_config = self._copy_circuit_folder()

        # Load circuit at new location
        c = snap.Circuit(circuit_config)
        node_populations = c.nodes.population_names

        # Iterate over node populations to find all morphologies
        # and extract them from the .h5 container
        morph_folders_to_delete = []
        morph_containers_to_delete = []
        global_morph_entry = None
        for npop in node_populations:
            nodes, morph_names, h5_container, h5_folder, target_folder = self._load_node_population(
                c, npop
            )
            if morph_names is None:
                continue

            # Extract from .h5 container
            self._extract_from_h5_container(
                h5_container,
                morph_names,
                h5_folder,
                target_folder,
                morph_containers_to_delete,
                morph_folders_to_delete,
            )

            # Update the circuit config so that it points to the individual morphology folder,
            # keeping the original global/local config file structure as similar as it was
            # before (but removing all other references to the original morphology folders)

            # Save original config file
            # cname, cext = os.path.splitext(circuit_config)  # noqa: ERA001
            # shutil.copy(circuit_config, cname + "__BAK__" + cext) # noqa: ERA001

            with Path(circuit_config).open(encoding="utf-8") as f:
                cfg_dict = json.load(f)

            self._check_config(cfg_dict)

            # Check & set if there is a global entry for morphologies (initially not set)
            global_morph_entry = self._set_morph_entry(
                circuit_config,
                target_folder,
                nodes,
                global_morph_entry=global_morph_entry,
                cfg_dict=cfg_dict,
                h5_folder=h5_folder,
            )

            with Path(circuit_config).open("w", encoding="utf-8") as f:
                json.dump(cfg_dict, f, indent=2)

        # Clean up morphology folders with individual morphologies
        L.info(f"Cleaning morphology container(s): {morph_containers_to_delete}")
        for _file in morph_containers_to_delete:
            Path(_file).unlink()
        L.info(f"Cleaning morphology folder(s): {morph_folders_to_delete}")
        for _folder in morph_folders_to_delete:
            shutil.rmtree(_folder)

        # Reload and check morphologies in modified circuit
        if not self._check_morphologies(circuit_config, self.config.initialize.output_format):
            msg = "ERROR: Morphology check not successful!"
            raise ValueError(msg)
        L.info("Morphology decontainerization DONE")
