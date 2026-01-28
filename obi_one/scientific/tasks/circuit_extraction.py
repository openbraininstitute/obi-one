import json
import logging
import os
import shutil
import tempfile
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

import bluepysnap as snap
import bluepysnap.circuit_validation
import h5py
import numpy as np
import tqdm
from bluepysnap import BluepySnapError
from brainbuilder.utils.sonata import split_population
from entitysdk import Client, models, types
from pydantic import Field, PrivateAttr

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import (
    _COORDINATE_CONFIG_FILENAME,
    _MAX_SMALL_MICROCIRCUIT_SIZE,
    _NEURON_PAIR_SIZE,
    _SCAN_CONFIG_FILENAME,
)
from obi_one.scientific.library.sonata_circuit_helpers import add_node_set_to_circuit
from obi_one.scientific.tasks.generate_simulation_configs import CircuitDiscriminator
from obi_one.scientific.unions.unions_neuron_sets import CircuitExtractionNeuronSetUnion

L = logging.getLogger(__name__)
_RUN_VALIDATION = False


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    EXTRACTION_TARGET = "Extraction Target"


class CircuitExtractionScanConfig(ScanConfig):
    """ScanConfig for extracting sub-circuits from larger circuits."""

    single_coord_class_name: ClassVar[str] = "CircuitExtractionSingleConfig"
    name: ClassVar[str] = "Circuit Extraction"
    description: ClassVar[str] = (
        "Extracts a sub-circuit from a SONATA circuit as defined by a neuron set. The output"
        " circuit will contain all morphologies, hoc files, and mod files that are required"
        " to simulate the extracted circuit."
    )

    _campaign: models.CircuitExtractionCampaign = None

    class Config:
        json_schema_extra: ClassVar[dict] = {
            "ui_enabled": True,
            "group_order": [
                BlockGroup.SETUP,
                BlockGroup.EXTRACTION_TARGET,
            ],
        }

    class Initialize(Block):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
            ui_element="model_identifier",
            title="Circuit",
            description="Parent circuit to extract a sub-circuit from.",
        )
        do_virtual: bool = Field(
            ui_element="boolean_input",
            default=True,
            title="Include Virtual Populations",
            description="Include virtual neurons which target the cells contained in the specified"
            " neuron set (together with their connectivity onto the specified neuron set) in the"
            " extracted sub-circuit.",
        )
        create_external: bool = Field(
            ui_element="boolean_input",
            default=True,
            title="Create External Population",
            description="Convert (non-virtual) neurons which are outside of the specified neuron"
            " set, but which target the cells contained therein, into a new external population"
            " of virtual neurons (together with their connectivity onto the specified neuron set).",
        )

    info: Info = Field(
        ui_element="block_single",
        title="Info",
        description="Information about the circuit extraction campaign.",
        group=BlockGroup.SETUP,
        group_order=0,
    )
    initialize: Initialize = Field(
        ui_element="block_single",
        title="Initialization",
        description="Parameters for initializing the circuit extraction campaign.",
        group=BlockGroup.SETUP,
        group_order=1,
    )
    neuron_set: CircuitExtractionNeuronSetUnion = Field(
        ui_element="block_union",
        title="Neuron Set",
        description="Set of neurons to be extracted from the parent circuit, including their"
        " connectivity.",
        group=BlockGroup.EXTRACTION_TARGET,
        group_order=0,
    )

    def create_campaign_entity_with_config(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: Client = None,
    ) -> models.CircuitExtractionCampaign:
        """Initializes the circuit extraction campaign in the database."""
        L.info("1. Initializing circuit extraction campaign in the database...")
        if multiple_value_parameters_dictionary is None:
            multiple_value_parameters_dictionary = {}

        L.info("-- Register CircuitExtractionCampaign Entity")
        self._campaign = db_client.register_entity(
            models.CircuitExtractionCampaign(
                name=self.info.campaign_name,
                description=self.info.campaign_description,
                scan_parameters=multiple_value_parameters_dictionary,
            )
        )

        L.info("-- Upload campaign_generation_config")
        _ = db_client.upload_file(
            entity_id=self._campaign.id,
            entity_type=models.CircuitExtractionCampaign,
            file_path=output_root / _SCAN_CONFIG_FILENAME,
            file_content_type="application/json",
            asset_label="campaign_generation_config",
        )

        return self._campaign

    def create_campaign_generation_entity(
        self, circuit_extraction_configs: list[models.CircuitExtractionConfig], db_client: Client
    ) -> None:
        L.info("3. Saving completed circuit extraction campaign generation")

        L.info("-- Register CircuitExtractionConfigGeneration Entity")
        db_client.register_entity(
            models.CircuitExtractionConfigGeneration(
                start_time=datetime.now(UTC),
                used=[self._campaign],
                generated=circuit_extraction_configs,
            )
        )


