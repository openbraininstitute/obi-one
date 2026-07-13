"""Register cell morphologies with assets, morphometrics, and optional mesh."""

import logging
import pathlib
from pathlib import Path
from typing import Any
from uuid import UUID

from entitysdk import Client
from entitysdk.models import CellMorphology, MeasurementAnnotation
from entitysdk.models.asset import Asset
from entitysdk.models.measurement_annotation import MeasurementKind
from entitysdk.types import AssetLabel, ContentType, MeasurableEntity

from obi_one.scientific.library import morphology_mesh
from obi_one.scientific.library.morphology_measurement_annotation import compute_morphometrics

L = logging.getLogger(__name__)

EXTENSION_CONTENT_TYPE_MAP: dict[str, ContentType] = {
    ".asc": ContentType.application_asc,
    ".swc": ContentType.application_swc,
    ".h5": ContentType.application_x_hdf5,
}


def _get_content_type(file_extension: str) -> ContentType:
    content_type = EXTENSION_CONTENT_TYPE_MAP.get(file_extension.lower())
    if not content_type:
        error_msg = f"Unsupported file extension: '{file_extension}'."
        raise ValueError(error_msg)
    return content_type


def upload_morphology_file(
    client: Client,
    entity_id: UUID,
    file_path: Path,
    *,
    asset_label: AssetLabel = AssetLabel.morphology,
) -> Asset:
    """Upload a morphology file as an asset on the given entity."""
    content_type = _get_content_type(file_path.suffix)
    return client.upload_file(
        entity_id=entity_id,
        entity_type=CellMorphology,
        file_path=file_path,
        file_content_type=content_type,
        asset_label=asset_label,
    )


def upload_morphology_content(
    client: Client,
    entity_id: UUID,
    file_name: str,
    content: bytes,
    *,
    asset_label: AssetLabel = AssetLabel.morphology,
) -> Asset:
    """Upload morphology content (bytes) as an asset on the given entity."""
    file_extension = pathlib.Path(file_name).suffix
    content_type = _get_content_type(file_extension)
    return client.upload_content(
        entity_id=entity_id,
        entity_type=CellMorphology,
        file_content=content,
        file_name=file_name,
        file_content_type=content_type,
        asset_label=asset_label,
    )


def register_morphometrics(
    client: Client,
    entity_id: UUID,
    measurement_kinds: list[dict[str, Any]],
) -> MeasurementAnnotation:
    """Register morphometric measurements for a CellMorphology entity."""
    measurement_annotation = MeasurementAnnotation(
        entity_id=entity_id,
        entity_type=MeasurableEntity.cell_morphology,
        measurement_kinds=[
            MeasurementKind.model_validate(measurement_kind)
            for measurement_kind in measurement_kinds
        ],
    )
    return client.register_entity(entity=measurement_annotation)


def try_generate_and_upload_mesh(
    client: Client,
    entity_id: UUID,
    swc_path: Path | None = None,
    swc_bytes: bytes | None = None,
) -> Asset | None:
    """Attempt to generate a GLB mesh from SWC data and upload it."""
    if not morphology_mesh.HAS_MESHING:
        L.debug("Meshing dependencies not available, skipping GLB generation")
        return None

    if swc_path and not swc_bytes:
        swc_bytes = swc_path.read_bytes()
    elif not swc_bytes:
        L.debug("No SWC data provided for mesh generation, skipping")
        return None

    try:
        return morphology_mesh.mesh_and_upload(client, entity_id, swc_bytes)
    except Exception:  # noqa: BLE001
        L.warning("GLB mesh generation failed for entity %s", entity_id, exc_info=True)
        return None


def register_morphology_with_assets_and_metrics(
    client: Client,
    morphology: CellMorphology,
    morphology_files: dict[str, Path],
    *,
    metrics_source_path: Path | None = None,
    generate_mesh: bool = True,
    extra_assets: dict[AssetLabel, Path] | None = None,
) -> tuple[CellMorphology, MeasurementAnnotation | None, Asset | None]:
    """Register a CellMorphology entity, upload assets, compute metrics, and optionally mesh."""
    registered_morphology = client.register_entity(entity=morphology)
    entity_id = registered_morphology.id
    if entity_id is None:
        msg = "Registered morphology entity has no id"
        raise RuntimeError(msg)

    for file_path in morphology_files.values():
        upload_morphology_file(client, entity_id, file_path)

    if extra_assets:
        for asset_label, file_path in extra_assets.items():
            content_type = _get_content_type(file_path.suffix)
            client.upload_file(
                entity_id=entity_id,
                entity_type=CellMorphology,
                file_path=file_path,
                file_content_type=content_type,
                asset_label=asset_label,
            )

    measurement_annotation = None
    analysis_path = metrics_source_path
    if analysis_path is None:
        analysis_path = morphology_files.get(".h5") or morphology_files.get(".swc")

    if analysis_path and analysis_path.exists():
        try:
            measurement_kinds = compute_morphometrics(analysis_path)
            measurement_annotation = register_morphometrics(client, entity_id, measurement_kinds)
        except Exception:  # noqa: BLE001
            L.warning("Morphometrics computation failed for %s", entity_id, exc_info=True)

    mesh_asset = None
    if generate_mesh:
        swc_path = morphology_files.get(".swc")
        mesh_asset = try_generate_and_upload_mesh(client, entity_id, swc_path=swc_path)

    return registered_morphology, measurement_annotation, mesh_asset
