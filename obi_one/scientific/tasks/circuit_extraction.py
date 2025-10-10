import json
import logging
import os
import shutil
from pathlib import Path
from typing import ClassVar

import bluepysnap as snap
import bluepysnap.circuit_validation
import entitysdk.client
import h5py
import tqdm
from bluepysnap import BluepySnapError
from brainbuilder.utils.sonata import split_population
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.sonata_circuit_helpers import add_node_set_to_circuit
from obi_one.scientific.unions.unions_neuron_sets import NeuronSetUnion

L = logging.getLogger(__name__)


class CircuitExtractionScanConfig(ScanConfig):
    """ScanConfig for extracting sub-circuits from larger circuits."""

    single_coord_class_name: ClassVar[str] = "CircuitExtractionSingleConfig"
    name: ClassVar[str] = "Circuit Extraction"
    description: ClassVar[str] = (
        "Extracts a sub-circuit of a SONATA circuit as defined by a node set. The output"
        " circuit will contain all morphologies, hoc files, and mod files that are required"
        " to simulate the extracted circuit."
    )

    class Initialize(Block):
        circuit: Circuit | list[Circuit]
        run_validation: bool = False
        do_virtual: bool | list[bool] = Field(
            default=True,
            name="Do virtual",
            description="Enable virtual neurons that target the cells contained in the"
            " specified neuron set to be split out and kept as virtual neurons together"
            " with their connectivity.",
        )
        create_external: bool | list[bool] = Field(
            default=True,
            name="Create external",
            description="Enable external neurons that are outside the specified neuron set"
            " but target the cells contained therein to be turned into new virtual neurons"
            " together with their connectivity.",
        )

        virtual_sources_to_ignore: tuple[str, ...] | list[tuple[str, ...]] = ()

    initialize: Initialize
    neuron_set: NeuronSetUnion


class CircuitExtractionSingleConfig(CircuitExtractionScanConfig, SingleConfigMixin):
    """Extracts a sub-circuit of a SONATA circuit as defined by a node set.

    The output circuit will contain all morphologies, hoc files, and mod files
    that are required to simulate the extracted circuit.
    """


