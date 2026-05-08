import json
import logging
import os
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

import bluepysnap as snap
import bluepysnap.circuit_validation
from brainbuilder.utils.sonata import split_population
from entitysdk import Client, models, types
from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import Field, PrivateAttr

from obi_one.config import settings
from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.entity_property_types import (
    MappedPropertiesGroup,
)
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig
from obi_one.scientific.library.sonata_circuit_helpers import add_node_set_to_circuit
from obi_one.scientific.tasks.generate_simulations.config.circuit import (
    CircuitDiscriminator,
)
from obi_one.scientific.unions.unions_neuron_sets import CircuitExtractionNeuronSetUnion
from obi_one.utils import circuit as circuit_utils, circuit_registration
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
    neuron_set: CircuitExtractionNeuronSetUnion = Field(
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

    def _register_output(
        self, db_client: Client, circuit_path: Path
    ) -> models.Circuit:
        """Register the extracted circuit entity with assets and derivation link."""
        parent = self._circuit_entity

        # Build circuit name and description
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

        return circuit_registration.register_circuit(
            client=db_client,
            circuit_path=circuit_path,
            name=circuit_name,
            description=circuit_descr,
            build_category=parent.build_category,  # ty:ignore[unresolved-attribute]
            brain_region=parent.brain_region,  # ty:ignore[unresolved-attribute]
            subject=parent.subject,  # ty:ignore[unresolved-attribute]
            contact_email=parent.contact_email,  # ty:ignore[unresolved-attribute]
            published_in=parent.published_in,  # ty:ignore[unresolved-attribute]
            experiment_date=parent.experiment_date,  # ty:ignore[unresolved-attribute]
            license=parent.license,  # ty:ignore[unresolved-attribute]
            atlas=None,  # TODO: Not yet implemented
            root=parent.root_circuit_id or parent.id,  # ty:ignore[unresolved-attribute]
            parent=parent,
            derivation_type=types.DerivationType.circuit_extraction,
        )

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
            with BenchmarkTracker.section("register_circuit"):
                new_circuit_entity = self._register_output(
                    db_client=db_client, circuit_path=new_circuit_path
                )

            # Update execution activity (if any)
            if new_circuit_entity is not None:
                CircuitExtractionTask._update_execution_activity(
                    db_client=db_client,
                    execution_activity=execution_activity,
                    generated=[str(new_circuit_entity.id)],
                )

            L.info("Registration DONE")

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
