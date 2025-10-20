import logging
import sys

import entitysdk
from entitysdk import Client, ProjectContext

from obi_one.core.run_tasks import run_task_for_single_config_asset

L = logging.getLogger(__name__)

N_ARGS = 7

# python launch_task_for_single_config_asset.py Simulation
#  1569a81e-b578-4c39-a3a9-f9a05f123db9 c9edaedf-e5c0-4643-979c-47375f3160e0 TOKEN LAB_ID PROJECT_ID


def main() -> None:
    if len(sys.argv) == N_ARGS:
        entity_type_str = sys.argv[1]
        entity_id = sys.argv[2]
        config_asset_id = sys.argv[3]
        token = sys.argv[4]
        lab_id = sys.argv[5]
        project_id = sys.argv[6]

        L.info(
            f"Running task for \
                entity type: {entity_type_str}, \
                entity ID: {entity_id}, \
                asset ID: {config_asset_id}"
        )

        entity_type = getattr(entitysdk.models, entity_type_str)

        project_context = ProjectContext(virtual_lab_id=lab_id, project_id=project_id)
        db_client = Client(token_manager=token, project_context=project_context)

        run_task_for_single_config_asset(
            entity_type=entity_type,
            entity_id=entity_id,
            config_asset_id=config_asset_id,
            db_client=db_client,
        )

    else:
        L.info(f"Please provide {N_ARGS} arguments only.")


if __name__ == "__main__":
    main()
