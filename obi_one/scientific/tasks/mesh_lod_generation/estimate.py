from uuid import UUID

import entitysdk


def estimate_mesh_lod_generation_count(
    *,
    db_client: entitysdk.Client,
    config_id: UUID,
) -> int:
    _ = db_client
    _ = config_id
    return 1