class CircuitExtractionSingleConfig(CircuitExtractionScanConfig, SingleConfigMixin):
    """Extracts a sub-circuit of a SONATA circuit as defined by a node set.

    The output circuit will contain all morphologies, hoc files, and mod files
    that are required to simulate the extracted circuit.
    """

    _single_entity: models.CircuitExtractionConfig = None

    @property
    def single_entity(self) -> models.CircuitExtractionConfig:
        return self._single_entity

    def set_single_entity(self, entity: models.CircuitExtractionConfig) -> None:
        """Sets the single entity attribute to the given entity."""
        self._single_entity = entity

    def create_single_entity_with_config(
        self,
        campaign: models.CircuitExtractionCampaign,  # noqa: ARG002
        db_client: Client,
    ) -> models.CircuitExtractionConfig:
        """Saves the circuit extraction config to the database."""
        L.info(f"2.{self.idx} Saving circuit extraction {self.idx} to database...")

        if not isinstance(self.initialize.circuit, CircuitFromID):
            msg = "Circuit extraction can only be saved to entitycore if circuit is CircuitFromID"
            raise OBIONEError(msg)

        L.info("-- Register CircuitExtractionConfig Entity")
        self._single_entity = db_client.register_entity(
            models.CircuitExtractionConfig(
                name=f"Circuit extraction {self.idx}",
                description=f"Circuit extraction {self.idx}",
                scan_parameters=self.single_coordinate_scan_params.dictionary_representaiton(),
                circuit_id=self.initialize.circuit.id_str,
            )
        )

        L.info("-- Upload circuit_extraction_config")
        _ = db_client.upload_file(
            entity_id=self.single_entity.id,
            entity_type=models.CircuitExtractionConfig,
            file_path=Path(self.coordinate_output_root, _COORDINATE_CONFIG_FILENAME),
            file_content_type="application/json",
            asset_label="circuit_extraction_config",
        )

        return self._single_entity