class CircuitExtractionTask(Task):
    config: CircuitExtractionSingleConfig

    @staticmethod
    def _filter_ext(file_list: list, ext: str) -> list:
        return list(filter(lambda f: Path(f).suffix.lower() == f".{ext}", file_list))

    @classmethod
    def _rebase_config(cls, config_dict: dict, old_base: str, new_base: str) -> None:
        old_base = str(Path(old_base).resolve())
        for key, value in config_dict.items():
            if isinstance(value, str):
                if value == old_base:
                    config_dict[key] = ""
                else:
                    config_dict[key] = value.replace(old_base, new_base)
            elif isinstance(value, dict):
                cls._rebase_config(value, old_base, new_base)
            elif isinstance(value, list):
                for _v in value:
                    cls._rebase_config(_v, old_base, new_base)

    @staticmethod
    def _copy_mod_files(circuit_path: str, output_root: str, mod_folder: str) -> None:
        mod_folder = "mod"
        source_dir = Path(os.path.split(circuit_path)[0]) / mod_folder
        if Path(source_dir).exists():
            L.info("Copying mod files")
            dest_dir = Path(output_root) / mod_folder
            shutil.copytree(source_dir, dest_dir)

    @staticmethod
    def _run_validation(circuit_path: str) -> None:
        errors = snap.circuit_validation.validate(circuit_path, skip_slow=True)
        if len(errors) > 0:
            msg = f"Circuit validation error(s) found: {errors}"
            raise ValueError(msg)
        L.info("No validation errors found!")

    @classmethod
    def _get_morph_dirs(
        cls, pop_name: str, pop: snap.nodes.NodePopulation, original_circuit: snap.Circuit
    ) -> (dict, dict):
        src_morph_dirs = {}
        dest_morph_dirs = {}
        for _morph_ext in ["swc", "asc", "h5"]:
            try:
                morph_folder = original_circuit.nodes[pop_name].morph._get_morphology_base(  # noqa: SLF001
                    _morph_ext
                )
                # TODO: Should not use private function!! But required to get path
                #       even if h5 container.
            except BluepySnapError:
                # Morphology folder for given extension not defined in config
                continue

            if not Path(morph_folder).exists():
                # Morphology folder/container does not exist
                continue

            if (
                Path(morph_folder).is_dir()
                and len(cls._filter_ext(Path(morph_folder).iterdir(), _morph_ext)) == 0
            ):
                # Morphology folder does not contain morphologies
                continue

            dest_morph_dirs[_morph_ext] = pop.morph._get_morphology_base(_morph_ext)  # noqa: SLF001
            # TODO: Should not use private function!!
            src_morph_dirs[_morph_ext] = morph_folder
        return src_morph_dirs, dest_morph_dirs

    @classmethod
    def _copy_morphologies(
        cls, pop_name: str, pop: snap.nodes.NodePopulation, original_circuit: snap.Circuit
    ) -> None:
        L.info(f"Copying morphologies for population '{pop_name}' ({pop.size})")
        morphology_list = pop.get(properties="morphology").unique()

        src_morph_dirs, dest_morph_dirs = cls._get_morph_dirs(pop_name, pop, original_circuit)

        if len(src_morph_dirs) == 0:
            msg = "ERROR: No morphologies of any supported format found!"
            raise ValueError(msg)
        for _morph_ext, _src_dir in src_morph_dirs.items():
            if _morph_ext == "h5" and Path(_src_dir).is_file():
                # TODO: If there is only one neuron extracted, consider removing
                #       the container!!
                # Copy containerized morphologies into new container
                Path(os.path.split(dest_morph_dirs[_morph_ext])[0]).mkdir(
                    parents=True, exist_ok=True
                )
                src_container = _src_dir
                dest_container = dest_morph_dirs[_morph_ext]
                with (
                    h5py.File(src_container) as f_src,
                    h5py.File(dest_container, "a") as f_dest,
                ):
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
                L.info(
                    f"Copied {len(morphology_list) - skip_counter} morphologies into"
                    f" container ({skip_counter} already existed)"
                )
            else:
                # Copy morphology files
                Path(dest_morph_dirs[_morph_ext]).mkdir(parents=True, exist_ok=True)
                for morphology_name in tqdm.tqdm(
                    morphology_list, desc=f"Copying .{_morph_ext} morphologies"
                ):
                    src_file = Path(_src_dir) / f"{morphology_name}.{_morph_ext}"
                    dest_file = (
                        Path(dest_morph_dirs[_morph_ext]) / f"{morphology_name}.{_morph_ext}"
                    )
                    if not Path(src_file).exists():
                        msg = f"ERROR: Morphology '{src_file}' missing!"
                        raise ValueError(msg)
                    if not Path(dest_file).exists():
                        # Copy only, if not yet existing (could happen for shared
                        # morphologies among populations)
                        shutil.copyfile(src_file, dest_file)

    @staticmethod
    def _copy_hoc_files(
        pop_name: str, pop: snap.nodes.NodePopulation, original_circuit: snap.Circuit
    ) -> None:
        hoc_file_list = [
            _hoc.split(":")[-1] + ".hoc" for _hoc in pop.get(properties="model_template").unique()
        ]
        L.info(
            f"Copying {len(hoc_file_list)} biophysical neuron models (.hoc) for"
            f" population '{pop_name}' ({pop.size})"
        )

        source_dir = original_circuit.nodes[pop_name].config["biophysical_neuron_models_dir"]
        dest_dir = pop.config["biophysical_neuron_models_dir"]
        Path(dest_dir).mkdir(parents=True, exist_ok=True)

        for _hoc_file in hoc_file_list:
            src_file = Path(source_dir) / _hoc_file
            dest_file = Path(dest_dir) / _hoc_file
            if not Path(src_file).exists():
                msg = f"ERROR: HOC file '{src_file}' missing!"
                raise ValueError(msg)
            if not Path(dest_file).exists():
                # Copy only, if not yet existing (could happen for shared hoc files
                # among populations)
                shutil.copyfile(src_file, dest_file)

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
    ) -> str:
        # Add neuron set to SONATA circuit object
        # (will raise an error in case already existing)
        nset_name = self.config.neuron_set.__class__.__name__
        nset_def = self.config.neuron_set.get_node_set_definition(
            self.config.initialize.circuit, self.config.initialize.circuit.default_population_name
        )
        sonata_circuit = self.config.initialize.circuit.sonata_circuit
        add_node_set_to_circuit(sonata_circuit, {nset_name: nset_def}, overwrite_if_exists=False)

        # Create subcircuit using "brainbuilder"
        L.info(f"Extracting subcircuit from '{self.config.initialize.circuit.name}'")
        split_population.split_subcircuit(
            self.config.coordinate_output_root,
            nset_name,
            sonata_circuit,
            self.config.initialize.do_virtual,
            self.config.initialize.create_external,
            self.config.initialize.virtual_sources_to_ignore,
        )

        # Custom edit of the circuit config so that all paths are relative to the new base directory
        # (in case there were absolute paths in the original config)

        old_base = os.path.split(self.config.initialize.circuit.path)[0]

        # Quick fix to deal with symbolic links in base circuit (not usually required)
        # > alt_base = old_base  # Alternative old base
        # > for _sfix in ["-ER", "-DD", "-BIP", "-OFF", "-POS"]:
        # >     alt_base = alt_base.removesuffix(_sfix)

        new_base = "$BASE_DIR"
        new_circuit_path = Path(self.config.coordinate_output_root) / "circuit_config.json"

        # Create backup before modifying
        # > shutil.copyfile(new_circuit_path, os.path.splitext(new_circuit_path)[0] + ".BAK")

        with Path(new_circuit_path).open(encoding="utf-8") as config_file:
            config_dict = json.load(config_file)
        self._rebase_config(config_dict, old_base, new_base)

        # Quick fix to deal with symbolic links in base circuit
        # > if alt_base != old_base:
        # > self._rebase_config(config_dict, alt_base, new_base)

        with Path(new_circuit_path).open("w", encoding="utf-8") as config_file:
            json.dump(config_dict, config_file, indent=4)

        # Copy subcircuit morphologies and e-models (separately per node population)
        original_circuit = self.config.initialize.circuit.sonata_circuit
        new_circuit = snap.Circuit(new_circuit_path)
        for pop_name, pop in new_circuit.nodes.items():
            if pop.config["type"] == "biophysical":
                # Copying morphologies of any (supported) format
                if "morphology" in pop.property_names:
                    self._copy_morphologies(pop_name, pop, original_circuit)

                # Copy .hoc file directory (Even if defined globally, shows up under pop.config)
                if "biophysical_neuron_models_dir" in pop.config:
                    self._copy_hoc_files(pop_name, pop, original_circuit)

        # Copy .mod files, if any
        self._copy_mod_files(
            self.config.initialize.circuit.path, self.config.coordinate_output_root, "mod"
        )

        # Run circuit validation
        if self.config.initialize.run_validation:
            self._run_validation(new_circuit_path)

        L.info("Extraction DONE")

    def save(self) -> None:
        """Currently should return a created entity."""
