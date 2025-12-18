import argparse
import logging
import os
import sys
from functools import partial

from entitysdk import Client, ProjectContext, models
from entitysdk.token_manager import TokenFromFunction
from obi_auth import get_token

from obi_one.core.exception import OBIONEError
from obi_one.core.run_tasks import run_task_for_single_config_asset

L = logging.getLogger(__name__)


def update_activity_status(
    db_client: Client, activity_type: str, activity_id: str, status: str
) -> None:
    if not db_client:
        return
    if not activity_id:
        L.warning("Status update not possible since no execution activity provided!")
        return

    activity_type_resolved = getattr(models, activity_type)
    status_dict = {"status": status}
    db_client.update_entity(
        entity_type=activity_type_resolved, entity_id=activity_id, attrs_or_entity=status_dict
    )


def main() -> int:
    """Script to launch a task for a single configuration asset.

    Example usage.

    python launch_task_for_single_config_asset.py
        --entity_type Simulation
        --entity_id babb299c-782a-41f1-b782-bc4c5da45462
        --config_asset_id 12eb6209-a4a1-40ad-ae2e-4b5c137e42a8
        --activity_type SimulationExecution
        --activity_id b6759d3d-001d-49b3-b57f-84303415fe0a
        --entity_cache True
        --scan_output_root ./grid_scan
        --virtual_lab_id e6030ed8-a589-4be2-80a6-f975406eb1f6
        --project_id 2720f785-a3a2-4472-969d-19a53891c817

    Environment Variables Required:
        PERSISTENT_TOKEN_ID: Persistent authentication token.
        DEPLOYMENT: Deployment environment.
        LOCAL_STORE_PREFIX: Local asset store for file mounting.
    """
    persistent_token_id = os.getenv("PERSISTENT_TOKEN_ID")
    deployment = os.getenv("DEPLOYMENT")
    db_client = None

    try:
        parser = argparse.ArgumentParser(
            description="Script to launch a task for a single configuration asset."
        )

        parser.add_argument("--entity_type", required=True, help="EntitySDK entity type as string")
        parser.add_argument("--entity_id", required=True, help="Entity ID as string")
        parser.add_argument(
            "--config_asset_id", required=True, help="Configuration Asset ID as string"
        )
        parser.add_argument(
            "--activity_type", required=False, help="EntitySDK execution activity type as string"
        )
        parser.add_argument("--activity_id", required=False, help="Execution activity ID as string")
        parser.add_argument(
            "--entity_cache",
            required=True,
            help="Boolean flag for campaign entity caching.\
                    Check if enabled for particular EntityFromID types.",
        )
        parser.add_argument(
            "--scan_output_root",
            required=True,
            help="scan_output_root as string. The coordinate output root will be relative to this\
                in a directory named using the idx of the single coordinate config.",
        )
        parser.add_argument("--virtual_lab_id", required=True, help="Virtual Lab ID as string")
        parser.add_argument("--project_id", required=True, help="Project ID as string.")

        args = parser.parse_args()

    except ValueError as e:
        L.error(f"Argument parsing error: {e}")
        return 1

    if args.activity_id and not args.activity_type:
        L.error("Execution activity type required!")
        return 1

    try:
        # Get entity type
        entity_type = getattr(models, args.entity_type)

        # Get DB client
        token_manager = TokenFromFunction(
            partial(
                get_token,
                environment=deployment,
                auth_mode="persistent_token",
                persistent_token_id=persistent_token_id,
            ),
        )
        project_context = ProjectContext(
            project_id=args.project_id, virtual_lab_id=args.virtual_lab_id, environment=deployment
        )
        db_client = Client(
            environment=deployment, project_context=project_context, token_manager=token_manager
        )  # TODO: Use local asset store

        # Update activity status
        update_activity_status(db_client, args.activity_type, args.activity_id, "running")

        # Run actual task
        run_task_for_single_config_asset(
            entity_type=entity_type,
            entity_id=args.entity_id,
            config_asset_id=args.config_asset_id,
            scan_output_root=args.scan_output_root,
            db_client=db_client,
            entity_cache=args.entity_cache,
            activity_id=args.activity_id,
        )
    except OBIONEError as e:
        L.error(f"Error launching task for single configuration asset: {e}")
        update_activity_status(db_client, args.activity_type, args.activity_id, "error")
        return 1

    # Task completed without error
    update_activity_status(db_client, args.activity_type, args.activity_id, "done")

    return 0


if __name__ == "__main__":
    sys.exit(main())
