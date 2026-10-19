import logging
from pathlib import Path

from entitysdk import Client, MultipartUploadTransferConfig, models
from entitysdk.models.asset import Asset
from entitysdk.types import AssetLabel

from obi_one.core.exception import OBIONEError
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.circuit import Circuit

L = logging.getLogger(__name__)


def _asset_label_value(label: object) -> str:
    """Normalize an asset label (enum or str) to its string value."""
    return str(getattr(label, "value", label))


def _assets_with_label(entity: models.Circuit, asset_label: AssetLabel) -> list[Asset]:
    """Return all assets on the entity that match ``asset_label``."""
    target = _asset_label_value(asset_label)
    return [asset for asset in (entity.assets or []) if _asset_label_value(asset.label) == target]


def _delete_assets_with_label(
    client: Client, registered_circuit: models.Circuit, asset_label: AssetLabel
) -> None:
    """Delete all assets with ``asset_label`` on the circuit (in-memory + remote)."""
    for asset in _assets_with_label(registered_circuit, asset_label):
        client.delete_asset(
            entity_id=registered_circuit.id,
            entity_type=models.Circuit,
            asset_id=asset.id,
        )
        L.info("Deleted existing '%s' asset %s", asset_label, asset.id)
        if registered_circuit.assets is not None:
            # Circuit is a frozen model, so the attribute cannot be reassigned; mutate the
            # existing list in place to keep the in-memory assets in sync with the remote state.
            registered_circuit.assets[:] = [
                a for a in registered_circuit.assets if a.id != asset.id
            ]


def _upload_or_replace_file(
    client: Client,
    registered_circuit: models.Circuit,
    *,
    asset_label: AssetLabel,
    file_path: Path,
    file_content_type: str,
    transfer_config: MultipartUploadTransferConfig | None = None,
) -> Asset:
    """Upload a file asset, replacing any existing asset with the same label.

    Uses ``update_asset_file`` (delete + re-upload) when a single existing asset
    is found and no custom transfer config is required. Otherwise deletes any
    matching assets and uploads fresh.
    """
    existing = _assets_with_label(registered_circuit, asset_label)

    if transfer_config is None and len(existing) == 1:
        asset = client.update_asset_file(
            entity_id=registered_circuit.id,
            entity_type=models.Circuit,
            asset_id=existing[0].id,
            file_path=file_path,
            file_content_type=file_content_type,  # ty:ignore[invalid-argument-type]
        )
        L.info("'%s' asset replaced under asset ID %s", asset_label, asset.id)
        return asset

    # Prefer update_asset_file above; when transfer_config is set (e.g. multipart
    # compressed uploads) we delete + upload_file ourselves because
    # update_asset_file does not accept transfer_config.
    if existing:
        _delete_assets_with_label(client, registered_circuit, asset_label)

    asset = client.upload_file(
        entity_id=registered_circuit.id,
        entity_type=models.Circuit,
        file_path=file_path,
        file_content_type=file_content_type,  # ty:ignore[invalid-argument-type]
        asset_label=asset_label,
        transfer_config=transfer_config,
    )
    L.info("'%s' asset uploaded under asset ID %s", asset_label, asset.id)
    return asset


def _upload_or_replace_directory(
    client: Client,
    registered_circuit: models.Circuit,
    *,
    asset_label: AssetLabel,
    name: str,
    paths: dict,
) -> Asset:
    """Upload a directory asset, replacing any existing asset with the same label.

    entitysdk has no ``update_asset_directory``; this mirrors ``update_asset_file``
    by deleting matching assets first, then uploading.
    """
    if _assets_with_label(registered_circuit, asset_label):
        _delete_assets_with_label(client, registered_circuit, asset_label)

    asset = client.upload_directory(
        label=asset_label,
        name=name,
        entity_id=registered_circuit.id,
        entity_type=models.Circuit,
        paths=paths,
    )
    L.info("'%s' asset uploaded under asset ID %s", asset_label, asset.id)
    return asset


def resolve_circuit(
    circuit: Circuit | CircuitFromID,
    *,
    db_client: Client,
    entity_cache: bool,
    cache_root: Path,
    temp_dir: Path,
) -> tuple[Circuit, models.Circuit | None]:
    """Resolve a circuit object into a staged local circuit.

    Handles both local Circuit instances and CircuitFromID references that
    need to be staged from entitycore.

    Args:
        circuit: A Circuit instance (local) or CircuitFromID (remote).
        db_client: The entitycore SDK client.
        entity_cache: If True, stage into a persistent cache directory under
            cache_root; otherwise stage into temp_dir.
        cache_root: Root path for the entity cache (e.g., scan_output_root).
        temp_dir: Temporary directory path to use when entity_cache is False.

    Returns:
        Tuple of (resolved Circuit, circuit entity or None).
    """
    if isinstance(circuit, Circuit):
        L.info("Circuit is a local Circuit instance.")
        return circuit, None

    if isinstance(circuit, CircuitFromID):
        L.info("Circuit is a CircuitFromID instance.")
        circuit_id = circuit.id_str

        if entity_cache:
            L.info("Use entity cache")
            dest_dir = cache_root / "entity_cache" / "sonata_circuit" / circuit_id
        else:
            dest_dir = temp_dir / "sonata_circuit"

        staged_circuit = circuit.stage_circuit(
            db_client=db_client, dest_dir=dest_dir, entity_cache=entity_cache
        )
        circuit_entity = circuit.entity(db_client=db_client)
        return staged_circuit, circuit_entity

    msg = f"Unsupported circuit type: {type(circuit)}"
    raise OBIONEError(msg)
