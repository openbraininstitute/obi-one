# ruff: file-ignore[implicit-namespace-package]
"""Launch script for circuit validation task.

Runs on the launch-system with image ``python_3_12_openmpi5_neuron9_neurodamus``.
Stages the circuit, compiles MOD files, runs snap validation, and updates the
circuit entity's lifecycle status accordingly.

Environment Variables Required:
    PERSISTENT_TOKEN_ID: Persistent authentication token.
    DEPLOYMENT: Deployment environment.
    LOCAL_STORE_PREFIX: Local asset store for file mounting.
"""

import argparse
import logging
import os
import sys
from functools import partial
from uuid import UUID

from entitysdk import Client, LocalAssetStore, ProjectContext, models
from entitysdk.token_manager import TokenFromFunction
from obi_auth import get_token

from obi_one.db_sdk.registration.circuit.lifecycle import is_validation_allowed
from obi_one.scientific.tasks.circuit_validation.task import (
    _update_lifecycle_status,  # ruff: ignore[import-private-name]
    is_circuit_customization,
    run_circuit_validation,
)

L = logging.getLogger(__name__)


def main() -> int:
    persistent_token_id = os.getenv("PERSISTENT_TOKEN_ID")
    deployment = os.getenv("DEPLOYMENT")
    local_store_prefix = os.getenv("LOCAL_STORE_PREFIX")
    db_client = None
    circuit_id = None

    try:  # ruff: ignore[too-many-statements-in-try-clause]
        parser = argparse.ArgumentParser(description="Validate a customized circuit.")
        parser.add_argument("--circuit_id", required=True, help="Customized circuit entity ID")
        parser.add_argument("--virtual_lab_id", required=True, help="Virtual lab ID")
        parser.add_argument("--project_id", required=True, help="Project ID")
        parser.add_argument(
            "--force",
            type=lambda value: str(value).lower() == "true",
            default=False,
            help="Validate even if the circuit is not in draft status",
        )
        args = parser.parse_args()

        circuit_id = UUID(args.circuit_id)

        # Use direct token if available (local testing), otherwise persistent token auth
        direct_token = os.getenv("ENTITYCORE_ACCESS_TOKEN")
        if direct_token:
            token_manager = TokenFromFunction(lambda: direct_token)
        else:
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
        if not is_validation_allowed(lifecycle_status=circuit.lifecycle_status, force=args.force):
            L.info(
                "Skipping validation for circuit %s: lifecycle_status=%s "
                "(expected draft; pass --force true to overwrite)",
                circuit_id,
                circuit.lifecycle_status,
            )
            return 0

        result = run_circuit_validation(
            db_client=db_client,
            circuit_id=circuit_id,
            is_customization=is_circuit_customization(circuit),
        )
        L.info("Validation result: valid=%s, errors=%d", result["valid"], len(result["errors"]))

    except Exception as e:  # ruff: ignore[blind-except]
        L.exception("Circuit validation failed with unexpected error: %s", e)
        if db_client is not None and circuit_id is not None:
            _update_lifecycle_status(db_client, circuit_id, "disqualified")
        return 1

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
