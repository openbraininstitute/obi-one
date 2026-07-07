"""Launch script for mesh LOD generation task.

Runs on the launch-system. Builds the MeshLodGenerationSingleConfig directly
from CLI arguments and generates LOD assets for the given EMCellMesh entity.
Best-effort: failures are logged but the process exit code reflects success.

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

import httpx
from entitysdk import Client, LocalAssetStore, ProjectContext
from entitysdk.token_manager import TokenFromFunction
from obi_auth import get_token

from obi_one.scientific.tasks.mesh_lod_generation.config import MeshLodGenerationSingleConfig
from obi_one.scientific.tasks.mesh_lod_generation.task import MeshLODGenerationTask

L = logging.getLogger(__name__)

HTTP_TIMEOUT = httpx.Timeout(connect=15.0, read=900.0, write=900.0, pool=15.0)


def main() -> int:
    persistent_token_id = os.getenv("PERSISTENT_TOKEN_ID")
    deployment = os.getenv("DEPLOYMENT")
    local_store_prefix = os.getenv("LOCAL_STORE_PREFIX")

    try:
        parser = argparse.ArgumentParser(description="Generate LOD meshes for an EMCellMesh asset.")
        parser.add_argument("--entity_id", required=True, help="EMCellMesh entity ID")
        parser.add_argument("--mesh_asset_id", required=True, help="Source mesh asset ID")
        parser.add_argument("--mesh_format", required=True, help="Source mesh format")
        parser.add_argument("--virtual_lab_id", required=True, help="Virtual lab ID")
        parser.add_argument("--project_id", required=True, help="Project ID")
        args = parser.parse_args()

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
            http_client=httpx.Client(timeout=HTTP_TIMEOUT),
        )

        config = MeshLodGenerationSingleConfig(
            entity_id=UUID(args.entity_id),
            mesh_asset_id=UUID(args.mesh_asset_id),
            mesh_format=args.mesh_format,
        )
        task = MeshLODGenerationTask(config=config, client=db_client)
        task.execute(db_client=db_client)

        L.info("LOD generation complete for entity %s", args.entity_id)

    except Exception as e:  # noqa: BLE001
        L.exception("Mesh LOD generation failed: %s", e)
        return 1

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
