"""Selective staging of files out of a circuit's ``sonata_circuit`` directory asset.

Staging a whole circuit is not affordable everywhere. The obi-one web service runs campaign
generation in-process with only a small tmpfs to write to, and a circuit's edge files can be
orders of magnitude larger than everything else combined. These helpers fetch just the files a
caller actually reads.

Public circuits are cheap either way, because entitysdk symlinks them out of the mounted asset
store. It is private-project circuits, which have no mount and therefore have to be downloaded,
that make the distinction matter.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import libsonata
from entitysdk.models.circuit import Circuit
from entitysdk.types import FetchFileStrategy

if TYPE_CHECKING:
    from uuid import UUID

    import entitysdk.client
    from entitysdk.models.asset import Asset

L = logging.getLogger(__name__)

CIRCUIT_CONFIG_FILE_NAME = "circuit_config.json"

# Matches what ``entitysdk.staging.circuit.stage_circuit`` selects, so the partial and full
# staging paths always operate on the same asset.
SONATA_CIRCUIT_ASSET_SELECTION = {
    "content_type": "application/vnd.directory",
    "is_directory": True,
    "label": "sonata_circuit",
}


def _asset_path_in(declared_path: str, dest_dir: Path) -> str:
    """The path of a file declared in the circuit config, relative to the staging directory.

    ``expanded_json`` reflects the config's manifest. With the usual ``"$BASE_DIR": "./"`` the
    declared paths are already relative to the config, which is exactly what the asset API
    wants; an absolute ``$BASE_DIR`` yields absolute paths that have to be made relative again.

    Raises:
        ValueError: If an absolute declared path falls outside the staging directory, in which
            case it does not correspond to a file inside the asset and cannot be fetched.
    """
    path = Path(declared_path)

    if not path.is_absolute():
        return str(path)

    try:
        return str(path.resolve().relative_to(dest_dir))
    except ValueError as err:
        msg = (
            f"Circuit config declares '{declared_path}', which is outside the staging directory"
            f" '{dest_dir}'. Only files inside the sonata_circuit asset can be staged."
        )
        raise ValueError(msg) from err


def _files_to_stage(config: dict, dest_dir: Path) -> list[str]:
    """The node sets file, if the config declares one, and every population's nodes file.

    Deduplicated because several node populations can be backed by one file, and staging the
    same path twice would fail on the symlink.
    """
    declared = []

    # Omitted from expanded_json entirely when the config does not declare one.
    if node_sets_file := config.get("node_sets_file"):
        declared.append(node_sets_file)

    declared.extend(
        entry["nodes_file"] for entry in config.get("networks", {}).get("nodes", []) or []
    )

    asset_paths = []
    for declared_path in declared:
        asset_path = _asset_path_in(declared_path, dest_dir)
        if asset_path not in asset_paths:
            asset_paths.append(asset_path)
    return asset_paths


def stage_circuit_nodes(
    db_client: entitysdk.client.Client,
    *,
    entity_id: UUID,
    asset: Asset,
    dest_dir: Path,
) -> Path:
    """Stages the circuit config, node sets and every population's nodes file.

    Edge files, morphologies and mechanisms are left alone, so this is only usable by callers
    that read node properties and nothing else.

    Returns:
        Path to the staged ``circuit_config.json``.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    config_path = dest_dir / CIRCUIT_CONFIG_FILE_NAME
    db_client.fetch_file(
        entity_id=entity_id,
        entity_type=Circuit,
        asset_id=asset,
        output_path=config_path,
        asset_path=Path(CIRCUIT_CONFIG_FILE_NAME),
        # Copied rather than symlinked so that $BASE_DIR resolves to dest_dir. A symlink would
        # make it resolve into the asset store, whose sibling paths point at the files this
        # function deliberately does not stage.
        strategy=FetchFileStrategy.copy_or_download,
    )

    # libsonata resolves the paths in a config without opening the files they name, so the
    # config can be read to decide what else is worth fetching while it is the only file here.
    config = json.loads(libsonata.CircuitConfig.from_file(str(config_path)).expanded_json)

    for asset_path in _files_to_stage(config, dest_dir):
        L.debug("Staging '%s' for circuit %s", asset_path, entity_id)
        db_client.fetch_file(
            entity_id=entity_id,
            entity_type=Circuit,
            asset_id=asset,
            output_path=dest_dir / asset_path,
            asset_path=Path(asset_path),
        )

    return config_path
