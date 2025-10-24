import argparse
import logging
import os

import entitysdk
from entitysdk import Client, ProjectContext

from obi_one.core.run_tasks import run_task_for_single_config_asset

L = logging.getLogger(__name__)


def main() -> None:
    """Script to launch a task for a single configuration asset.

    Example usage.

    python launch_task_for_single_config_asset.py
        --entity_type Simulation
        --entity_id 1569a81e-b578-4c39-a3a9-f9a05f123db9
        --config_asset_id c9edaedf-e5c0-4643-979c-47375f3160e0
        --lab_id 123e4567-e89b-12d3-a456-426614174000
        --project_id 987e6543-e21b-12d3-a456-426614174999

    Environment Variables Required:
        OBI_AUTHENTICATION_TOKEN: Your authentication token for the platform.
    """
    parser = argparse.ArgumentParser(
        description="Script to launch a task for a single configuration asset."
    )

    parser.add_argument("--entity_type", required=True, help="EntitySDK Entity type as string")
    parser.add_argument("--entity_id", required=True, help="Entity ID as string")
    parser.add_argument("--config_asset_id", required=True, help="Configuration Asset ID as string")
    parser.add_argument("--lab_id", required=True, help="Virtual Lab ID as string")
    parser.add_argument("--project_id", required=True, help="Project ID as string.")

    args = parser.parse_args()

    entity_type_str = args.entity_type
    entity_id = args.entity_id
    config_asset_id = args.config_asset_id
    lab_id = args.lab_id
    project_id = args.project_id

    entity_type = getattr(entitysdk.models, entity_type_str)

    token = os.getenv("OBI_AUTHENTICATION_TOKEN")

    project_context = ProjectContext(virtual_lab_id=lab_id, project_id=project_id)
    db_client = Client(token_manager=token, project_context=project_context)

    run_task_for_single_config_asset(
        entity_type=entity_type,
        entity_id=entity_id,
        config_asset_id=config_asset_id,
        db_client=db_client,
    )


if __name__ == "__main__":
    main()
