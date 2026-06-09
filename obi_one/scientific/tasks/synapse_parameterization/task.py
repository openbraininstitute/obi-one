import logging
import shutil
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

L = logging.getLogger(__name__)


class SynapseParameterizationTask(Task):
    config: SynapseParameterizationSingleConfig

    _circuit: Circuit | None = PrivateAttr(default=None)
    _circuit_entity: models.Circuit | None = PrivateAttr(default=None)
    _pathway_model: model_types.ConnPropsModel | None = PrivateAttr(default=None)

    def _stage_circuit(self, *, db_client: Client, entity_cache: bool) -> Path:
        self._circuit_entity = self.config.initialize.circuit.entity(db_client=db_client)
        root_dir = self.config.scan_output_root.resolve()
        output_dir = self.config.coordinate_output_root.resolve()

        if entity_cache:
            # Use a cache directory at the campaign root --> Won't be deleted after extraction!
            L.info("Using entity cache")
            stage_dir = root_dir / "entity_cache" / "sonata_circuit" / str(self._circuit_entity.id)
        else:
            # Stage circuit directly in output directory --> Modify in-place!
            stage_dir = output_dir

        circuit = self.config.initialize.circuit.stage_circuit(
            db_client=db_client, dest_dir=stage_dir, entity_cache=entity_cache
        )

        if output_dir != stage_dir:
            # Copy staged circuit into output directory
            shutil.copytree(stage_dir, output_dir, dirs_exist_ok=False)
            circuit = Circuit(name=circuit.name, path=str(output_dir / "circuit_config.json"))

        self._circuit = circuit

        return output_dir

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

        # Stage circuit
        output_dir = self._stage_circuit(db_client=db_client, entity_cache=entity_cache)

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
