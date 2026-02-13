import json
import logging
import os
import shutil
import tempfile
from datetime import UTC, datetime
from enum import StrEnum
from importlib.resources import files
from pathlib import Path
from typing import ClassVar

import bluepysnap as snap
import bluepysnap.circuit_validation
import h5py
import numpy as np
from bluepysnap import BluepySnapError
from brainbuilder.utils.sonata import split_population
from conntility import ConnectivityMatrix
from entitysdk import Client, models, types
from PIL import Image
from pydantic import ConfigDict, Field, PrivateAttr

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.path import NamedPath
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

    model_config = ConfigDict(
        json_schema_extra={
            "ui_enabled": True,
            "group_order": [BlockGroup.SETUP, BlockGroup.EXTRACTION_TARGET],
        }
    )

    class Initialize(Block):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
            title="Circuit",
            description="Parent circuit to extract a sub-circuit from.",
            json_schema_extra={
                "ui_element": "model_identifier",
            },
        )
        do_virtual: bool = Field(
            default=True,
            title="Include Virtual Populations",
            description="Include virtual neurons which target the cells contained in the specified"
            " neuron set (together with their connectivity onto the specified neuron set) in the"
            " extracted sub-circuit.",
            json_schema_extra={
                "ui_element": "boolean_input",
            },
        )
        create_external: bool = Field(
            default=True,
            title="Create External Population",
            description="Convert (non-virtual) neurons which are outside of the specified neuron"
            " set, but which target the cells contained therein, into a new external population"
            " of virtual neurons (together with their connectivity onto the specified neuron set).",
            json_schema_extra={
                "ui_element": "boolean_input",
            },
        )

    info: Info = Field(
        title="Info",
        description="Information about the circuit extraction campaign.",
        json_schema_extra={
            "ui_element": "block_single",
            "group": BlockGroup.SETUP,
            "group_order": 0,
        },
    )
    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the circuit extraction campaign.",
        json_schema_extra={
            "ui_element": "block_single",
            "group": BlockGroup.SETUP,
            "group_order": 1,
        },
    )
    neuron_set: CircuitExtractionNeuronSetUnion = Field(
        title="Neuron Set",
        description="Set of neurons to be extracted from the parent circuit, including their"
        " connectivity.",
        json_schema_extra={
            "ui_element": "block_union",
            "group": BlockGroup.EXTRACTION_TARGET,
            "group_order": 0,
        },
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

    @staticmethod
    def _add_compressed_circuit_asset(
        db_client: Client, compressed_file: Path, registered_circuit: models.Circuit
    ) -> models.Asset:
        """Upload a compressed circuit file asset to a registered circuit entity."""
        asset_label = "compressed_sonata_circuit"

        if not compressed_file.exists():
            msg = f"Compressed circuit file '{compressed_file}' does not exist!"
            raise OBIONEError(msg)

        # Upload compressed file asset
        compressed_asset = db_client.upload_file(
            entity_id=registered_circuit.id,
            entity_type=models.Circuit,
            file_path=compressed_file,
            file_content_type="application/gzip",
            asset_label=asset_label,
        )
        L.info(f"'{asset_label}' asset uploaded under asset ID {compressed_asset.id}")
        return compressed_asset

    @staticmethod
    def _add_connectivity_matrix_asset(
        db_client: Client, matrix_dir: Path, registered_circuit: models.Circuit
    ) -> models.Asset:
        """Upload connectivity matrix directory asset to a registered circuit entity."""
        asset_label = "circuit_connectivity_matrices"

        if not matrix_dir.is_dir():
            msg = f"Connectivity matrix directory '{matrix_dir}' does not exist!"
            raise OBIONEError(msg)

        # Collect matrix files
        matrix_files = {
            str(path.relative_to(matrix_dir)): path
            for path in matrix_dir.rglob("*")
            if path.is_file()
        }
        L.info(f"{len(matrix_files)} files in '{matrix_dir}'")

        # Upload directory asset
        matrix_asset = db_client.upload_directory(
            label=asset_label,
            name=asset_label,
            entity_id=registered_circuit.id,
            entity_type=models.Circuit,
            paths=matrix_files,
        )
        L.info(f"'{asset_label}' asset uploaded under asset ID {matrix_asset.id}")
        return matrix_asset

    @staticmethod
    def convert_image_to_webp(
        image_path: Path, *, overwrite: bool = False, quality: int = 80, method: int = 6
    ) -> Path:
        """Converts an image file (e.g., .png) to .webp format."""
        if not image_path.exists():
            msg = f"Input file '{image_path}' does not exist!"
            raise OBIONEError(msg)
        output_path = image_path.with_suffix(".webp")
        if not overwrite and output_path.exists():
            msg = f"Output file '{output_path}' already exists!"
            raise OBIONEError(msg)
        with Image.open(image_path) as img:
            image = img.convert("RGBA")
            image.save(output_path, "webp", quality=quality, method=method)
        return output_path

    @staticmethod
    def _add_image_assets(
        db_client: Client, plot_dir: Path, plot_files: list, registered_circuit: models.Circuit
    ) -> list[models.Asset]:
        """Upload connectivity plot assets to a registered circuit entity.

        Note: Image files will be converted to .webp, if needed.
        """
        asset_label_map = {
            "node_stats": ("node_stats", "webp"),
            "small_adj_and_stats": ("network_stats_a", "webp"),
            "small_network_in_2D": ("network_stats_b", "webp"),
            "network_global_stats": ("network_stats_a", "webp"),
            "network_pathway_stats": ("network_stats_b", "webp"),
            "circuit_visualization": ("circuit_visualization", "webp"),
            "simulation_designer_image": ("simulation_designer_image", "png"),
        }
        if not plot_dir.is_dir():
            msg = f"Connectivity plots directory '{plot_dir}' does not exist!"
            raise OBIONEError(msg)

        # Upload image file assets (incl. conversion to .webp format if needed)
        plot_assets = []
        for file in plot_files:
            file_path = plot_dir / file
            if not file_path.is_file():
                msg = f"Connectivity plot '{file_path.name}' does not exist!"
                raise OBIONEError(msg)
            if file_path.stem not in asset_label_map:
                msg = f"No asset label for plot '{file_path.name}' - SKIPPING!"
                L.warning(msg)
                continue
            asset_label, fmt = asset_label_map[file_path.stem]
            if fmt == "webp":
                file_path = CircuitExtractionTask.convert_image_to_webp(image_path=file_path)
            if "." + fmt != file_path.suffix:
                msg = f"File format mismatch '{file_path.name}' (.{fmt} required)!"
                raise OBIONEError(msg)
            plot_asset = db_client.upload_file(
                entity_id=registered_circuit.id,
                entity_type=models.Circuit,
                file_path=file_path,
                file_content_type=f"image/{fmt}",
                asset_label=asset_label,
            )
            L.info(f"'{asset_label}' asset uploaded under asset ID {plot_asset.id}")
            plot_assets.append(plot_asset)
        return plot_assets

    @staticmethod
    def _run_circuit_folder_compression(circuit_path: Path, circuit_name: str) -> Path:
        """Set up and run folder compression task."""
        # Import here to avoid circular import
        from obi_one.core.run_tasks import run_tasks_for_generated_scan  # noqa: PLC0415
        from obi_one.core.scan_generation import GridScanGenerationTask  # noqa: PLC0415
        from obi_one.scientific.tasks.folder_compression import (  # noqa: PLC0415
            FolderCompressionScanConfig,
        )

        # Set up circuit folder compression
        folder_path = NamedPath(
            name=circuit_path.parent.name + "__COMPRESSED__",  # Used as output name
            path=str(circuit_path.parent),
        )
        compression_init = FolderCompressionScanConfig.Initialize(
            folder_path=[folder_path],
            file_format="gz",
            file_name="circuit",
            archive_name=circuit_name,
        )
        folder_compressions_config = FolderCompressionScanConfig(initialize=compression_init)

        # Run circuit folder compression
        grid_scan = GridScanGenerationTask(
            form=folder_compressions_config,
            output_root=circuit_path.parents[1],
            coordinate_directory_option="VALUE",
        )
        grid_scan.execute()
        run_tasks_for_generated_scan(grid_scan)

        # Check and return output file
        output_file = (
            grid_scan.single_configs[0].coordinate_output_root
            / f"{compression_init.file_name}.{compression_init.file_format}"
        )
        if not output_file.exists():
            msg = "Compressed circuit file does not exist!"
            raise OBIONEError(msg)
        L.info(f"Circuit folder compressed into {output_file}")
        return output_file

    @staticmethod
    def _run_connectivity_matrix_extraction(circuit_path: Path) -> Path:
        """Set up and run connectivity matrix extraction task."""
        # Import here to avoid circular import
        from obi_one.core.run_tasks import run_tasks_for_generated_scan  # noqa: PLC0415
        from obi_one.core.scan_generation import GridScanGenerationTask  # noqa: PLC0415
        from obi_one.scientific.tasks.connectivity_matrix_extraction import (  # noqa: PLC0415
            ConnectivityMatrixExtractionScanConfig,
        )

        # Set up connectivity matrix extraction
        circuit = Circuit(
            name=circuit_path.parent.name + "__CONN_MATRIX__",  # Used as output name
            path=str(circuit_path),
        )
        edge_population = circuit.default_edge_population_name
        matrix_init = ConnectivityMatrixExtractionScanConfig.Initialize(
            circuit=[circuit],
            edge_population=edge_population,
            node_attributes=("synapse_class", "layer", "mtype", "etype", "x", "y", "z"),
            with_matrix_config=True,
        )
        matrix_extraction_config = ConnectivityMatrixExtractionScanConfig(initialize=matrix_init)

        # Run connectivity matrix extraction
        grid_scan = GridScanGenerationTask(
            form=matrix_extraction_config,
            output_root=circuit_path.parents[1],
            coordinate_directory_option="VALUE",
        )
        grid_scan.execute()
        run_tasks_for_generated_scan(grid_scan)

        # Check and return output directory
        output_dir = grid_scan.single_configs[0].coordinate_output_root
        output_file = output_dir / "matrix_config.json"
        if not output_file.exists():
            msg = "Connectivity matrix config file does not exist!"
            raise OBIONEError(msg)
        L.info(f"Connectivity matrix extracted to {output_dir}")
        return output_dir, output_file, edge_population

    @staticmethod
    def _run_basic_connectivity_plots(
        circuit_path: Path, matrix_config: Path, edge_population: str
    ) -> tuple[Path, list]:
        """Set up and run basic connectivity plotting task."""
        # Import here to avoid circular import
        from obi_one.core.run_tasks import run_tasks_for_generated_scan  # noqa: PLC0415
        from obi_one.core.scan_generation import GridScanGenerationTask  # noqa: PLC0415
        from obi_one.scientific.tasks.basic_connectivity_plots import (  # noqa: PLC0415
            BasicConnectivityPlotsScanConfig,
        )

        # Find the connectivity matrix file
        if not matrix_config.exists():
            msg = f"Connectivity matrix config file '{matrix_config}' not found!"
            raise OBIONEError(msg)
        with matrix_config.open(encoding="utf-8") as f:
            config_dict = json.load(f)
        edge_pop_config = config_dict.get(edge_population, {})
        matrix_file = matrix_config.parent / edge_pop_config.get("single", {}).get("path", "")
        if not matrix_file.is_file():
            msg = f"Connectivity matrix file '{matrix_file}' not found!"
            raise OBIONEError(msg)

        # Set up basic connectivity plots
        matrix_path = NamedPath(
            name=circuit_path.parent.name + "__BASIC_PLOTS__",  # Used as output name
            path=str(matrix_file),
        )
        cmat = ConnectivityMatrix.from_h5(matrix_path.path)
        if cmat.vertices.shape[0] <= _MAX_SMALL_MICROCIRCUIT_SIZE:
            plot_types = ("nodes", "small_adj_and_stats", "network_in_2D", "network_in_2D_circular", "property_table_extra")
        else:
            plot_types = ("nodes", "connectivity_global", "connectivity_pathway")
        plots_init = BasicConnectivityPlotsScanConfig.Initialize(
            matrix_path=[matrix_path],
            plot_formats=("png",),
            rendering_cmap="tab10",
            plot_types=plot_types,
        )
        plots_config = BasicConnectivityPlotsScanConfig(initialize=plots_init)

        # Run basic connectivity plots
        grid_scan = GridScanGenerationTask(
            form=plots_config,
            output_root=circuit_path.parents[1],
            coordinate_directory_option="VALUE",
        )
        grid_scan.execute()
        run_tasks_for_generated_scan(grid_scan)

        # Check and return output directory
        output_file_map = {
            "nodes": "node_stats.png",
            "small_adj_and_stats": "small_adj_and_stats.png",
            "network_in_2D": "small_network_in_2D.png",
            "network_in_2D_circular": "small_network_in_2D_circular.png",
            "property_table_extra": "property_table_extra.png",
            "connectivity_global": "network_global_stats.png",
            "connectivity_pathway": "network_pathway_stats.png",
        }
        output_dir = grid_scan.single_configs[0].coordinate_output_root
        output_files = [output_file_map[_pt] for _pt in plot_types]
        for file in output_files:
            if not (output_dir / file).is_file():
                msg = f"Connectivity plot '{file}' missing!"
                raise OBIONEError(msg)
        L.info(f"Basic connectivity plots generated in {output_dir}: {output_files}")
        return output_dir, output_files

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
                L.info(f"Copying {len(morphology_list)} containerized .{_morph_ext} morphologies")
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
                    for morphology_name in morphology_list:
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
                L.info(f"Copying {len(morphology_list)} .{_morph_ext} morphologies")
                Path(dest_morph_dirs[_morph_ext]).mkdir(parents=True, exist_ok=True)
                for morphology_name in morphology_list:
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

    @staticmethod
    def _generate_overview_figure(basic_plots_dir: Path | None, output_file: Path) -> Path:
        """Generates an overview figure of the extracted circuit."""
        # Use circular view from basic connectivity plots, if existing
        if basic_plots_dir:
            fig_paths = basic_plots_dir / "small_network_in_2D_circular.png"
            if fig_paths.is_file():
                # Add table path (optional)
                tab_path = basic_plots_dir / "property_table_extra.png"
                if tab_path.is_file():
                    fig_paths = (fig_paths, tab_path)
            else:
                fig_paths = None
        else:
            fig_paths = None

        # Use template figure from library if no circular plot available
        if fig_paths is None:
            fig_paths = Path(
                str(files("obi_one.scientific.library").joinpath("extracted_circuit_template.png"))
            )

        # Check that output file does not exist yet
        if output_file.exists():
            msg = f"Output file '{output_file}' already exists!"
            raise OBIONEError(msg)

        # Save output figure
        output_file.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(fig_paths, tuple):
            # Stack images horizontally
            img_L = Image.open(fig_paths[0])
            img_R = Image.open(fig_paths[-1])
            width = img_L.width + img_R.width
            height = max(img_L.height, img_R.height)
            img_merged = Image.new("RGB", (width, height), (255, 255, 255))
            img_merged.paste(img_L, (0, 0))
            img_merged.paste(img_R, (img_L.width, height - img_R.height >> 1))
            img_merged.save(output_file)
        else:
            # Check that output file has the correct extension
            if output_file.suffix != fig_paths.suffix:
                msg = (
                    f"Output file extension '{output_file.suffix}' does not match "
                    f"figure extension '{fig_paths.suffix}'!"
                )
                raise OBIONEError(msg)

            # Copy figure to output file
            shutil.copy(fig_paths, output_file)

        return output_file

    @staticmethod
    def _generate_additional_circuit_assets(  # noqa: C901
        db_client: Client,
        new_circuit_path: Path,
        new_circuit_entity: models.Circuit,
    ) -> None:
        """Generate and register additional circuit assets."""
        # Compressed circuit asset
        try:
            compressed_circuit = CircuitExtractionTask._run_circuit_folder_compression(
                circuit_path=new_circuit_path,
                circuit_name=new_circuit_entity.name if new_circuit_entity else None,
            )
        except Exception as e:  # noqa: BLE001
            # Catch any exception here and turn into warnings only
            L.warning(f"Circuit compression failed: {e}")
            compressed_circuit = None

        if db_client and new_circuit_entity and compressed_circuit:
            try:
                CircuitExtractionTask._add_compressed_circuit_asset(
                    db_client=db_client,
                    compressed_file=compressed_circuit,
                    registered_circuit=new_circuit_entity,
                )
            except Exception as e:  # noqa: BLE001
                # Catch any exception here and turn into warnings only
                L.warning(f"Compressed circuit registration failed: {e}")

        # Connectivity matrix asset
        try:
            (
                matrix_dir,
                matrix_config,
                edge_population,
            ) = CircuitExtractionTask._run_connectivity_matrix_extraction(
                circuit_path=new_circuit_path
            )
        except Exception as e:  # noqa: BLE001
            # Catch any exception here and turn into warnings only
            L.warning(f"Connectivity matrix extraction failed: {e}")
            matrix_dir = matrix_config = edge_population = None

        if db_client and new_circuit_entity and matrix_dir:
            try:
                CircuitExtractionTask._add_connectivity_matrix_asset(
                    db_client=db_client,
                    matrix_dir=matrix_dir,
                    registered_circuit=new_circuit_entity,
                )
            except Exception as e:  # noqa: BLE001
                # Catch any exception here and turn into warnings only
                L.warning(f"Connectivity matrix registration failed: {e}")

        # Connectivity plots asset
        try:
            plot_dir, plot_files = CircuitExtractionTask._run_basic_connectivity_plots(
                circuit_path=new_circuit_path,
                matrix_config=matrix_config,
                edge_population=edge_population,
            )
        except Exception as e:  # noqa: BLE001
            # Catch any exception here and turn into warnings only
            L.warning(f"Connectivity plots generation failed: {e}")
            plot_dir = plot_files = None

        if db_client and new_circuit_entity and plot_dir and plot_files:
            try:
                CircuitExtractionTask._add_image_assets(
                    db_client=db_client,
                    plot_dir=plot_dir,
                    plot_files=plot_files,
                    registered_circuit=new_circuit_entity,
                )
            except Exception as e:  # noqa: BLE001
                # Catch any exception here and turn into warnings only
                L.warning(f"Connectivity plots registration failed: {e}")

        # Overview & sim designer visualizations
        try:
            viz_dir = new_circuit_path.parent.with_name(
                new_circuit_path.parent.name + "__CIRCUIT_VIZ__"
            )
            viz_files = []
            viz_path = CircuitExtractionTask._generate_overview_figure(
                plot_dir, viz_dir / "circuit_visualization.png"
            )
            viz_files.append(viz_path.name)
            sim_viz_path = CircuitExtractionTask._generate_overview_figure(
                plot_dir, viz_dir / "simulation_designer_image.png"
            )
            viz_files.append(sim_viz_path.name)
        except Exception as e:  # noqa: BLE001
            # Catch any exception here and turn into warnings only
            L.warning(f"Circuit visualization generation failed: {e}")
            viz_dir = viz_files = None

        if db_client and new_circuit_entity and viz_dir and viz_files:
            try:
                CircuitExtractionTask._add_image_assets(
                    db_client=db_client,
                    plot_dir=viz_dir,
                    plot_files=viz_files,
                    registered_circuit=new_circuit_entity,
                )
            except Exception as e:  # noqa: BLE001
                # Catch any exception here and turn into warnings only
                L.warning(f"Circuit visualization registration failed: {e}")

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

        # Register new circuit entity incl. folder asset and linked entities
        new_circuit_entity = None
        if db_client and self._circuit_entity:
            new_circuit_entity = self._create_circuit_entity(
                db_client=db_client, circuit_path=new_circuit_path
            )

            # Register circuit folder asset
            self._add_circuit_folder_asset(
                db_client=db_client,
                circuit_path=new_circuit_path,
                registered_circuit=new_circuit_entity,
            )

            # Derivation link
            self._add_derivation_link(db_client=db_client, registered_circuit=new_circuit_entity)

            # Update execution activity (if any)
            self._update_execution_activity(
                db_client=db_client,
                execution_activity=execution_activity,
                circuit_id=str(new_circuit_entity.id),
            )

            L.info("Registration DONE")

        # Generate and register additional circuit asset
        self._generate_additional_circuit_assets(
            db_client=db_client,
            new_circuit_path=new_circuit_path,
            new_circuit_entity=new_circuit_entity,
        )

        # Clean-up
        self._cleanup_temp_dir()

        if new_circuit_entity:
            return str(new_circuit_entity.id)
        return None
