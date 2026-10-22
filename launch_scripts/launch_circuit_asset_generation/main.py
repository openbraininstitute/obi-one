"""Launch script for circuit asset generation task.

Runs on ECS. Stages the circuit and generates the compressed circuit, connectivity
matrices, connectivity plots, the overview / sim-designer images and, past single scale,
the morphology pack. Any image the user uploaded at registration time is already attached
and is left untouched (skipped rather than overwritten). Where the morphology pack is the
only asset missing, only the files it reads are staged. Best-effort: failures are logged
but do not affect circuit status.

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
from entitysdk.types import AssetLabel
from obi_auth import get_token
from obi_auth.typedef import AuthMode, DeploymentEnvironment

from obi_one.db_sdk.registration.circuit.generate import (
    generate_additional_circuit_assets,
    generate_morphology_pack_asset,
    missing_assets,
)
from obi_one.scientific.library.circuit import Circuit as OBICircuit
from obi_one.scientific.library.morphology_pack.staging import stage_morphology_pack_inputs

L = logging.getLogger(__name__)


def main() -> int:
    persistent_token_id = os.getenv("PERSISTENT_TOKEN_ID")
    deployment = os.getenv("DEPLOYMENT")
    local_store_prefix = os.getenv("LOCAL_STORE_PREFIX")

    parser = argparse.ArgumentParser(description="Generate circuit assets.")
    parser.add_argument("--circuit_id", required=True, help="Circuit entity ID")
    parser.add_argument("--virtual_lab_id", required=True, help="Virtual lab ID")
    parser.add_argument("--project_id", required=True, help="Project ID")
    parser.add_argument(
        "--force",
        type=lambda value: str(value).lower() == "true",
        default=False,
        help="Regenerate compressed archive even if it already exists",
    )

    try:  # ruff: ignore[too-many-statements-in-try-clause]
        args = parser.parse_args()

        token_manager = TokenFromFunction(
            partial(
                get_token,
                environment=DeploymentEnvironment(deployment),
                auth_mode=AuthMode.persistent_token,
                persistent_token_id=persistent_token_id,
            ),
        )
        project_context = ProjectContext(
            project_id=args.project_id,
            virtual_lab_id=args.virtual_lab_id,
        )
        db_client = Client(
            environment=deployment,
            project_context=project_context,
            token_manager=token_manager,
            local_store=None
            if local_store_prefix is None
            else LocalAssetStore(prefix=Path(local_store_prefix)),
        )

        circuit = db_client.get_entity(entity_id=UUID(args.circuit_id), entity_type=models.Circuit)

        with tempfile.TemporaryDirectory() as tmp_dir:
            staged_dir = Path(tmp_dir) / "circuit"
            staged_dir.mkdir()

            # The pack reads the config, the nodes and the morphologies alone, so the edges,
            # downloaded for a private circuit, are left out when it is all that is missing.
            if not args.force and missing_assets(circuit) == {AssetLabel.circuit_morphology_pack}:
                circuit_config_path = stage_morphology_pack_inputs(db_client, circuit, staged_dir)
                generate_morphology_pack_asset(
                    circuit_path=circuit_config_path,
                    output_dir=Path(tmp_dir) / "morphology_pack",
                    client=db_client,
                    circuit_entity=circuit,
                )
            else:
                circuit_config_path = stage_circuit(db_client, model=circuit, output_dir=staged_dir)

                # Determine edge population for matrix extraction
                c = OBICircuit(name=str(circuit.name), path=str(circuit_config_path))
                edge_pop = (
                    c.default_edge_population_name
                    if c.sonata_circuit.edges.population_names
                    else None
                )

                generate_additional_circuit_assets(
                    circuit_path=circuit_config_path,
                    edge_population=edge_pop,
                    client=db_client,
                    circuit_entity=circuit,
                    force=args.force,
                    include_overview_images=True,
                )

        L.info("Asset generation complete for circuit %s", UUID(args.circuit_id))

    except Exception as e:  # ruff: ignore[blind-except]
        L.exception("Asset generation failed: %s", e)
        return 1

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