class CircuitExtractionTask(Task):
    config: CircuitExtractionSingleConfig
    _circuit: Circuit | None = PrivateAttr(default=None)
    _circuit_entity: models.Circuit | None = PrivateAttr(default=None)
    _temp_dir: tempfile.TemporaryDirectory | None = PrivateAttr(default=None)

    def __del__(self) -> None:
        """Destructor for automatic clean-up (if something goes wrong)."""
        self._cleanup_temp_dir()

    def _create_temp_dir(self) -> Path:
        """Creation of a new temporary directory."""
        self._cleanup_temp_dir()  # In case it exists already
        self._temp_dir = tempfile.TemporaryDirectory()
        return Path(self._temp_dir.name).resolve()

    def _cleanup_temp_dir(self) -> None:
        """Clean-up of temporary directory, if any."""
        if self._temp_dir is not None:
            self._temp_dir.cleanup()
            self._temp_dir = None

    def _resolve_circuit(self, *, db_client: Client, entity_cache: bool) -> None:
        """Set circuit variable based on the type of initialize.circuit."""
        if isinstance(self.config.initialize.circuit, Circuit):
            L.info("initialize.circuit is a Circuit instance.")
            self._circuit = self.config.initialize.circuit

        elif isinstance(self.config.initialize.circuit, CircuitFromID):
            L.info("initialize.circuit is a CircuitFromID instance.")
            circuit_id = self.config.initialize.circuit.id_str

            if entity_cache:
                # Use a cache directory at the campaign root --> Won't be deleted after extraction!
                L.info("Use entity cache")
                circuit_dest_dir = (
                    self.config.scan_output_root / "entity_cache" / "sonata_circuit" / circuit_id
                )
            else:
                # Stage circuit in a temporary directory --> Will be deleted after extraction!
                circuit_dest_dir = self._create_temp_dir() / "sonata_circuit"

            self._circuit = self.config.initialize.circuit.stage_circuit(
                db_client=db_client, dest_dir=circuit_dest_dir, entity_cache=entity_cache
            )
            self._circuit_entity = self.config.initialize.circuit.entity(db_client=db_client)

        if self._circuit is None:
            msg = "Failed to resolve circuit!"
            raise OBIONEError(msg)

    @staticmethod
    def get_circuit_size(c: Circuit) -> (str, int, int, int):
        c_sonata = c.sonata_circuit
        num_nrn = c_sonata.nodes[c.default_population_name].size
        if num_nrn == 1:
            scale = types.CircuitScale.single
        elif num_nrn == _NEURON_PAIR_SIZE:
            scale = types.CircuitScale.pair
        elif num_nrn <= _MAX_SMALL_MICROCIRCUIT_SIZE:
            scale = types.CircuitScale.small
        else:
            scale = types.CircuitScale.microcircuit
        # TODO: Add support for other scales as well
        # https://github.com/openbraininstitute/obi-one/issues/463

        if scale == types.CircuitScale.single:
            # Special case: Include extrinsic synapses & connections
            edge_pops = Circuit.get_edge_population_names(c_sonata, incl_virtual=True)
            edge_pops = [
                e for e in edge_pops if c_sonata.edges[e].target.name == c.default_population_name
            ]
        else:
            # Default case: Only include intrinsic synapse & connections
            edge_pops = [c.default_edge_population_name]

        num_syn = np.sum([c_sonata.edges[e].size for e in edge_pops]).astype(int)
        num_conn = np.sum(
            [
                len(
                    list(
                        c_sonata.edges[e].iter_connections(
                            target={"population": c_sonata.edges[e].target.name}
                        )
                    )
                )
                for e in edge_pops
            ]
        ).astype(int)

        return scale, num_nrn, num_syn, num_conn

    def _create_circuit_entity(self, db_client: Client, circuit_path: Path) -> models.Circuit:
        """Register a new Circuit entity of the extracted SONATA circuit (w/o assets)."""
        parent = self._circuit_entity  # Parent circuit entity

        # Define metadata for extracted circuit entity
        campaign_str = self.config.info.campaign_name.replace(" ", "-")
        circuit_name = f"{parent.name}__{campaign_str}"
        params = self.config.single_coordinate_scan_params.scan_params
        instance_info = [
            f"{p.location_str}={
                f'{p.value.entity(db_client).name}[{p.value.id_str}]'
                if isinstance(p.value, CircuitFromID)
                else p.value
            }"
            for p in params
        ]
        instance_info = ", ".join(instance_info)
        if len(params) > 0:
            circuit_name = f"{circuit_name}-{self.config.idx}"
            instance_info = f" - Instance {self.config.idx} with {instance_info}"
        circuit_descr = self.config.info.campaign_description + instance_info

        # Get counts
        c = Circuit(name=circuit_name, path=str(circuit_path))
        scale, num_nrn, num_syn, num_conn = CircuitExtractionTask.get_circuit_size(c)

        # Create circuit model
        circuit_model = models.Circuit(
            name=circuit_name,
            description=circuit_descr,
            subject=parent.subject,
            brain_region=parent.brain_region,
            license=parent.license,
            number_neurons=num_nrn,
            number_synapses=num_syn,
            number_connections=num_conn,
            has_morphologies=parent.has_morphologies,
            has_point_neurons=parent.has_point_neurons,
            has_electrical_cell_models=parent.has_electrical_cell_models,
            has_spines=parent.has_spines,
            scale=scale,
            build_category=parent.build_category,
            root_circuit_id=parent.root_circuit_id,
            atlas_id=parent.atlas_id,
            contact_email=parent.contact_email,
            published_in=parent.published_in,
            experiment_date=parent.experiment_date,
            authorized_public=False,
        )
        registered_circuit = db_client.register_entity(circuit_model)
        L.info(f"Circuit '{registered_circuit.name}' registered under ID {registered_circuit.id}")
        return registered_circuit

    @staticmethod
    def _add_circuit_folder_asset(
        db_client: Client, circuit_path: Path, registered_circuit: models.Circuit
    ) -> models.Asset:
        """Upload a circuit folder directory asset to a registered circuit entity."""
        asset_label = "sonata_circuit"
        circuit_folder = circuit_path.parent
        if not circuit_folder.is_dir():
            msg = "Circuit folder does not exist!"
            raise OBIONEError(msg)

        # Collect circuit files
        circuit_files = {
            str(path.relative_to(circuit_folder)): path
            for path in circuit_folder.rglob("*")
            if path.is_file()
        }
        L.info(f"{len(circuit_files)} files in '{circuit_folder}'")
        if "circuit_config.json" not in circuit_files:
            msg = "Circuit config file not found in circuit folder!"
            raise OBIONEError(msg)
        if "node_sets.json" not in circuit_files:
            msg = "Node sets file not found in circuit folder!"
            raise OBIONEError(msg)

        # Upload asset
        directory_asset = db_client.upload_directory(
            label=asset_label,
            name=asset_label,
            entity_id=registered_circuit.id,
            entity_type=models.Circuit,
            paths=circuit_files,
        )
        L.info(f"'{asset_label}' asset uploaded under asset ID {directory_asset.id}")
        return directory_asset

    def _add_derivation_link(
        self, db_client: Client, registered_circuit: models.Circuit
    ) -> models.Derivation:
        """Add a derivation link to the parent circuit."""
        parent = self._circuit_entity  # Parent circuit entity
        derivation_type = types.DerivationType.circuit_extraction
        derivation_model = models.Derivation(
            used=parent,
            generated=registered_circuit,
            derivation_type=derivation_type,
        )
        registered_derivation = db_client.register_entity(derivation_model)
        L.info(f"Derivation link '{derivation_type}' registered")
        return registered_derivation

    def _add_contributions(self, db_client: Client, registered_circuit: models.Circuit) -> list:
        """Add circuit contributions (from the parent circuit)."""
        # Get parent contributions
        parent = self._circuit_entity  # Parent circuit entity
        parent_contributions = db_client.search_entity(
            entity_type=models.Contribution, query={"entity__id": parent.id}
        ).all()

        # Register same contributions for extracted circuit
        contributions_list = []
        for contr in parent_contributions:
            contr_model = models.Contribution(
                agent=contr.agent, role=contr.role, entity=registered_circuit
            )
            registered_contr = db_client.register_entity(contr_model)
            contributions_list.append(registered_contr)
        # TODO: Additional contributors to be added by the user?
        L.info(f"{len(contributions_list)} contributions registered")
        return contributions_list

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
                #       the container
                # https://github.com/openbraininstitute/obi-one/issues/387

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

    @staticmethod
    def _get_execution_activity(
        db_client: Client = None,
        execution_activity_id: str | None = None,
    ) -> models.CircuitExtractionExecution | None:
        """Returns the CircuitExtractionExecution activity.

        Such activity is expected to be created and managed externally.
        """
        if db_client and execution_activity_id:
            execution_activity = db_client.get_entity(
                entity_type=models.CircuitExtractionExecution, entity_id=execution_activity_id
            )
        else:
            execution_activity = None
        return execution_activity

    @staticmethod
    def _update_execution_activity(
        db_client: Client = None,
        execution_activity: models.CircuitExtractionExecution | None = None,
        circuit_id: str | None = None,
    ) -> models.CircuitExtractionExecution | None:
        """Updates a CircuitExtractionExecution activity after task completion.

        Registers only the generated circuit ID. Other updates (status,
        end time, executor, etc) are expected to be managed externally.
        """
        if db_client and execution_activity and circuit_id:
            upd_dict = {"generated_ids": [circuit_id]}
            upd_entity = db_client.update_entity(
                entity_id=execution_activity.id,
                entity_type=models.CircuitExtractionExecution,
                attrs_or_entity=upd_dict,
            )
            L.info("CircuitExtractionExecution activity UPDATED")
        else:
            upd_entity = None
        return upd_entity

    def execute(
        self,
        *,
        db_client: Client = None,
        entity_cache: bool = False,
        execution_activity_id: str | None = None,
    ) -> str | None:  # Returns the ID of the extracted circuit
        # Get execution activity (expected to be created and managed externally)
        execution_activity = CircuitExtractionTask._get_execution_activity(
            db_client=db_client, execution_activity_id=execution_activity_id
        )

        # Resolve parent circuit (local path or staging from ID)
        self._resolve_circuit(db_client=db_client, entity_cache=entity_cache)

        # Add neuron set to SONATA circuit object
        # (will raise an error in case already existing)
        nset_name = self.config.neuron_set.__class__.__name__
        nset_def = self.config.neuron_set.get_node_set_definition(
            self._circuit, self._circuit.default_population_name
        )
        sonata_circuit = self._circuit.sonata_circuit
        add_node_set_to_circuit(sonata_circuit, {nset_name: nset_def}, overwrite_if_exists=False)

        # Create subcircuit using "brainbuilder"
        L.info(f"Extracting subcircuit from '{self._circuit.name}'")
        split_population.split_subcircuit(
            self.config.coordinate_output_root,
            nset_name,
            sonata_circuit,
            self.config.initialize.do_virtual,
            self.config.initialize.create_external,
        )

        # Custom edit of the circuit config so that all paths are relative to the new base directory
        # (in case there were absolute paths in the original config)

        old_base = os.path.split(self._circuit.path)[0]

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
        original_circuit = self._circuit.sonata_circuit
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
        self._copy_mod_files(self._circuit.path, self.config.coordinate_output_root, "mod")

        # Run circuit validation
        if _RUN_VALIDATION:
            self._run_validation(new_circuit_path)

        L.info("Extraction DONE")

        # Register new circuit entity incl. assets and linked entities
        new_circuit_id = None
        if db_client and self._circuit_entity:
            new_circuit_entity = self._create_circuit_entity(
                db_client=db_client, circuit_path=new_circuit_path
            )
            new_circuit_id = str(new_circuit_entity.id)

            # Register circuit folder asset
            self._add_circuit_folder_asset(
                db_client=db_client,
                circuit_path=new_circuit_path,
                registered_circuit=new_circuit_entity,
            )

            # TODO: Register compressed circuit asset
            # https://github.com/openbraininstitute/obi-one/issues/462
            # --> Requires running circuit compression
            # self._add_compressed_circuit_asset(db_client=db_client, circuit_path=new_circuit_path,
            # registered_circuit=new_circuit_entity)

            # TODO: Connectivity matrix folder asset
            # https://github.com/openbraininstitute/obi-one/issues/441
            # --> Requires running matrix extraction
            # self._add_matrix_folder_asset(db_client=db_client, circuit_path=new_circuit_path,
            # registered_circuit=new_circuit_entity)

            # TODO: Circuit figures for detailed explore page
            # https://github.com/openbraininstitute/obi-one/issues/442
            # --> Requires generating a new overview figure
            # --> Requires running circuit analysis & plotting
            # self._add_circuit_fig_assets(db_client=db_client, circuit_path=new_circuit_path,
            # registered_circuit=new_circuit_entity)

            # TODO: Circuit figure for campaign designer UI
            # https://github.com/openbraininstitute/obi-one/issues/442
            # --> Requires generating a new campaign designer figure
            # self._add_sim_designer_fig_asset(db_client=db_client, circuit_path=new_circuit_path,
            # registered_circuit=new_circuit_entity)

            # Derivation link
            self._add_derivation_link(db_client=db_client, registered_circuit=new_circuit_entity)

            # TODO: Contribution links
            # --> Contributors to be still defined (don't copy parent circuit's ones)
            # self._add_contributions(db_client=db_client,
            # registered_circuit=new_circuit_entity)

            # Update execution activity (if any)
            self._update_execution_activity(
                db_client=db_client,
                execution_activity=execution_activity,
                circuit_id=new_circuit_id,
            )

            L.info("Registration DONE")

        # Clean-up
        self._cleanup_temp_dir()

        return new_circuit_id
