"""ME-model synapse placement task."""

import logging
from pathlib import Path

from entitysdk import Client, types

from obi_one.core.task import Task
from obi_one.db_sdk.registration import circuit as circuit_registration
from obi_one.scientific.library.build_synaptome import (
    BuildSynaptomeResult,
    build_synaptome_artifact,
)
from obi_one.scientific.tasks.build_synaptome.config import (
    MEModelSynapticModelPlacementSingleConfig,
)

L = logging.getLogger(__name__)


def build_synaptome(
    config: MEModelSynapticModelPlacementSingleConfig,
    output_directory: Path,
    *,
    db_client: Client,
) -> BuildSynaptomeResult:
    """Build and validate a simulatable single-neuron SONATA synaptome."""
    return build_synaptome_artifact(config, output_directory, db_client=db_client)


class MEModelSynapticModelPlacementTask(Task):
    """Build and register a single-cell synaptome circuit."""

    config: MEModelSynapticModelPlacementSingleConfig

    def execute(
        self,
        *,
        db_client: Client,
        entity_cache: bool = False,
        execution_activity_id: str | None = None,
    ) -> str:
        """Generate the SONATA artifact and register it through Activity provenance."""
        _ = entity_cache
        execution_activity = self._get_execution_activity(
            db_client=db_client,
            execution_activity_id=execution_activity_id,
        )
        me_model = self.config.initialize.me_model.entity(db_client=db_client)
        subject = me_model.morphology.subject
        if subject is None:
            msg = f"ME-model '{me_model.id}' morphology has no subject for Circuit registration."
            raise ValueError(msg)
        result = build_synaptome_artifact(
            self.config,
            self.config.coordinate_output_root / "SONATA",
            db_client=db_client,
        )

        circuit = circuit_registration.register_circuit(
            client=db_client,
            circuit_path=result.circuit_config_path,
            name=self.config.info.campaign_name,
            description=self.config.info.campaign_description,
            build_category=types.CircuitBuildCategory.computational_model,
            brain_region=me_model.brain_region,
            subject=subject,
            target_simulator=types.TargetSimulator.NEURON,
            experiment_date=me_model.morphology.experiment_date,
            license=me_model.license or me_model.morphology.license,
            derived_from_emodel=me_model.emodel,
            derivation_label=result.model_template,
        )
        if circuit is None:
            msg = "Build Synaptome circuit registration did not return a Circuit."
            raise RuntimeError(msg)

        self._update_execution_activity(
            db_client=db_client,
            execution_activity=execution_activity,
            generated=[str(circuit.id)],
        )
        L.info("Build Synaptome completed. Output Circuit ID: %s", circuit.id)
        return str(circuit.id)
