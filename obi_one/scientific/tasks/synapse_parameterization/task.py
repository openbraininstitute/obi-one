import logging
import shutil
import tempfile
from pathlib import Path

from entitysdk import Client, models, types
from pydantic import PrivateAttr

from obi_one.config import settings
from obi_one.core.task import Task
from obi_one.db_sdk import db_sdk
from obi_one.db_sdk.registration import circuit as circuit_registration
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.synapse_parameterization.config import (
    SynapseParameterizationSingleConfig,
)
from obi_one.scientific.tasks.synapse_parameterization.utils import (
    check_consistent_synapse_models,
    get_default_for,
    write_back_to_edge_file,
)
from obi_one.scientific.unions_and_references.synaptic_model_assigner import (
    SynapticModelAssignerUnion,
)
from obi_one.utils.benchmark import BenchmarkTracker

if settings.synapse_parameterization.benchmarking_enabled:
    BenchmarkTracker.enable()
else:
    BenchmarkTracker.disable()

L = logging.getLogger(__name__)


class SynapseParameterizationTask(Task):
    config: SynapseParameterizationSingleConfig

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

    def _register_parameterized_circuit(
        self, *, db_client: Client, circuit_path: Path
    ) -> models.Circuit | None:
        """Register the parameterized circuit as a derivation of the original."""
        parent = self._circuit_entity
        if parent is None:
            return None

        return circuit_registration.register_circuit(
            client=db_client,
            circuit_path=circuit_path,
            name=f"{parent.name} (synapse-parameterized)",
            description=f"Synapse-parameterized derivation of circuit '{parent.name}'.",
            build_category=parent.build_category,
            brain_region=parent.brain_region,  # ty:ignore[invalid-argument-type]
            subject=parent.subject,  # ty:ignore[invalid-argument-type]
            target_simulator=parent.target_simulator or types.TargetSimulator.NEURON,
            experiment_date=parent.experiment_date,
            license=parent.license,
            atlas=None,
            root=parent.root_circuit_id or parent.id,
            parent=parent,
            derivation_type=types.DerivationType.circuit_rewiring,
            skip_validation=True,
        )

    def _assemble_per_edge_population(self) -> dict[str, list[SynapticModelAssignerUnion]]:
        """Splits all SynapticModelAssigners parameterized up by the EdgePopulation they use."""
        per_edge_population = {}
        for assigner in self.config.synapse_model_assigners.values():
            per_edge_population.setdefault(assigner.edge_population_name, []).append(assigner)
        return per_edge_population

    def execute(
        self,
        *,
        db_client: Client | None = None,
        entity_cache: bool = False,
        execution_activity_id: str | None = None,
    ) -> str | None:  # Returns the ID of the parameterized circuit
        # Start benchmark tracking
        BenchmarkTracker.start_tracking()

        # Get execution activity (expected to be created and managed externally)
        execution_activity = SynapseParameterizationTask._get_execution_activity(
            db_client=db_client, execution_activity_id=execution_activity_id
        )

        # Resolve the circuit (local path or staging from ID), then copy it into the output
        # directory so that its synapse parameters can be modified in place.
        with BenchmarkTracker.section("resolve_circuit"):
            staged_circuit, self._circuit_entity = db_sdk.resolve_circuit(
                self.config.initialize.circuit,
                db_client=db_client,  # ty:ignore[invalid-argument-type]
                entity_cache=entity_cache,
                cache_root=self.config.scan_output_root,
                temp_dir=self._create_temp_dir(),
            )

        # Check the configuration against the staged circuit *before* copying it. None of
        # these problems can be fixed later in the run, and the copy below is the expensive
        # part - an assigner naming an edge population its neuron sets do not connect used
        # to surface as a KeyError from inside `_edge_indices`, long after this point.
        with BenchmarkTracker.section("validate_config"):
            per_edge_population = self._assemble_per_edge_population()
            staged = Circuit(name=staged_circuit.name, path=str(staged_circuit.path))
            for assigners_for_ep in per_edge_population.values():
                check_consistent_synapse_models(assigners_for_ep)
                for assigner in assigners_for_ep:
                    assigner.validate_for_circuit(staged)

        with BenchmarkTracker.section("copy_circuit"):
            output_dir = self.config.coordinate_output_root.resolve()
            shutil.copytree(Path(staged_circuit.path).parent, output_dir, dirs_exist_ok=False)
            self._circuit = Circuit(
                name=staged_circuit.name, path=str(output_dir / "circuit_config.json")
            )

        with BenchmarkTracker.section("parameterize_synapses"):
            circ = self._circuit.sonata_circuit
            for ep_name, assigners_for_ep in per_edge_population.items():
                df = get_default_for(assigners_for_ep, ep_name, self._circuit)
                for assigner in assigners_for_ep:
                    assigner.assign_parameters(self._circuit, df)
                write_back_to_edge_file(df, circ.edges[ep_name])

        # Register the (re-)parameterized circuit as a derivation of the original.
        # Skipped for local circuits (no parent entity) or when no db_client is available.
        new_circuit_entity = None
        if db_client and self._circuit_entity:
            L.info("Registering the output...")
            with BenchmarkTracker.section("register_circuit"):
                new_circuit_entity = self._register_parameterized_circuit(
                    db_client=db_client, circuit_path=output_dir
                )

            # Update execution activity (if any) with the registered circuit
            if new_circuit_entity is not None:
                SynapseParameterizationTask._update_execution_activity(
                    db_client=db_client,
                    execution_activity=execution_activity,
                    generated=[str(new_circuit_entity.id)],
                )

        # Clean-up
        with BenchmarkTracker.section("cleanup"):
            self._cleanup_temp_dir()

        # Print and save benchmark summary
        benchmark_dir = output_dir.parent / (output_dir.name + "__BENCHMARK__")
        benchmark_file = benchmark_dir / "benchmark_results.json"
        BenchmarkTracker.print_summary(output_path=benchmark_file)

        if new_circuit_entity is not None:
            return str(new_circuit_entity.id)
        return None
