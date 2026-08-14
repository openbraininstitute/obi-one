"""Circuit simplification task: reduces detailed SONATA circuits to simplified representations.

Uses the sonata_simplify pipeline to transform biophysically-detailed circuits into
simplified point-neuron or single-compartment circuits while preserving network
connectivity. Point-neuron algorithms (LIF, AdEx, Izhikevich, GLIF, GIF) are
automatically exported to NEST format; single_compartment produces SONATA/NEURON
output only. Each output (SONATA + export) is registered as a separate Circuit
entity with derivation links to the parent.
"""

import json
import logging
import os
import shutil
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal

import bluepysnap as snap
from entitysdk import Client, models, types
from entitysdk.types import DerivationType
from pydantic import Field, PrivateAttr
from sonata_simplify.algorithms import ALGORITHM_DESCRIPTIONS, ALGORITHM_TITLES

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.db_sdk import db_sdk
from obi_one.db_sdk.registration import circuit as circuit_registration
from obi_one.scientific.blocks.neuron_sets.specific import AllBiophysicalNeurons
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig
from obi_one.scientific.library.simulation.neuron import process
from obi_one.scientific.library.sonata_circuit_helpers import (
    write_circuit_node_set_file,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitDiscriminator,
)
from obi_one.scientific.unions_and_references.neuron_sets import (
    ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES,
    BiophysicalNeuronSetReference,
)
from obi_one.types import SimulationBackend

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block groups for the simplification form."""

    SETUP = "Setup"
    SIMPLIFICATION = "Simplification"


# Literal type for algorithm selection.
# Names encode both the base algorithm and the target simulator:
#   <algorithm>_<simulator>  →  simplifies + exports to that simulator
#   single_compartment       →  SONATA/NEURON only (no export)
SimplificationModelType = Literal[
    "single_compartment",
    "lif_nest",
    "adex_nest",
    "adex_brian2",
    "izhikevich_nest",
    "glif_nest",
    "gif_nest",
]

# Maps compound name → (base_algorithm, exporter_name or None)
# Brian2 only supports AdEx; other algorithms use NEST.
ALGORITHM_EXPORT_MAP: dict[str, tuple[str, str | None]] = {
    "single_compartment": ("single_compartment", None),
    "lif_nest": ("lif", "nest:iaf_psc_alpha"),
    "adex_nest": ("adex", "nest:aeif_cond_alpha"),
    "adex_brian2": ("adex", "brian2:adex"),
    "izhikevich_nest": ("izhikevich", "nest:izhikevich"),
    "glif_nest": ("glif", "nest:glif_psc"),
    "gif_nest": ("gif", "nest:gif_cond_exp"),
}

# UI display titles for compound names (extends ALGORITHM_TITLES from sonata_simplify)
ALGORITHM_EXPORT_TITLES: dict[str, str] = {
    "single_compartment": (
        f"{ALGORITHM_TITLES.get('single_compartment', 'Single Compartment')} (NEURON)"
    ),
    "lif_nest": f"{ALGORITHM_TITLES.get('lif', 'LIF')} (NEST)",
    "adex_nest": f"{ALGORITHM_TITLES.get('adex', 'AdEx')} (NEST)",
    "adex_brian2": f"{ALGORITHM_TITLES.get('adex', 'AdEx')} (Brian2)",
    "izhikevich_nest": f"{ALGORITHM_TITLES.get('izhikevich', 'Izhikevich')} (NEST)",
    "glif_nest": f"{ALGORITHM_TITLES.get('glif', 'GLIF')} (NEST)",
    "gif_nest": f"{ALGORITHM_TITLES.get('gif', 'GIF')} (NEST)",
}

# UI descriptions for compound names
ALGORITHM_EXPORT_DESCRIPTIONS: dict[str, str] = {
    name: ALGORITHM_DESCRIPTIONS.get(base, "") for name, (base, _) in ALGORITHM_EXPORT_MAP.items()
}


class CircuitSimplificationScanConfig(InfoScanConfig):
    """ScanConfig for simplifying SONATA circuits.

    Transforms detailed biophysical circuits into simplified representations
    while preserving network connectivity. Multiple target models can be selected,
    each producing a separate simplified output circuit.
    """

    name: ClassVar[str] = "Circuit Simplification"
    description: ClassVar[str] = (
        "Simplifies a SONATA circuit by reducing biophysical complexity while preserving"
        " network connectivity. Supports multiple target models (single-compartment,"
        " LIF, AdEx, Izhikevich, GLIF, GIF). Point-neuron models are automatically"
        " exported to NEST format."
    )

    default_node_set_name: ClassVar[str] = "Default: All Biophysical Neurons"
    default_neuron_set_type: ClassVar[type[AllBiophysicalNeurons]] = AllBiophysicalNeurons

    @property
    def default_neuron_set_reference(self) -> BiophysicalNeuronSetReference:
        """The default neuron set reference (all biophysical neurons)."""
        ref = BiophysicalNeuronSetReference(
            block_dict_name="neuron_sets", block_name=self.default_node_set_name
        )
        ref.block = self.default_neuron_set_type()
        ref.block.set_block_name(self.default_node_set_name)
        return ref

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP,
            BlockGroup.SIMPLIFICATION,
        ],
        SchemaKey.PROPERTY_ENDPOINTS: {
            "circuit": "/mapped-circuit-properties/{circuit_id}",
        },
    }

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
            description="Input SONATA circuit to be simplified.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER,
                SchemaKey.PARAMETER_ORDER_PRIORITY: 100,
            },
        )
        node_set: BiophysicalNeuronSetReference | None = Field(
            default=None,
            title="Neuron Set",
            description=(
                "Neuron set to simplify. If None, defaults to all biophysical neurons."
                " Currently hidden from the UI — always uses the default."
            ),
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
                SchemaKey.REFERENCE_TYPES: ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES,
                SchemaKey.PARAMETER_ORDER_PRIORITY: 99,
                SchemaKey.UI_HIDDEN: True,
            },
        )

    class Simplification(Block):
        algorithms: list[SimplificationModelType] = Field(
            default=["single_compartment"],
            title="Algorithms",
            description=(
                "Select one or more target models for simplification."
                " Each produces a separate simplified output circuit."
                " Names encode the target simulator: e.g. 'adex_nest' exports"
                " to NEST, 'adex_brian2' exports to Brian2."
            ),
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION_ENHANCED,
                SchemaKey.TITLE_BY_KEY: ALGORITHM_EXPORT_TITLES,
                SchemaKey.DESCRIPTION_BY_KEY: ALGORITHM_EXPORT_DESCRIPTIONS,
            },
        )

    info: Info = Field(
        title="Info",
        description="Information about the simplification campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    initialize: Initialize = Field(
        title="Initialization",
        description="Input circuit to be simplified.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    simplification: Simplification = Field(
        title="Algorithms",
        description="Target models for simplification.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SIMPLIFICATION,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class CircuitSimplificationSingleConfig(CircuitSimplificationScanConfig, SingleConfigMixin):
    """Single-coordinate configuration for circuit simplification.

    Enforces that all parameters are single values (no scan dimensions).
    """


class CircuitSimplificationTask(Task):
    """Task that runs the sonata_simplify pipeline to produce simplified circuits.

    For each selected algorithm, the task:
    1. Runs the SimplificationPipeline to reduce the input circuit.
    2. For point-neuron algorithms, automatically exports to NEST format.
    3. Registers each output (SONATA + NEST export) as a Circuit entity
       with derivation links to the parent, using the correct target_simulator.
    """

    config: CircuitSimplificationSingleConfig
    _circuit: Circuit | None = PrivateAttr(default=None)
    _circuit_entity: models.Circuit | None = PrivateAttr(default=None)

    def _register_output(
        self,
        db_client: Client,
        circuit_path: Path,
        algorithm_name: str,
        export_suffix: str = "",
    ) -> models.Circuit | None:
        """Register a simplified circuit entity with derivation link to parent.

        Args:
            db_client: Entitycore client.
            circuit_path: Path to the output circuit_config.json.
            algorithm_name: Algorithm name (for naming/description).
            export_suffix: Suffix appended to the circuit name for exports
                (e.g. ``"_nest_aeif_cond_alpha"``). Empty for SONATA-only output.
        """
        parent = self._circuit_entity

        # Read target_simulator from the output circuit_config.json
        # (the pipeline/exporter sets it correctly: NEURON for single_compartment,
        # NEST for point-neuron exports, Brian2 for Brian2 exports).
        target_simulator = self._read_target_simulator(circuit_path)

        campaign_str = self.config.info.campaign_name.replace(" ", "-")
        circuit_name = f"{parent.name}__{campaign_str}__{algorithm_name}{export_suffix}"  # ty:ignore[unresolved-attribute]
        circuit_descr = (
            f"{self.config.info.campaign_description} - Simplified using '{algorithm_name}'"
        )

        return circuit_registration.register_circuit(
            client=db_client,
            circuit_path=circuit_path,
            name=circuit_name,
            description=circuit_descr,
            build_category=parent.build_category,  # ty:ignore[unresolved-attribute]
            brain_region=parent.brain_region,  # ty:ignore[unresolved-attribute, invalid-argument-type]
            subject=parent.subject,  # ty:ignore[unresolved-attribute, invalid-argument-type]
            target_simulator=target_simulator,
            experiment_date=parent.experiment_date,  # ty:ignore[unresolved-attribute]
            license=parent.license,  # ty:ignore[unresolved-attribute]
            atlas=None,
            root=parent.root_circuit_id or parent.id,  # ty:ignore[unresolved-attribute]
            parent=parent,
            derivation_type=DerivationType.circuit_simplification,
        )

    @staticmethod
    def _build_simulation_config(
        input_circuit_path: str,
        output_dir: Path,
        node_set_name: str | None = None,
        node_sets_file: str | None = None,
    ) -> Path:
        """Build a simulation_config.json for the sonata_simplify pipeline.

        The pipeline expects a simulation config JSON that references the
        circuit config and output directory. If ``node_set_name`` and
        ``node_sets_file`` are provided, they are included in the sim config
        so the pipeline can resolve the node set via BluePySnap (merging
        the sim config's node sets with the circuit's, same as BCL/ND).
        """
        sim_config = {
            "manifest": {"$BASE_DIR": str(Path(input_circuit_path).parent)},
            "network": "$BASE_DIR/" + str(Path(input_circuit_path).name),
            "output": {
                "output_dir": str(output_dir / "output"),
                "spikes_file": "spikes.h5",
            },
            "run": {
                "dt": 0.025,
                "random_seed": 1,
                "tstop": 3000.0,
            },
            "conditions": {
                "v_init": -80.0,
            },
        }
        if node_set_name is not None:
            sim_config["node_set"] = node_set_name
        if node_sets_file is not None:
            sim_config["node_sets_file"] = node_sets_file

        sim_config_path = output_dir / "simulation_config.json"
        with Path(sim_config_path).open("w", encoding="utf-8") as f:
            json.dump(sim_config, f, indent=2)

        return sim_config_path

    def _resolve_node_set(self, output_dir: Path) -> str | None:
        """Resolve the neuron set and write a node_sets.json to the output dir.

        Follows the same pattern as generate_simulations: adds the neuron set
        to the SONATA circuit object (in memory), writes the updated node sets
        to ``node_sets.json`` in the output dir, and returns the node set name.

        The sim config will reference this file via ``node_sets_file``, and the
        pipeline merges it with the circuit's existing node sets (same as BCL/ND).

        Returns the node set name, or None if no neuron set is configured.
        """
        node_set_ref = self.config.initialize.node_set
        if node_set_ref is None:
            # Use default: all biophysical neurons
            node_set_ref = self.config.default_neuron_set_reference

        if node_set_ref is None:
            return None

        # Set block name if not already set
        block = node_set_ref.block
        if not block.has_block_name():
            block.set_block_name(node_set_ref.block_name)

        # Add node set to the SONATA circuit object (in memory) and write to file.
        # This does NOT modify the input circuit files — it only writes a new
        # node_sets.json to the output directory.
        sonata_circuit = self._circuit.sonata_circuit  # ty:ignore[unresolved-attribute]
        block.add_node_set_definition_to_sonata_circuit(
            self._circuit,  # ty:ignore[invalid-argument-type]
            sonata_circuit,
            force_resolve_ids=True,
        )
        write_circuit_node_set_file(
            sonata_circuit,
            str(output_dir),
            file_name="node_sets.json",
            overwrite_if_exists=True,
        )
        L.info(f"Node set '{block.block_name}' written to {output_dir / 'node_sets.json'}")
        return block.block_name

    @staticmethod
    def _smoke_check_loadability(circuit_config_path: Path, algorithm_name: str) -> None:
        """Verify that the simplified circuit can be loaded by BluePySnap.

        Attempts to load the output circuit_config.json with ``bluepysnap.Circuit``.
        If loading fails, raises ``RuntimeError`` so the task fails before
        registering an unusable circuit entity (F11).

        Args:
            circuit_config_path: Path to the simplified circuit_config.json.
            algorithm_name: Algorithm name (for error messaging).

        Raises:
            RuntimeError: If the circuit cannot be loaded.
        """
        try:
            snap.Circuit(str(circuit_config_path))
            L.info(f"Smoke check passed: '{algorithm_name}' circuit is loadable")
        except Exception as e:
            msg = (
                f"Smoke check FAILED for algorithm '{algorithm_name}': "
                f"the simplified circuit at {circuit_config_path} cannot be "
                f"loaded by BluePySnap. Error: {e}"
            )
            L.error(msg)
            raise RuntimeError(msg) from e

    @staticmethod
    def _read_target_simulator(circuit_config_path: Path) -> types.TargetSimulator:
        """Read target_simulator from a circuit_config.json.

        The pipeline/exporter sets this correctly in the output:
        - ``single_compartment`` → ``NEURON`` (inherited from parent circuit)
        - NEST exports → ``NEST``
        - Brian2 exports → ``Brian2``

        Falls back to the parent's target_simulator if the field is absent.
        """
        with Path(circuit_config_path).open(encoding="utf-8") as f:
            cfg = json.load(f)
        sim_str = cfg.get("target_simulator", "NEURON")
        try:
            return types.TargetSimulator(sim_str)
        except ValueError:
            L.warning(
                f"Unknown target_simulator '{sim_str}' in"
                f" {circuit_config_path}, defaulting to NEURON"
            )
            return types.TargetSimulator.NEURON

    def execute(  # ruff: ignore[complex-structure, too-many-locals, too-many-statements]
        self,
        *,
        db_client: Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,
        execution_activity_id: str | None = None,
    ) -> str | None:
        """Execute the circuit simplification task.

        Returns the ID of the first registered simplified circuit, or None.
        """
        # Get execution activity
        execution_activity = CircuitSimplificationTask._get_execution_activity(
            db_client=db_client, execution_activity_id=execution_activity_id
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            # Resolve parent circuit (local path or staging from ID)
            self._circuit, self._circuit_entity = db_sdk.resolve_circuit(
                self.config.initialize.circuit,  # ty:ignore[invalid-argument-type]
                db_client=db_client,
                entity_cache=entity_cache,
                cache_root=self.config.scan_output_root,
                temp_dir=Path(temp_dir),
            )

            input_circuit_path = Path(self._circuit.path).absolute()

            # After GridScanGenerationTask expands the scan config, list fields
            # with a single element are unwrapped to scalar values. Wrap algorithms
            # back into a list so iteration works correctly either way.
            algorithms = self.config.simplification.algorithms
            if isinstance(algorithms, str):
                algorithms = [algorithms]

            # Resolve neuron set and write node_sets.json to the output root.
            # The node set name and node_sets_file are passed via the sim config
            # so the pipeline can resolve the node set via BluePySnap (merging
            # the sim config's node sets with the circuit's, same as BCL/ND).
            node_set_name = self._resolve_node_set(self.config.coordinate_output_root)

            output_circuit_ids: list[str] = []
            if "single_compartment" in algorithms:
                mechanisms_dir = process.get_mechanisms_dirs(input_circuit_path)
                assert len(mechanisms_dir) == 1, "Do not currently handle multiple mechanisms_dirs"  # ruff: ignore[assert]
                mechanisms_dir = next(iter(mechanisms_dir))
                sim_backend = (
                    SimulationBackend.neurodamus
                    if shutil.which("neurodamus-compile-mods")
                    else SimulationBackend.bluecellulab
                )
                process.compile_mechanisms(
                    output_dir=Path(),
                    mechanisms_dir=mechanisms_dir,
                    simulation_backend=sim_backend,
                )

            # Import sonata_simplify lazily (heavy dependencies)
            from sonata_simplify.pipeline import (  # ruff: ignore[import-outside-top-level]
                SimplificationPipeline,
            )
            from sonata_simplify.recipe import Recipe  # ruff: ignore[import-outside-top-level]

            for algorithm_name in algorithms:
                L.info(f"Running simplification with algorithm: {algorithm_name}")

                # Split compound name into base algorithm and exporter
                # e.g. "adex_nest" → ("adex", "nest:aeif_cond_alpha")
                base_algorithm, exporter_name = ALGORITHM_EXPORT_MAP[algorithm_name]

                # Create output directory for this algorithm
                output_dir = (self.config.coordinate_output_root / algorithm_name).absolute()
                output_dir.mkdir(parents=True, exist_ok=True)

                # Build simulation config for the pipeline.
                # If a node set was resolved, include node_set (name) and
                # node_sets_file derived relative to this algorithm's sim config.
                node_sets_file = (
                    os.path.relpath(
                        self.config.coordinate_output_root / "node_sets.json",
                        start=output_dir,
                    )
                    if node_set_name is not None
                    else None
                )
                sim_config_path = CircuitSimplificationTask._build_simulation_config(
                    str(input_circuit_path),
                    output_dir,
                    node_set_name=node_set_name,
                    node_sets_file=node_sets_file,
                )

                # Initialize the pipeline with the BASE algorithm name
                # (the pipeline's simplification_mode expects "lif", not "lif_nest")
                pipeline = SimplificationPipeline(
                    simulation_config=str(sim_config_path),
                    simplification_mode=base_algorithm,
                )

                # Run the pipeline with a recipe that includes the exporter
                recipe = Recipe.from_mode(base_algorithm, exporter=exporter_name)
                pipeline.run_recipe(recipe)

                # The simplified SONATA circuit is in output_dir / "output"
                # (the sim config sets output_dir to output_dir / "output")
                simplified_circuit_path = output_dir / "output" / "circuit_config.json"

                if not simplified_circuit_path.exists():
                    L.warning(
                        f"Simplified circuit config not found at {simplified_circuit_path}"
                        f" for algorithm '{algorithm_name}'"
                    )
                    continue

                # Smoke check: verify the simplified circuit is loadable
                # before registering it. A malformed output would create an
                # unusable circuit entity (F11).
                self._smoke_check_loadability(simplified_circuit_path, algorithm_name)

                # Register the SONATA output circuit entity
                if db_client and self._circuit_entity:
                    new_circuit_entity = self._register_output(
                        db_client=db_client,
                        circuit_path=simplified_circuit_path,
                        algorithm_name=algorithm_name,
                    )
                    if new_circuit_entity is not None:
                        output_circuit_ids.append(str(new_circuit_entity.id))

                # Register the exported circuit (if an exporter was used)
                if exporter_name and db_client and self._circuit_entity:
                    export_suffix = exporter_name.replace(":", "_")
                    export_dir = simplified_circuit_path.parent / f"output_{export_suffix}"
                    export_circuit_path = export_dir / "circuit_config.json"
                    if export_circuit_path.exists():
                        L.info(f"Registering exported circuit: {export_circuit_path}")
                        export_entity = self._register_output(
                            db_client=db_client,
                            circuit_path=export_circuit_path,
                            algorithm_name=algorithm_name,
                            export_suffix=f"_{export_suffix}",
                        )
                        if export_entity is not None:
                            output_circuit_ids.append(str(export_entity.id))
                    else:
                        L.warning(
                            f"Export output not found at {export_circuit_path}"
                            f" for algorithm '{algorithm_name}'"
                        )

                L.info(f"Simplification with '{algorithm_name}' DONE")

            # Update execution activity
            if db_client and execution_activity and output_circuit_ids:
                CircuitSimplificationTask._update_execution_activity(
                    db_client=db_client,
                    execution_activity=execution_activity,
                    generated=output_circuit_ids,
                )

        if output_circuit_ids:
            return output_circuit_ids[0]
        return None
