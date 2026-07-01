"""Launch script for circuit validation task.

Runs on ECS. Stages the merged circuit, compiles MOD files, runs snap validation,
and updates the circuit entity's readiness_status accordingly.

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
from pathlib import Path
from uuid import UUID

# Use pre-installed packages from the obi-one Docker image's venv.
# The wrapper creates a bare venv, but we need NEURON, bluecellulab, etc.
_IMAGE_SITE_PACKAGES = "/code/.venv/lib/python3.12/site-packages"
if os.path.isdir(_IMAGE_SITE_PACKAGES):
    sys.path.append(_IMAGE_SITE_PACKAGES)

# Add repo root to sys.path for obi_one imports (not pip-installed, loaded from source).
# This takes priority over image packages so we run the latest code from the branch.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from entitysdk import Client, LocalAssetStore, ProjectContext, models
from entitysdk.token_manager import TokenFromFunction
from obi_auth import get_token

from obi_one.scientific.tasks.circuit_validation.task import (
    _update_lifecycle_status,
    run_circuit_validation,
)

L = logging.getLogger(__name__)


def main() -> int:
    persistent_token_id = os.getenv("PERSISTENT_TOKEN_ID")
    deployment = os.getenv("DEPLOYMENT")
    local_store_prefix = os.getenv("LOCAL_STORE_PREFIX")
    db_client = None
    circuit_id = None

    try:
        parser = argparse.ArgumentParser(description="Validate a customized circuit.")
        parser.add_argument("--circuit_id", required=True, help="Customized circuit entity ID")
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

        result = run_circuit_validation(db_client=db_client, circuit_id=circuit_id)
        L.info("Validation result: valid=%s, errors=%d", result["valid"], len(result["errors"]))

    except Exception as e:  # noqa: BLE001
        L.exception("Circuit validation failed with unexpected error: %s", e)
        if db_client is not None and circuit_id is not None:
            _update_lifecycle_status(db_client, circuit_id, "failed")
        return 1

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
