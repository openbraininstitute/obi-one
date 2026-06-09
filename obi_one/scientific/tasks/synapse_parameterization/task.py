import logging
import shutil
import tempfile
from pathlib import Path

from connectome_manipulator.model_building import model_types
from entitysdk import Client, models, types
from pydantic import PrivateAttr

from obi_one.core.task import Task
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.synapse_parameterization.config import (
    SynapseParameterizationSingleConfig,
)
from obi_one.scientific.tasks.synapse_parameterization.utils import (
    check_consistent_synapse_models,
    get_default_for,
    write_back_to_edge_file,
)
from obi_one.scientific.unions.unions_synaptic_model_assigner import (
    SynapticModelAssignerUnion,
)
from obi_one.utils import db_sdk

L = logging.getLogger(__name__)


class SynapseParameterizationTask(Task):
    config: SynapseParameterizationSingleConfig

    _circuit: Circuit | None = PrivateAttr(default=None)
    _circuit_entity: models.Circuit | None = PrivateAttr(default=None)
    _pathway_model: model_types.ConnPropsModel | None = PrivateAttr(default=None)
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
        """Register the parameterized circuit as a derivation of the original (dry run).

        Metadata is inherited from the original circuit so that all entity references
        (subject, species, brain region, hierarchy, parent) resolve cleanly.
        """
        # Deferred import: pulls in heavy circuit/asset tooling only when registering.
        from obi_one.utils.circuit_registration.register import (  # noqa: PLC0415
            register_circuit_from_metadata,
        )

        parent = self._circuit_entity
        hierarchy = db_client.get_entity(
            entity_id=parent.brain_region.hierarchy_id,
            entity_type=models.BrainRegionHierarchy,
        )
        circuit_metadata = {
            "name": f"{parent.name} (synapse-parameterized)",
            "description": (
                f"Synapse-parameterized derivation of circuit '{parent.name}' ({parent.id})."
            ),
            "build_category": parent.build_category,
            "species": parent.subject.species.name,
            "subject": parent.subject.name,
            "brain_region": parent.brain_region.name,
            "brain_region_hierarchy": hierarchy.name,
            "target_simulator": parent.target_simulator or types.TargetSimulator.NEURON,
            "parent": parent.name,
            "derivation_type": types.DerivationType.circuit_rewiring,
        }
        return register_circuit_from_metadata(
            client=db_client,
            circuit_metadata=circuit_metadata,
            circuit_path=circuit_path,
            dry_run=True,
        )

    def _assemble_per_edge_population(self) -> dict[str, list[SynapticModelAssignerUnion]]:
        """Splits all SynapticModelAssigners parameterized up by the EdgePopulation they use."""
        per_edge_population = {}
        for _, assigner in self.config.synapse_model_assigners.items():
            per_edge_population.setdefault(assigner.edge_population_name, []).append(assigner)
        return per_edge_population

    def execute(self, *, db_client: Client = None, entity_cache: bool = False) -> None:
        if db_client is None:
            msg = "The synapse parameterization task requires a working db_client!"
            raise ValueError(msg)

        # Resolve the circuit (local path or staging from ID), then copy it into the output
        # directory so that its synapse parameters can be modified in place.
        staged_circuit, self._circuit_entity = db_sdk.resolve_circuit(
            self.config.initialize.circuit,
            db_client=db_client,
            entity_cache=entity_cache,
            cache_root=self.config.scan_output_root,
            temp_dir=self._create_temp_dir(),
        )
        output_dir = self.config.coordinate_output_root.resolve()
        shutil.copytree(Path(staged_circuit.path).parent, output_dir, dirs_exist_ok=False)
        self._circuit = Circuit(
            name=staged_circuit.name, path=str(output_dir / "circuit_config.json")
        )

        # Check parameters
        circ = self._circuit.sonata_circuit
        per_edge_population = self._assemble_per_edge_population()
        for assigners_for_ep in per_edge_population.values():
            check_consistent_synapse_models(assigners_for_ep)

        for ep_name, assigners_for_ep in per_edge_population.items():
            df = get_default_for(assigners_for_ep, ep_name, self._circuit)
            for assigner in assigners_for_ep:
                assigner.assign_parameters(self._circuit, df)
            write_back_to_edge_file(df, circ.edges[ep_name])

        # Register the (re-)parameterized circuit as a derivation of the original (dry run)
        L.info("Registering the output...")
        self._register_parameterized_circuit(db_client=db_client, circuit_path=output_dir)
