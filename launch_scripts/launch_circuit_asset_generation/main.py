"""Launch script for circuit asset generation task.

Runs on ECS. Stages the circuit and generates additional assets
(compressed circuit, connectivity matrices, stats, images).
Best-effort: failures are logged but do not affect circuit status.

Environment Variables Required:
    PERSISTENT_TOKEN_ID: Persistent authentication token.
    DEPLOYMENT: Deployment environment.
    LOCAL_STORE_PREFIX: Local asset store for file mounting.
"""

import argparse
import logging
import os
import sys
import tempfile
from functools import partial
from pathlib import Path
from uuid import UUID

from entitysdk import Client, LocalAssetStore, ProjectContext, models
from entitysdk.staging.circuit import stage_circuit
from entitysdk.token_manager import TokenFromFunction
from obi_auth import get_token

from obi_one.utils.circuit_registration.generate import generate_additional_circuit_assets

L = logging.getLogger(__name__)


def main() -> int:
    persistent_token_id = os.getenv("PERSISTENT_TOKEN_ID")
    deployment = os.getenv("DEPLOYMENT")
    local_store_prefix = os.getenv("LOCAL_STORE_PREFIX")

    try:
        parser = argparse.ArgumentParser(description="Generate circuit assets.")
        parser.add_argument("--circuit_id", required=True, help="Circuit entity ID")
        parser.add_argument("--virtual_lab_id", required=True, help="Virtual lab ID")
        parser.add_argument("--project_id", required=True, help="Project ID")
        args = parser.parse_args()

        circuit_id = UUID(args.circuit_id)

        token_manager = TokenFromFunction(
            partial(
                get_token,
                environment=deployment,
                auth_mode="persistent_token",
                persistent_token_id=persistent_token_id,
            ),
        )
        project_context = ProjectContext(
            project_id=args.project_id,
            virtual_lab_id=args.virtual_lab_id,
            environment=deployment,
        )
        db_client = Client(
            environment=deployment,
            project_context=project_context,
            token_manager=token_manager,
            local_store=LocalAssetStore(prefix=local_store_prefix),
        )

        circuit = db_client.get_entity(entity_id=circuit_id, entity_type=models.Circuit)

        with tempfile.TemporaryDirectory() as tmp_dir:
            staged_dir = Path(tmp_dir) / "circuit"
            staged_dir.mkdir()
            circuit_config_path = stage_circuit(db_client, model=circuit, output_dir=staged_dir)

            # Determine edge population for matrix extraction
            from obi_one.scientific.library.circuit import Circuit as OBICircuit

            c = OBICircuit(name=circuit.name, path=str(circuit_config_path))
            edge_pop = c.default_edge_population_name if c.sonata_circuit.edges.population_names else None

            generate_additional_circuit_assets(
                circuit_path=circuit_config_path,
                edge_population=edge_pop,
                client=db_client,
                circuit_entity=circuit,
            )

        L.info("Asset generation complete for circuit %s", circuit_id)

    except Exception as e:  # noqa: BLE001
        L.exception("Asset generation failed: %s", e)
        return 1

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
