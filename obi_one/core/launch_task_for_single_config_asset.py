import logging
import sys

import entitysdk

from obi_one.core.run_tasks import run_task_for_single_config_asset

L = logging.getLogger(__name__)

N_ARGS = 4

# python launch_task_for_single_config_asset.py "Simulation" "1569a81e-b578-4c39-a3a9-f9a05f123db9" "c9edaedf-e5c0-4643-979c-47375f3160e0"

def main() -> None:
    if len(sys.argv) == N_ARGS:
        entity_type, entity_id, config_asset_id = sys.argv[1], sys.argv[2], sys.argv[3]

        L.info(
            f"Running task for \
                entity type: {entity_type}, \
                entity ID: {entity_id}, \
                asset ID: {config_asset_id}"
        )

        db_client = [HOW DO WE INITIALIZE CLIENT? PASSING TOKEN, LAB ID, PROJECT ID AS PARAMETERS?]

        run_task_for_single_config_asset(
            entity_type=getattr(entitysdk.models, entity_type),
            entity_id=entity_id,
            config_asset_id=config_asset_id,
            db_client=db_client
        )

    else:
        L.info(f"Please provide {N_ARGS} arguments only.")

if __name__ == "__main__":
    main()