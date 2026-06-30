"""Module responsible for registering skeletonization outputs in EntitySDK."""

import logging

from entitysdk import Client, models
from entitysdk.models.cell_morphology_protocol import DigitalReconstructionCellMorphologyProtocol
from entitysdk.types import AssetLabel, CellMorphologyProtocolDesign, DerivationType, StainingType

from obi_one.core.exception import OBIONEError
from obi_one.scientific.library.morphology_registration import (
    register_morphology_with_assets_and_metrics,
)
from obi_one.scientific.tasks.skeletonization.constants import LICENSE_LABEL, ROLE_NAME
from obi_one.scientific.tasks.skeletonization.schemas import Metadata, SkeletonizationOutputs

L = logging.getLogger(__name__)


def _get_or_create_protocol(
    client: Client, metadata: Metadata
) -> models.CellMorphologyProtocol | DigitalReconstructionCellMorphologyProtocol:
    """Retrieve or create the cell morphology protocol for skeletonization.

    Args:
        client: Authenticated EntitySDK client.
        metadata: Metadata containing protocol and EM dataset information.

    Returns:
        The existing or newly created protocol entity.

    Raises:
        OBIONEError: If required dataset fields are missing for protocol creation.
    """
    # In case of duplicates take the first in ascending order
    protocol = client.search_entity(
        entity_type=models.CellMorphologyProtocol,
        query={
            "name": metadata.cell_morphology_protocol_name,
            "order_by": "+creation_date",
        },
    ).first()

    if protocol:
        return protocol

    dset = metadata.em_dense_reconstruction_dataset
    msg = f"Creating cell morphology protocol: {metadata.cell_morphology_protocol_name}"
    L.debug(msg)

    if not (dset.tissue_shrinkage or dset.slicing_direction or dset.slicing_thickness):
        msg = (
            f"CellMorphology protocol registration requires from "
            f"EMDenseReconstructionDataset {dset.id} the following fields: "
            "tissue_shrinkage, slicing_direction, sliching_thickness"
        )
        raise OBIONEError(msg)

    return client.register_entity(
        DigitalReconstructionCellMorphologyProtocol(
            name=metadata.cell_morphology_protocol_name,
            description=metadata.cell_morphology_protocol_description,
            protocol_design=CellMorphologyProtocolDesign.electron_microscopy,
            slicing_direction=dset.slicing_direction,
            slicing_thickness=dset.slicing_thickness,  # ty:ignore[invalid-argument-type]
            staining_type=StainingType.other,
            tissue_shrinkage=dset.tissue_shrinkage,
        )
    )


def register_output_resource(
    client: Client, metadata: Metadata, outputs: SkeletonizationOutputs
) -> models.CellMorphology:
    """Register the generated cell morphology and upload associated assets.

    This function:
    - Retrieves required Role and License entities.
    - Creates (if needed) a DigitalReconstructionCellMorphologyProtocol
      based on EM dataset metadata.
    - Registers a new CellMorphology entity via the shared registration service.
    - Creates a Contribution linking the morphology to its creator.
    - Uploads SWC, ASC, and HDF5 morphology files as assets.
    - Uploads the combined H5 morphology (with spines) as an extra asset.
    - Computes and registers morphometric measurements.
    - Attempts to generate and upload a GLB surface mesh.
    - Creates a Derivation linking EMDenseReconstructionDataset to Morphology.

    Args:
        client: Authenticated EntitySDK client used for entity registration.
        metadata: Metadata describing the morphology, protocol, subject,
            brain region, and EM dataset context.
        outputs: Paths to the generated morphology files.

    Returns:
        The registered CellMorphology entity.
    """
    role = client.search_entity(
        entity_type=models.Role,
        query={"name": ROLE_NAME},
    ).one()
    license = client.search_entity(
        entity_type=models.License,
        query={"label": LICENSE_LABEL},
    ).one()

    protocol = _get_or_create_protocol(client, metadata)

    morphology = models.CellMorphology(
        name=metadata.cell_morphology_name,
        description=metadata.cell_morphology_description,
        has_segmented_spines=True,
        cell_morphology_protocol=protocol,  # ty:ignore[invalid-argument-type]
        brain_region=metadata.brain_region,
        subject=metadata.subject,
        license=license,
    )

    morphology_files = {
        ".swc": outputs.swc_morphology_file,
        ".h5": outputs.h5_morphology_file,
        ".asc": outputs.asc_morphology_file,
    }

    extra_assets = {
        AssetLabel.morphology_with_spines: outputs.h5_combined_morphology_file,
    }

    registered_morphology, _measurement, _mesh = register_morphology_with_assets_and_metrics(
        client=client,
        morphology=morphology,
        morphology_files=morphology_files,
        metrics_source_path=outputs.h5_morphology_file,
        generate_mesh=True,
        extra_assets=extra_assets,
    )

    # Create contribution linking morphology to its creator
    client.register_entity(
        entity=models.Contribution(
            entity=registered_morphology,
            role=role,
            agent=registered_morphology.created_by,  # ty:ignore[invalid-argument-type]
        )
    )
    client.register_entity(
        entity=models.Derivation(
            generated=registered_morphology,
            used=metadata.em_dense_reconstruction_dataset,
            derivation_type=DerivationType.em_dense_reconstruction_dataset_cell_morphology,
        )
    )

    L.debug(f"Upload complete for {registered_morphology.id}")
    return registered_morphology
