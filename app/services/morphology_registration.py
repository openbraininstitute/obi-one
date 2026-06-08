"""Service for registering cell morphologies with assets and morphometrics.

This module provides the shared logic for:
- Registering a CellMorphology entity in EntityCore.
- Uploading morphology file assets (SWC, H5, ASC).
- Computing and registering morphometric measurements.
- Optionally generating and uploading a GLB surface mesh.

It is used by both the skeletonization task and the HTTP endpoint for
morphology upload with metrics calculation.
"""

import logging
import pathlib
from pathlib import Path
from uuid import UUID

from entitysdk import Client
from entitysdk.models import CellMorphology, MeasurementAnnotation
from entitysdk.models.asset import Asset
from entitysdk.models.measurement_annotation import MeasurementKind
from entitysdk.types import AssetLabel, ContentType, MeasurableEntity

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
    """Upload a morphology file as an asset on the given entity.

    Args:
        client: Authenticated EntitySDK client.
        entity_id: ID of the CellMorphology entity to attach the asset to.
        file_path: Local path to the morphology file.
        asset_label: Label for the asset (defaults to 'morphology').

    Returns:
        The created Asset.
    """
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
    """Upload morphology content (bytes) as an asset on the given entity.

    Args:
        client: Authenticated EntitySDK client.
        entity_id: ID of the CellMorphology entity to attach the asset to.
        file_name: Filename (used to derive the content type from extension).
        content: Raw file bytes.
        asset_label: Label for the asset (defaults to 'morphology').

    Returns:
        The created Asset.
    """
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


def compute_morphometrics(morphology_path: str | Path) -> list[MeasurementKind]:
    """Compute morphometric measurements for a morphology file.

    Uses the NeuroM-based analysis pipeline with the standard template.

    Args:
        morphology_path: Path to the morphology file (SWC, H5, or ASC).

    Returns:
        List of MeasurementKind results (only those with non-null values).
    """
    import neurom as nm  # noqa: PLC0415

    import app.endpoints.useful_functions.useful_functions as uf  # noqa: PLC0415
    from app.endpoints.morphology_metrics_calculation import (  # noqa: PLC0415
        _get_analysis_dict,
        _get_template,
    )

    neuron = nm.load_morphology(str(morphology_path))
    results_dict = uf.build_results_dict(_get_analysis_dict(), neuron)
    filled = uf.fill_json(_get_template(), results_dict, entity_id="temp_id")
    measurement_kinds = filled["data"][0]["measurement_kinds"]
    return [
        mk
        for mk in measurement_kinds
        if any(mi.get("value") is not None for mi in mk.get("measurement_items", []))
    ]


def register_morphometrics(
    client: Client,
    entity_id: UUID,
    measurement_kinds: list[MeasurementKind],
) -> MeasurementAnnotation:
    """Register morphometric measurements for a CellMorphology entity.

    Args:
        client: Authenticated EntitySDK client.
        entity_id: ID of the CellMorphology entity.
        measurement_kinds: List of computed measurement kinds.

    Returns:
        The registered MeasurementAnnotation entity.
    """
    measurement_annotation = MeasurementAnnotation(
        entity_id=entity_id,
        entity_type=MeasurableEntity.cell_morphology,
        measurement_kinds=measurement_kinds,
    )
    return client.register_entity(entity=measurement_annotation)


def try_generate_and_upload_mesh(
    client: Client,
    entity_id: UUID,
    swc_path: Path | None = None,
    swc_bytes: bytes | None = None,
) -> Asset | None:
    """Attempt to generate a GLB mesh from SWC data and upload it.

    Silently returns None if meshing dependencies are not installed or
    if meshing fails. This is a best-effort operation.

    Args:
        client: Authenticated EntitySDK client.
        entity_id: ID of the CellMorphology entity.
        swc_path: Path to an SWC file. Mutually exclusive with swc_bytes.
        swc_bytes: Raw SWC content. Mutually exclusive with swc_path.

    Returns:
        The uploaded Asset, or None if meshing was skipped or failed.
    """
    from app.endpoints.convert_morphology_to_registered_mesh import (  # noqa: PLC0415
        HAS_MESHING,
        mesh_and_register,
    )

    if not HAS_MESHING:
        L.debug("Meshing dependencies not available, skipping GLB generation")
        return None

    if swc_path and not swc_bytes:
        swc_bytes = swc_path.read_bytes()
    elif not swc_bytes:
        L.debug("No SWC data provided for mesh generation, skipping")
        return None

    try:
        return mesh_and_register(client, entity_id, swc_bytes)
    except Exception:  # noqa: BLE001
        L.warning(f"GLB mesh generation failed for entity {entity_id}", exc_info=True)
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
    """Register a CellMorphology entity, upload assets, compute metrics, and optionally mesh.

    This is the high-level entry point for morphology registration that consolidates:
    - Entity creation
    - Standard morphology file uploads (SWC, H5, ASC)
    - Additional custom assets (e.g. morphology_with_spines)
    - Morphometric computation and registration
    - GLB mesh generation and upload

    Args:
        client: Authenticated EntitySDK client.
        morphology: CellMorphology instance to register (not yet persisted).
        morphology_files: Dict mapping file extension (e.g. '.swc', '.h5', '.asc')
            to local file paths to upload as standard morphology assets.
        metrics_source_path: Path to the morphology file to use for metrics
            computation. If None, uses the first H5 or SWC file from morphology_files.
        generate_mesh: Whether to attempt GLB mesh generation from SWC.
        extra_assets: Optional dict mapping AssetLabel to file paths for
            additional assets (e.g. morphology_with_spines).

    Returns:
        Tuple of:
        - The registered CellMorphology entity.
        - The MeasurementAnnotation (or None if metrics computation failed).
        - The mesh Asset (or None if mesh generation was skipped or failed).
    """
    # 1. Register the entity
    registered_morphology = client.register_entity(entity=morphology)
    entity_id = registered_morphology.id

    # 2. Upload standard morphology files
    for file_path in morphology_files.values():
        upload_morphology_file(client, entity_id, file_path)

    # 3. Upload extra assets (e.g. combined morphology with spines)
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

    # 4. Compute and register morphometrics
    measurement_annotation = None
    analysis_path = metrics_source_path
    if analysis_path is None:
        # Prefer H5, fall back to SWC
        analysis_path = morphology_files.get(".h5") or morphology_files.get(".swc")

    if analysis_path and analysis_path.exists():
        try:
            measurement_kinds = compute_morphometrics(analysis_path)
            measurement_annotation = register_morphometrics(client, entity_id, measurement_kinds)
        except Exception:  # noqa: BLE001
            L.warning(
                f"Morphometrics computation failed for {entity_id}",
                exc_info=True,
            )

    # 5. Optionally generate and upload GLB mesh
    mesh_asset = None
    if generate_mesh:
        swc_path = morphology_files.get(".swc")
        mesh_asset = try_generate_and_upload_mesh(client, entity_id, swc_path=swc_path)

    return registered_morphology, measurement_annotation, mesh_asset
