"""Task that builds a SONATA circuit from an organoid circuit build config."""

import json
import logging
import re
import shutil
from pathlib import Path

from entitysdk.client import Client
from sonata_builder import BuildOptions, DesignSpec, build_circuit

from obi_one.core.task import Task
from obi_one.scientific.tasks.circuit_build.config import (
    OrganoidCircuitBuildSingleConfig,
)
from obi_one.scientific.tasks.circuit_build.registration import register_built_circuit
from obi_one.scientific.tasks.circuit_build.staging import (
    build_ads_dict,
    stage_components,
)

L = logging.getLogger(__name__)

ADS_FILENAME = "circuit_build_ads.json"


def _sanitize_name(name: str) -> str:
    """Turn a campaign name into a filesystem-safe directory name."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "circuit"


class OrganoidCircuitBuildTask(Task):
    """Build a simulatable SONATA circuit with sonata-builder and register it.

    Steps:
      1. Download the MEModel components (hoc, morphology, mechanisms) referenced
         by each population and stage the Tsodyks-Markram synapse mechanisms.
      2. Translate the config into an ADS (Assembloid Design Specification).
      3. Build the circuit with sonata-builder.
      4. Register the circuit in entitycore (unless disabled in the form).
    """

    config: OrganoidCircuitBuildSingleConfig

    def execute(
        self,
        *,
        db_client: Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: str | None = None,  # ruff: ignore[unused-method-argument]
    ) -> None:
        """Run the circuit build (and registration) for this single config."""
        config = self.config
        output_root = Path(config.coordinate_output_root) / _sanitize_name(config.campaign_name)
        component_source_dir = output_root / "component_sources"
        circuit_dir = output_root / "circuit"

        if config.registration.register_in_entitycore and db_client is None:
            err = "Registration requested but no db_client was provided."
            raise ValueError(err)

        L.info("Staging MEModel components under %s", component_source_dir)
        population_refs = stage_components(config, db_client, component_source_dir)

        catalogue_path = component_source_dir / "catalogues" / "entitycore_models.json"
        ads = build_ads_dict(config, population_refs, str(catalogue_path))
        ads_path = output_root / ADS_FILENAME
        output_root.mkdir(parents=True, exist_ok=True)
        ads_path.write_text(json.dumps(ads, indent=2), encoding="utf-8")
        L.info("Wrote ADS spec to %s", ads_path)

        result = build_circuit(
            DesignSpec.from_json(ads_path),
            circuit_dir,
            component_source_dir=component_source_dir,
            options=BuildOptions(
                profile_id=config.initialize.export_profile,
                generate_simulation_config=True,
            ),
        )
        L.info(
            "Built circuit %s: %d nodes, %s",
            result.build_identity,
            result.node_count,
            result.edge_counts,
        )

        # Ship the ADS inside the bundle so the circuit is self-describing.
        shutil.copy2(ads_path, circuit_dir / "provenance" / ADS_FILENAME)

        if config.registration.register_in_entitycore:
            circuit = register_built_circuit(config, db_client, circuit_dir)
            L.info("Circuit registered as entity %s", circuit.id)
