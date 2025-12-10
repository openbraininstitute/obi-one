import argparse
import logging
import os
import sys

import entitysdk
from entitysdk import Client, ProjectContext

from obi_one.core.exception import OBIONEError
from obi_one.core.run_tasks import run_task_for_single_config_asset

L = logging.getLogger(__name__)


def main() -> int:
    """Script to launch a task for a single configuration asset.

    Example usage.

    python launch_task_for_single_config_asset.py
        --entity_type Simulation
        --entity_id babb299c-782a-41f1-b782-bc4c5da45462
        --config_asset_id 12eb6209-a4a1-40ad-ae2e-4b5c137e42a8
        --scan_output_root ./grid_scan
        --entity_cache True
        --entity_core_api_url https://staging.openbraininstitute.org/api/entitycore
        --lab_id e6030ed8-a589-4be2-80a6-f975406eb1f6
        --project_id 2720f785-a3a2-4472-969d-19a53891c817

    Environment Variables Required:
        OBI_AUTHENTICATION_TOKEN: Your authentication token for the platform.
    """
    try:
        parser = argparse.ArgumentParser(
            description="Script to launch a task for a single configuration asset."
        )

        parser.add_argument("--entity_type", required=True, help="EntitySDK Entity type as string")
        parser.add_argument("--entity_id", required=True, help="Entity ID as string")
        parser.add_argument(
            "--config_asset_id", required=True, help="Configuration Asset ID as string"
        )
        parser.add_argument(
            "--scan_output_root",
            required=True,
            help="scan_output_root as string. The coordinate output root will be relative to this\
                in a directory named using the idx of the single coordinate config.",
        )
        parser.add_argument(
            "--entity_cache",
            required=True,
            help="Boolean flag for campaign entity caching.\
                    Check if enabled for particular EntityFromID types.",
        )
        parser.add_argument(
            "--entity_core_api_url", required=True, help="Entity Core API URL as string."
        )
        parser.add_argument("--lab_id", required=True, help="Virtual Lab ID as string")
        parser.add_argument("--project_id", required=True, help="Project ID as string.")

        args = parser.parse_args()

    except ValueError as e:
        L.error(f"Argument parsing error: {e}")
        return 1

    try:
        entity_type_str = args.entity_type
        entity_id = args.entity_id
        config_asset_id = args.config_asset_id
        scan_output_root = args.scan_output_root
        entity_cache = args.entity_cache
        entity_core_api_url = args.entity_core_api_url
        lab_id = args.lab_id
        project_id = args.project_id

        entity_type = getattr(entitysdk.models, entity_type_str)

        token = os.getenv("OBI_AUTHENTICATION_TOKEN")

        project_context = ProjectContext(virtual_lab_id=lab_id, project_id=project_id)
        db_client = Client(
            api_url=entity_core_api_url,
            token_manager=token,
            project_context=project_context,
        )

        run_task_for_single_config_asset(
            entity_type=entity_type,
            entity_id=entity_id,
            config_asset_id=config_asset_id,
            scan_output_root=scan_output_root,
            db_client=db_client,
            entity_cache=entity_cache,
        )
    except OBIONEError as e:
        L.error(f"Error launching task for single configuration asset: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
