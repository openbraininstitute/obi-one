"""Circuit simplification task: reduces detailed SONATA circuits to simplified representations.

Uses the sonata_simplify pipeline to transform biophysically-detailed circuits into
simplified point-neuron or single-compartment circuits while preserving network
connectivity. Supports multiple simplification algorithms and optional export to
NEST or BRIAN2 formats.
"""

import json
import logging
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from entitysdk import Client, models
from entitysdk.types import DerivationType, TaskActivityType, TaskConfigType
from pydantic import Field, PrivateAttr

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitDiscriminator,
)
from obi_one.utils import db_sdk
from obi_one.utils.circuit_registration import register as circuit_registration

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block groups for the simplification form."""

    SETUP = "Setup"
    SIMPLIFICATION = "Simplification"


class SimplificationAlgorithm(StrEnum):
    """Available simplification algorithms.

    These map to the algorithms registered in sonata_simplify.algorithms.registry.
    """

    single_compartment = "single_compartment"
    lif = "lif"
    adex = "adex"
    izhikevich = "izhikevich"
    glif = "glif"
    gif = "gif"


class ExportFormat(StrEnum):
    """Target simulator export formats."""

    none = "none"
    nest = "nest"
    brian2 = "brian2"


class CircuitSimplificationScanConfig(InfoScanConfig):
    """ScanConfig for simplifying SONATA circuits.

    Transforms detailed biophysical circuits into simplified representations
    while preserving network connectivity. Multiple algorithms can be selected,
    each producing a separate simplified output circuit.
    """

    single_coord_class_name: ClassVar[str] = "CircuitSimplificationSingleConfig"
    name: ClassVar[str] = "Circuit Simplification"
    description: ClassVar[str] = (
        "Simplifies a SONATA circuit by reducing biophysical complexity while preserving"
        " network connectivity. Supports multiple simplification algorithms (single-compartment,"
        " LIF, AdEx, Izhikevich, GLIF, GIF) and optional export to NEST or BRIAN2 formats."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP, BlockGroup.SIMPLIFICATION],
        SchemaKey.PROPERTY_ENDPOINTS: {
            "circuit": "/mapped-circuit-properties/{circuit_id}",
        },
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = (
        TaskConfigType.circuit_simplification__campaign
    )
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.circuit_simplification__config_generation
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
            description="Input SONATA circuit to be simplified.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER,
                SchemaKey.PARAMETER_ORDER_PRIORITY: 100,
            },
        )

    class Simplification(Block):
        algorithms: list[SimplificationAlgorithm] = Field(
            default=[SimplificationAlgorithm.single_compartment],
            title="Simplification Algorithms",
            description="Select one or more simplification algorithms. Each selected algorithm"
            " produces a separate simplified output circuit.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION,
            },
        )
        compute_filters: bool = Field(
            default=True,
            title="Compute Filters",
            description="Whether to compute tau_corr and w_corr filters for soma correction.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
            },
        )
        biophysical_population: str | None = Field(
            default=None,
            title="Biophysical Population",
            description="Name of the biophysical population to simplify (default: auto-detect).",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
            },
        )
        simplified_params_path: str | None = Field(
            default=None,
            title="Simplified Parameters Path",
            description="Path to custom simplified_parameters.json file. If not provided,"
            " bundled defaults are used.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
            },
        )
        morphology_dir: str | None = Field(
            default=None,
            title="Morphology Directory",
            description="Custom simplified morphology directory (optional).",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
            },
        )
        hoc_dir: str | None = Field(
            default=None,
            title="HOC Directory",
            description="Custom simplified HOC templates directory (optional).",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
            },
        )
        mod_dir: str | None = Field(
            default=None,
            title="MOD Directory",
            description="Custom MOD files directory (optional).",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
            },
        )
        export_format: ExportFormat = Field(
            default=ExportFormat.none,
            title="Export Format",
            description="Export the simplified circuit to a target simulator format (none, NEST,"
            " or BRIAN2).",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION,
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
        title="Simplification",
        description="Simplification algorithm and parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SIMPLIFICATION,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class CircuitSimplificationSingleConfig(
    CircuitSimplificationScanConfig, SingleConfigMixin
):
    """Single-coordinate configuration for circuit simplification.

    Enforces that all parameters are single values (no scan dimensions).
    """

    _single_task_config_type: ClassVar[TaskConfigType] = (
        TaskConfigType.circuit_simplification__config
    )
    _single_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.circuit_simplification__execution
    )


class CircuitSimplificationTask(Task):
    """Task that runs the sonata_simplify pipeline to produce simplified circuits.

    For each selected algorithm, the task:
    1. Runs the SimplificationPipeline to reduce the input circuit.
    2. Optionally exports to NEST or BRIAN2 format.
    3. Registers the output as a Circuit entity with derivation links to the parent.
    """

    config: CircuitSimplificationSingleConfig
    _circuit: Circuit | None = PrivateAttr(default=None)
    _circuit_entity: models.Circuit | None = PrivateAttr(default=None)
    _temp_dir: tempfile.TemporaryDirectory | None = PrivateAttr(default=None)

    def __del__(self) -> None:
        """Destructor for automatic clean-up."""
        self._cleanup_temp_dir()

    def _create_temp_dir(self) -> Path:
        """Create a new temporary directory."""
        self._cleanup_temp_dir()
        self._temp_dir = tempfile.TemporaryDirectory()
        return Path(self._temp_dir.name).resolve()

    def _cleanup_temp_dir(self) -> None:
        """Clean up temporary directory if it exists."""
        if self._temp_dir is not None:
            self._temp_dir.cleanup()
            self._temp_dir = None

    def _register_output(
        self,
        db_client: Client,
        circuit_path: Path,
        algorithm_name: str,
    ) -> models.Circuit | None:
        """Register a simplified circuit entity with derivation link to parent."""
        parent = self._circuit_entity

        campaign_str = self.config.info.campaign_name.replace(" ", "-")
        circuit_name = f"{parent.name}__{campaign_str}__{algorithm_name}"  # ty:ignore[unresolved-attribute]
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
            target_simulator=parent.target_simulator,  # ty:ignore[unresolved-attribute]
            experiment_date=parent.experiment_date,  # ty:ignore[unresolved-attribute]
            license=parent.license,  # ty:ignore[unresolved-attribute]
            atlas=None,
            root=parent.root_circuit_id or parent.id,  # ty:ignore[unresolved-attribute]
            parent=parent,
            derivation_type=DerivationType.circuit_simplification,
        )

    @staticmethod
    def _build_simulation_config(
        input_circuit_path: str, output_dir: Path
    ) -> Path:
        """Build a simulation_config.json for the sonata_simplify pipeline.

        The pipeline expects a simulation config JSON that references the
        circuit config and output directory.
        """
        sim_config = {
            "manifest": {"$BASE_DIR": str(Path(input_circuit_path).parent)},
            "network": str(Path(input_circuit_path).name),
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

        sim_config_path = output_dir / "simulation_config.json"
        with Path(sim_config_path).open("w", encoding="utf-8") as f:
            json.dump(sim_config, f, indent=2)

        return sim_config_path

    def execute(
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

        # Resolve parent circuit (local path or staging from ID)
        self._circuit, self._circuit_entity = db_sdk.resolve_circuit(
            self.config.initialize.circuit,  # ty:ignore[invalid-argument-type]
            db_client=db_client,
            entity_cache=entity_cache,
            cache_root=self.config.scan_output_root,
            temp_dir=self._create_temp_dir(),
        )

        input_circuit_path = self._circuit.path
        simplification = self.config.simplification

        # Import sonata_simplify lazily (heavy dependencies)
        from sonata_simplify.pipeline import SimplificationPipeline  # noqa: PLC0415

        output_circuit_ids: list[str] = []

        for algorithm in simplification.algorithms:
            algorithm_name = algorithm.value if hasattr(algorithm, "value") else str(algorithm)
            L.info(f"Running simplification with algorithm: {algorithm_name}")

            # Create output directory for this algorithm
            output_dir = self.config.coordinate_output_root / algorithm_name
            output_dir.mkdir(parents=True, exist_ok=True)

            # Build simulation config for the pipeline
            sim_config_path = CircuitSimplificationTask._build_simulation_config(
                input_circuit_path, output_dir
            )

            # Initialize the pipeline
            pipeline = SimplificationPipeline(
                simulation_config=str(sim_config_path),
                simplified_params_path=(
                    Path(simplification.simplified_params_path)
                    if simplification.simplified_params_path
                    else None
                ),
                morphology_dir=(
                    Path(simplification.morphology_dir)
                    if simplification.morphology_dir
                    else None
                ),
                hoc_dir=(
                    Path(simplification.hoc_dir) if simplification.hoc_dir else None
                ),
                mod_dir=(
                    Path(simplification.mod_dir) if simplification.mod_dir else None
                ),
                biophysical_population=simplification.biophysical_population,
                simplification_mode=algorithm_name,
            )

            # Run the pipeline
            pipeline.run()

            # The simplified circuit is in output_dir
            simplified_circuit_path = output_dir / "circuit_config.json"

            if not simplified_circuit_path.exists():
                L.warning(
                    f"Simplified circuit config not found at {simplified_circuit_path}"
                    f" for algorithm '{algorithm_name}'"
                )
                continue

            # Optionally export to NEST or BRIAN2
            if simplification.export_format != ExportFormat.none:
                CircuitSimplificationTask._run_exporter(
                    simplification.export_format,
                    input_circuit_dir=output_dir,
                    output_dir=output_dir / f"export_{simplification.export_format.value}",
                    algorithm_name=algorithm_name,
                )

            # Register the simplified circuit entity
            new_circuit_entity = None
            if db_client and self._circuit_entity:
                new_circuit_entity = self._register_output(
                    db_client=db_client,
                    circuit_path=simplified_circuit_path,
                    algorithm_name=algorithm_name,
                )
                if new_circuit_entity is not None:
                    output_circuit_ids.append(str(new_circuit_entity.id))

            L.info(f"Simplification with '{algorithm_name}' DONE")

        # Update execution activity
        if db_client and execution_activity and output_circuit_ids:
            CircuitSimplificationTask._update_execution_activity(
                db_client=db_client,
                execution_activity=execution_activity,
                generated=output_circuit_ids,
            )

        # Clean up
        self._cleanup_temp_dir()

        if output_circuit_ids:
            return output_circuit_ids[0]
        return None

    @staticmethod
    def _run_exporter(
        export_format: ExportFormat,
        input_circuit_dir: Path,
        output_dir: Path,
        algorithm_name: str,
    ) -> None:
        """Run the appropriate exporter for the simplified circuit."""
        from sonata_simplify.exporters import get_exporter  # noqa: PLC0415

        output_dir.mkdir(parents=True, exist_ok=True)

        exporter_name = export_format.value
        L.info(f"Exporting simplified circuit '{algorithm_name}' to {exporter_name}")

        try:
            exporter = get_exporter(
                exporter_name,
                input_circuit_dir=str(input_circuit_dir),
                output_dir=str(output_dir),
            )
            exporter.export()
            L.info(f"Export to {exporter_name} completed")
        except Exception:  # noqa: BLE001
            L.exception(f"Export to {exporter_name} failed")
