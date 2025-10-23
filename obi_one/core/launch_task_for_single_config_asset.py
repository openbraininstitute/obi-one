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

    Environment Variables Required:
        PLATFORM_AUTHENTICATION_TOKEN: Your authentication token for the platform.
        LAB_ID: The ID of the virtual lab.
        PROJECT_ID: The ID of the project.
    """
    parser = argparse.ArgumentParser(description="Example script with predefined CLI parameters")

    parser.add_argument("--entity_type", required=True, help="EntitySDK Entity type as string")
    parser.add_argument("--entity_id", required=True, help="Entity ID as string")
    parser.add_argument("--config_asset_id", required=True, help="Configuration Asset ID as string")

    args = parser.parse_args()

    entity_type_str = args.entity_type
    entity_id = args.entity_id
    config_asset_id = args.config_asset_id

    entity_type = getattr(entitysdk.models, entity_type_str)

    token = os.getenv("PLATFORM_AUTHENTICATION_TOKEN")
    lab_id = os.getenv("LAB_ID")
    project_id = os.getenv("PROJECT_ID")

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
