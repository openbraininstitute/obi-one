import json
import logging
import os
import shutil
import tempfile
from enum import StrEnum
from importlib.resources import files
from pathlib import Path
from typing import ClassVar

import bluepysnap as snap
import bluepysnap.circuit_validation
from brainbuilder.utils.sonata import split_population
from conntility import ConnectivityMatrix
from entitysdk import Client, models, types
from entitysdk.types import TaskActivityType, TaskConfigType
from PIL import Image
from pydantic import Field, PrivateAttr

from obi_one.config import settings
from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.path import NamedPath
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import (
    _MAX_SMALL_MICROCIRCUIT_SIZE,
)
from obi_one.scientific.library.entity_property_types import (
    MappedPropertiesGroup,
)
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig
from obi_one.scientific.library.sonata_circuit_helpers import add_node_set_to_circuit
from obi_one.scientific.tasks.basic_connectivity_plots import (
    BasicConnectivityPlotsScanConfig,
)
from obi_one.scientific.tasks.connectivity_matrix_extraction import (
    ConnectivityMatrixExtractionScanConfig,
)
from obi_one.scientific.tasks.folder_compression import (
    FolderCompressionScanConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.circuit import (
    CircuitDiscriminator,
)
from obi_one.scientific.unions.unions_neuron_sets_2 import NonVirtualNeuronSetUnion
from obi_one.utils import circuit as circuit_utils, db_sdk
from obi_one.utils.benchmark import BenchmarkTracker

if settings.circuit_extraction.benchmarking_enabled:
    BenchmarkTracker.enable()
else:
    BenchmarkTracker.disable()

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    EXTRACTION_TARGET = "Extraction Target"


class CircuitExtractionScanConfig(InfoScanConfig):
    """ScanConfig for extracting sub-circuits from larger circuits."""

    single_coord_class_name: ClassVar[str] = "CircuitExtractionSingleConfig"
    name: ClassVar[str] = "Circuit Extraction"
    description: ClassVar[str] = (
        "Extracts a sub-circuit from a SONATA circuit as defined by a neuron set. The output"
        " circuit will contain all morphologies, hoc files, and mod files that are required"
        " to simulate the extracted circuit."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP, BlockGroup.EXTRACTION_TARGET],
        SchemaKey.PROPERTY_ENDPOINTS: {
            MappedPropertiesGroup.CIRCUIT: "/mapped-circuit-properties/{circuit_id}",
        },
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = (
        TaskConfigType.circuit_extraction__campaign
    )
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.circuit_extraction__config_generation
    )

    def input_entities(self, db_client: Client) -> list[models.Entity]:
        input_entities = []
        if isinstance(self.initialize.circuit, CircuitFromID):
            input_entities.extend([self.initialize.circuit.entity(db_client=db_client)])
        elif isinstance(self.initialize.circuit, list):
            for circuit in self.initialize.circuit:
                if isinstance(circuit, CircuitFromID):
                    input_entities.extend([circuit.entity(db_client=db_client)])
        return input_entities

    class Initialize(Block):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
            title="Circuit",
            description="Parent circuit to extract a sub-circuit from.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER,
            },
        )
        do_virtual: bool = Field(
            default=True,
            title="Include Virtual Populations",
            description="Include virtual neurons which target the cells contained in the specified"
            " neuron set (together with their connectivity onto the specified neuron set) in the"
            " extracted sub-circuit.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
            },
        )
        create_external: bool = Field(
            default=True,
            title="Create External Population",
            description="Convert (non-virtual) neurons which are outside of the specified neuron"
            " set, but which target the cells contained therein, into a new external population"
            " of virtual neurons (together with their connectivity onto the specified neuron set).",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
            },
        )

    info: Info = Field(
        title="Info",
        description="Information about the circuit extraction campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the circuit extraction campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    neuron_set: NonVirtualNeuronSetUnion = Field(
        title="Neuron Set",
        description="Set of neurons to be extracted from the parent circuit, including their"
        " connectivity.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_UNION,
            SchemaKey.GROUP: BlockGroup.EXTRACTION_TARGET,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class CircuitExtractionSingleConfig(CircuitExtractionScanConfig, SingleConfigMixin):
    """Extracts a sub-circuit of a SONATA circuit as defined by a node set.

    The output circuit will contain all morphologies, hoc files, and mod files
    that are required to simulate the extracted circuit.
    """

    _single_task_config_type: ClassVar[TaskConfigType] = TaskConfigType.circuit_extraction__config
    _single_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.circuit_extraction__execution
    )


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
            self._circuit_entity = self.config.initialize.circuit.entity(db_client=db_client)  # ty:ignore[invalid-assignment]

        if self._circuit is None:
            msg = "Failed to resolve circuit!"
            raise OBIONEError(msg)

    def _create_circuit_entity(self, db_client: Client, circuit_path: Path) -> models.Circuit:
        """Register a new Circuit entity of the extracted SONATA circuit (w/o assets)."""
        parent = self._circuit_entity  # Parent circuit entity

        # Define metadata for extracted circuit entity
        campaign_str = self.config.info.campaign_name.replace(" ", "-")
        circuit_name = f"{parent.name}__{campaign_str}"  # ty:ignore[unresolved-attribute]
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
        scale, num_nrn, num_syn, num_conn = circuit_utils.get_circuit_size(c)

        # Create circuit model
        circuit_model = models.Circuit(
            name=circuit_name,
            description=circuit_descr,
            subject=parent.subject,  # ty:ignore[unresolved-attribute]
            brain_region=parent.brain_region,  # ty:ignore[unresolved-attribute]
            license=parent.license,  # ty:ignore[unresolved-attribute]
            number_neurons=num_nrn,
            number_synapses=num_syn,
            number_connections=num_conn,
            has_morphologies=parent.has_morphologies,  # ty:ignore[unresolved-attribute]
            has_point_neurons=parent.has_point_neurons,  # ty:ignore[unresolved-attribute]
            has_electrical_cell_models=parent.has_electrical_cell_models,  # ty:ignore[unresolved-attribute]
            has_spines=parent.has_spines,  # ty:ignore[unresolved-attribute]
            scale=scale,  # ty:ignore[invalid-argument-type]
            build_category=parent.build_category,  # ty:ignore[unresolved-attribute]
            root_circuit_id=parent.root_circuit_id or parent.id,  # ty:ignore[unresolved-attribute]
            atlas_id=parent.atlas_id,  # ty:ignore[unresolved-attribute]
            contact_email=parent.contact_email,  # ty:ignore[unresolved-attribute]
            published_in=parent.published_in,  # ty:ignore[unresolved-attribute]
            experiment_date=parent.experiment_date,  # ty:ignore[unresolved-attribute]
            authorized_public=False,
        )
        registered_circuit = db_client.register_entity(circuit_model)
        L.info(f"Circuit '{registered_circuit.name}' registered under ID {registered_circuit.id}")
        return registered_circuit

    def _add_derivation_link(
        self, db_client: Client, registered_circuit: models.Circuit
    ) -> models.Derivation:
        """Add a derivation link to the parent circuit."""
        parent = self._circuit_entity  # Parent circuit entity
        derivation_type = types.DerivationType.circuit_extraction
        derivation_model = models.Derivation(
            used=parent,  # ty:ignore[invalid-argument-type]
            generated=registered_circuit,
            derivation_type=derivation_type,
        )
        registered_derivation = db_client.register_entity(derivation_model)
        L.info(f"Derivation link '{derivation_type}' registered")
        return registered_derivation

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
            img_left = Image.open(fig_paths[0])
            img_right = Image.open(fig_paths[-1])
            width = img_left.width + img_right.width
            height = max(img_left.height, img_right.height)
            img_merged = Image.new("RGB", (width, height), (255, 255, 255))
            img_merged.paste(img_left, (0, 0))
            img_merged.paste(img_right, (img_left.width, height - img_right.height >> 1))
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
    def _run_circuit_folder_compression(circuit_path: Path, circuit_name: str) -> Path:
        """Set up and run folder compression task."""
        # Import here to avoid circular import
        from obi_one.core.run_tasks import run_tasks_for_generated_scan  # noqa: PLC0415
        from obi_one.core.scan_generation import GridScanGenerationTask  # noqa: PLC0415

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
    def _run_connectivity_matrix_extraction(circuit_path: Path) -> tuple[Path, Path, str]:
        """Set up and run connectivity matrix extraction task."""
        # Import here to avoid circular import
        from obi_one.core.run_tasks import run_tasks_for_generated_scan  # noqa: PLC0415
        from obi_one.core.scan_generation import GridScanGenerationTask  # noqa: PLC0415

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
            plot_types = (
                "nodes",
                "small_adj_and_stats",
                "network_in_2D",
                "network_in_2D_circular",
                "property_table_extra",
            )
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
        output_files = [output_file_map[pt] for pt in plot_types]
        for file in output_files:
            if not (output_dir / file).is_file():
                msg = f"Connectivity plot '{file}' missing!"
                raise OBIONEError(msg)
        L.info(f"Basic connectivity plots generated in {output_dir}: {output_files}")
        return output_dir, output_files

    @staticmethod
    def _generate_additional_circuit_assets(  # noqa: C901, PLR0915
        db_client: Client,
        new_circuit_path: Path,
        new_circuit_entity: models.Circuit,
    ) -> None:
        """Generate and register additional circuit assets."""
        # Compressed circuit asset
        try:
            with BenchmarkTracker.section("run_circuit_folder_compression"):
                compressed_circuit = CircuitExtractionTask._run_circuit_folder_compression(
                    circuit_path=new_circuit_path,
                    circuit_name=new_circuit_entity.name if new_circuit_entity else None,  # ty:ignore[invalid-argument-type]
                )
        except Exception as e:  # noqa: BLE001
            # Catch any exception here and turn into warnings only
            L.warning(f"Circuit compression failed: {e}")
            compressed_circuit = None

        if db_client and new_circuit_entity and compressed_circuit:
            try:
                with BenchmarkTracker.section("add_compressed_circuit_asset"):
                    db_sdk.add_compressed_circuit_asset(
                        client=db_client,
                        compressed_file=compressed_circuit,
                        registered_circuit=new_circuit_entity,
                    )
            except Exception as e:  # noqa: BLE001
                # Catch any exception here and turn into warnings only
                L.warning(f"Compressed circuit registration failed: {e}")

        # Connectivity matrix asset
        try:
            with BenchmarkTracker.section("run_connectivity_matrix_extraction"):
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
                with BenchmarkTracker.section("add_connectivity_matrix_asset"):
                    db_sdk.add_connectivity_matrix_asset(
                        client=db_client,
                        matrix_dir=matrix_dir,
                        registered_circuit=new_circuit_entity,
                    )
            except Exception as e:  # noqa: BLE001
                # Catch any exception here and turn into warnings only
                L.warning(f"Connectivity matrix registration failed: {e}")

        # Connectivity plots asset
        try:
            with BenchmarkTracker.section("run_basic_connectivity_plots"):
                plot_dir, plot_files = CircuitExtractionTask._run_basic_connectivity_plots(
                    circuit_path=new_circuit_path,
                    matrix_config=matrix_config,  # ty:ignore[invalid-argument-type]
                    edge_population=edge_population,  # ty:ignore[invalid-argument-type]
                )
        except Exception as e:  # noqa: BLE001
            # Catch any exception here and turn into warnings only
            L.warning(f"Connectivity plots generation failed: {e}")
            plot_dir = plot_files = None

        if db_client and new_circuit_entity and plot_dir and plot_files:
            try:
                with BenchmarkTracker.section("add_connectivity_plot_assets"):
                    db_sdk.add_image_assets(
                        client=db_client,
                        plot_dir=plot_dir,
                        plot_files=plot_files,
                        registered_circuit=new_circuit_entity,
                    )
            except Exception as e:  # noqa: BLE001
                # Catch any exception here and turn into warnings only
                L.warning(f"Connectivity plots registration failed: {e}")

        # Overview & sim designer visualizations
        try:
            with BenchmarkTracker.section("generate_overview_figures"):
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
                with BenchmarkTracker.section("add_overview_figure_assets"):
                    db_sdk.add_image_assets(
                        client=db_client,
                        plot_dir=viz_dir,
                        plot_files=viz_files,
                        registered_circuit=new_circuit_entity,
                    )
            except Exception as e:  # noqa: BLE001
                # Catch any exception here and turn into warnings only
                L.warning(f"Circuit visualization registration failed: {e}")

    def execute(  # noqa: PLR0915
        self,
        *,
        db_client: Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,
        execution_activity_id: str | None = None,
    ) -> str | None:  # Returns the ID of the extracted circuit
        # Start benchmark tracking
        BenchmarkTracker.start_tracking()

        # Get execution activity (expected to be created and managed externally)
        execution_activity = CircuitExtractionTask._get_execution_activity(
            db_client=db_client, execution_activity_id=execution_activity_id
        )

        # Resolve parent circuit (local path or staging from ID)
        with BenchmarkTracker.section("resolve_circuit"):
            self._resolve_circuit(db_client=db_client, entity_cache=entity_cache)

        # Add neuron set to SONATA circuit object
        # (will raise an error in case already existing)
        with BenchmarkTracker.section("add_node_set"):
            nset_name = self.config.neuron_set.__class__.__name__
            nset_def = self.config.neuron_set.get_node_set_definition(
                self._circuit,  # ty:ignore[invalid-argument-type]
                self._circuit.default_population_name,  # ty:ignore[unresolved-attribute]
            )
            sonata_circuit = self._circuit.sonata_circuit  # ty:ignore[unresolved-attribute]
            add_node_set_to_circuit(
                sonata_circuit, {nset_name: nset_def}, overwrite_if_exists=False
            )

        # Create subcircuit using "brainbuilder"
        L.info(f"Extracting subcircuit from '{self._circuit.name}'")  # ty:ignore[unresolved-attribute]
        with BenchmarkTracker.section("split_subcircuit"):
            split_population.split_subcircuit(
                self.config.coordinate_output_root,
                nset_name,
                sonata_circuit,
                self.config.initialize.do_virtual,
                self.config.initialize.create_external,
            )

        # Custom edit of the circuit config so that all paths are relative to the new base directory
        # (in case there were absolute paths in the original config)

        old_base = os.path.split(self._circuit.path)[0]  # ty:ignore[unresolved-attribute]

        # Fix to deal with symbolic links in the base circuit which may have been resolved
        # Note: .resolve() resolves symlinks!
        alt_base = str(Path(self._circuit.path).resolve().parent)  # ty:ignore[unresolved-attribute]

        new_base = "$BASE_DIR"
        new_circuit_path = Path(self.config.coordinate_output_root) / "circuit_config.json"

        # Create backup before modifying
        # > shutil.copyfile(new_circuit_path, os.path.splitext(new_circuit_path)[0] + ".BAK")

        with Path(new_circuit_path).open(encoding="utf-8") as config_file:
            config_dict = json.load(config_file)
        circuit_utils.rebase_config(config_dict, old_base, new_base)
        if alt_base != old_base:
            # Rebase alternative old base directory as well
            circuit_utils.rebase_config(config_dict, alt_base, new_base)

        with Path(new_circuit_path).open("w", encoding="utf-8") as config_file:
            json.dump(config_dict, config_file, indent=4)

        # Check and fix the node sets file, if needed
        circuit_utils.fix_node_sets_file(new_circuit_path)

        # Copy subcircuit morphologies and e-models (separately per node population)
        with BenchmarkTracker.section("copy_morph_hoc_mod"):
            original_circuit = self._circuit.sonata_circuit  # ty:ignore[unresolved-attribute]
            new_circuit = snap.Circuit(new_circuit_path)
            for pop_name, pop in new_circuit.nodes.items():
                if pop.config["type"] == "biophysical":
                    # Copying morphologies of any (supported) format
                    if "morphology" in pop.property_names:
                        circuit_utils.copy_morphologies(pop_name, pop, original_circuit)

                    # Copy .hoc file directory (Even if defined globally, shows up under pop.config)
                    if "biophysical_neuron_models_dir" in pop.config:
                        circuit_utils.copy_hoc_files(pop_name, pop, original_circuit)

            # Copy .mod files, if any
            circuit_utils.copy_mod_files(
                self._circuit.path,  # ty:ignore[unresolved-attribute]
                self.config.coordinate_output_root,  # ty:ignore[invalid-argument-type]
                "mod",
            )

        # Run circuit validation
        if settings.circuit_extraction.run_validation:
            with BenchmarkTracker.section("run_validation"):
                circuit_utils.run_validation(new_circuit_path)  # ty:ignore[invalid-argument-type]

        L.info("Extraction DONE")

        # Register new circuit entity incl. folder asset and linked entities
        new_circuit_entity = None
        if db_client and self._circuit_entity:
            with BenchmarkTracker.section("register_circuit_entity"):
                new_circuit_entity = self._create_circuit_entity(
                    db_client=db_client, circuit_path=new_circuit_path
                )

            # Register circuit folder asset
            with BenchmarkTracker.section("register_circuit_folder_asset"):
                db_sdk.add_circuit_folder_asset(
                    client=db_client,
                    circuit_path=new_circuit_path,
                    registered_circuit=new_circuit_entity,
                )

            # Derivation link
            self._add_derivation_link(db_client=db_client, registered_circuit=new_circuit_entity)

            # Update execution activity (if any)
            if new_circuit_entity is not None:
                CircuitExtractionTask._update_execution_activity(
                    db_client=db_client,
                    execution_activity=execution_activity,
                    generated=[str(new_circuit_entity.id)],
                )

            L.info("Registration DONE")

        # Generate and register additional circuit asset
        self._generate_additional_circuit_assets(
            db_client=db_client,
            new_circuit_path=new_circuit_path,
            new_circuit_entity=new_circuit_entity,  # ty:ignore[invalid-argument-type]
        )

        # Clean-up
        with BenchmarkTracker.section("cleanup"):
            self._cleanup_temp_dir()

        # Print and save benchmark summary
        benchmark_dir = new_circuit_path.parent.parent / (
            new_circuit_path.parent.name + "__BENCHMARK__"
        )
        benchmark_file = benchmark_dir / "benchmark_results.json"
        BenchmarkTracker.print_summary(output_path=benchmark_file)

        if new_circuit_entity:
            return str(new_circuit_entity.id)
        return None
