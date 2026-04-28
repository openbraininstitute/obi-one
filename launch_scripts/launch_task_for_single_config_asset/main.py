import argparse
import logging
import os
import sys
from functools import partial

from entitysdk import Client, LocalAssetStore, ProjectContext, models
from entitysdk.types import ActivityStatus
from entitysdk.token_manager import TokenFromFunction
from obi_auth import get_token

from obi_one.core.run_tasks import run_task_type
from obi_one.utils.db_sdk import update_activity_status, finalize_activity

L = logging.getLogger(__name__)


def main() -> int:
    """Script to launch a task for a single configuration asset.

    Example usage.

    python launch_task_for_single_config_asset.py
        --entity_type Simulation
        --entity_id babb299c-782a-41f1-b782-bc4c5da45462
        --execution_activity_type SimulationExecution
        --execution_activity_id b6759d3d-001d-49b3-b57f-84303415fe0a
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
    local_store_prefix = os.getenv("LOCAL_STORE_PREFIX")
    db_client = None

    try:
        parser = argparse.ArgumentParser(
            description="Script to launch a task for a single configuration asset."
        )
        parser.add_argument("--task-type", required=True, help="Task type")
        parser.add_argument("--config_entity_type", required=False, help="EntitySDK entity type as string")
        parser.add_argument("--config_entity_id", required=True, help="Entity ID as string")
        parser.add_argument(
            "--execution_activity_type",
            required=False,
            help="EntitySDK execution activity type as string",
        )
        parser.add_argument(
            "--execution_activity_id", required=False, help="Execution activity ID as string"
        )
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

    try:
        # TODO: Remove once legacy tasks are moved to generic configs/activities
        if args.config_entity_type:
            config_entity_type = getattr(models, args.config_entity_type)
            execution_activity_type = getattr(models, args.execution_activity_type)
        else:
            config_entity_type = models.TaskConfig
            execution_activity_type = models.TaskActivity

        # Get DB client (incl. file mounting)
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
            environment=deployment,
            project_context=project_context,
            token_manager=token_manager,
            local_store=LocalAssetStore(prefix=local_store_prefix),
        )
        update_activity_status(
            client=db_client,
            activity_id=args.execution_activity_id,
            activity_type=execution_activity_type,
            status=ActivityStatus.running,
        )
        run_task_type(
            task_type=args.task_type,
            entity_type=config_entity_type,
            entity_id=args.config_entity_id,
            scan_output_root=args.scan_output_root,
            db_client=db_client,
            entity_cache=args.entity_cache,
            execution_activity_id=args.execution_activity_id,
        )
    except Exception as e:  # noqa: BLE001
        # Catch any error that may occur to make sure that error status is correctly set
        L.exception(f"Error launching task for single configuration asset: {e}")
        finalize_activity(
            client=db_client,
            activity_id=args.execution_activity_id,
            activity_type=execution_activity_type,
            status=ActivityStatus.error,
        )
        return 1

    finalize_activity(
        client=db_client,
        activity_id=args.execution_activity_id,
        activity_type=execution_activity_type,
        status=ActivityStatus.done,
    )

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
