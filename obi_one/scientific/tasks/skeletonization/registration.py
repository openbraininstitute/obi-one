"""Module responsible for registering skeletonization outputs in EntitySDK."""

import logging

from entitysdk import Client, models
from entitysdk.models.cell_morphology_protocol import DigitalReconstructionCellMorphologyProtocol
from entitysdk.types import AssetLabel, CellMorphologyProtocolDesign, ContentType, StainingType

from obi_one.core.exception import OBIONEError
from obi_one.scientific.tasks.skeletonization.constants import LICENSE_LABEL, ROLE_NAME
from obi_one.scientific.tasks.skeletonization.schemas import Metadata, SkeletonizationOutputs

L = logging.getLogger(__name__)


def register_output_resource(
    client: Client, metadata: Metadata, outputs: SkeletonizationOutputs
) -> models.CellMorphology:
    """Register the generated cell morphology and upload associated assets.

    This function:
    - Retrieves required Role and License entities.
    - Creates (if needed) a DigitalReconstructionCellMorphologyProtocol
      based on EM dataset metadata.
    - Registers a new CellMorphology entity.
    - Creates a Contribution linking the morphology to its creator.
    - Uploads SWC, ASC, and HDF5 morphology files as assets.

    Args:
        client: Authenticated EntitySDK client used for entity registration.
        metadata: Metadata describing the morphology, protocol, subject,
            brain region, and EM dataset context.
        outputs: Paths to the generated morphology files.

    Returns:
        The registered CellMorphology entity. Note that uploaded assets
        are not reflected on the returned instance unless it is re-fetched.
    """
    role = client.search_entity(
        entity_type=models.Role,
        query={"name": ROLE_NAME},
    ).one()
    license = client.search_entity(
        entity_type=models.License,
        query={"label": LICENSE_LABEL},
    ).one()

    # Create a cell morphology protocol if there are enough details
    protocol = None
    dset = metadata.em_dense_reconstruction_dataset

    # in case of duplicates take the first in ascending order
    protocol = client.search_entity(
        entity_type=models.CellMorphologyProtocol,
        query={
            "name": metadata.cell_morphology_protocol_name,
            "order_by": "+creation_date",
        },
    ).first()
    if not protocol:
        msg = f"Creating cell morphology protocol: {metadata.cell_morphology_protocol_name}"
        L.debug(msg)
        if not (dset.tissue_shrinkage or dset.slicing_direction or dset.slicing_thickness):
            msg = (
                f"CellMorphology protocol registration requires from "
                f"EMDenseReconstructionDataset {dset.id} the following fields: "
                "tissue_shrinkage, slicing_direction, sliching_thickness"
            )
            raise OBIONEError(msg)
        protocol = client.register_entity(
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
    morphology = client.register_entity(
        models.CellMorphology(
            name=metadata.cell_morphology_name,
            description=metadata.cell_morphology_description,
            has_segmented_spines=True,
            cell_morphology_protocol=protocol,  # ty:ignore[invalid-argument-type]
            brain_region=metadata.brain_region,
            subject=metadata.subject,
            license=license,
        )
    )
    client.register_entity(
        entity=models.Contribution(
            entity=morphology,
            role=role,
            agent=morphology.created_by,  # ty:ignore[invalid-argument-type]
        )
    )
    client.upload_file(
        entity_id=morphology.id,  # ty:ignore[invalid-argument-type]
        entity_type=models.CellMorphology,
        file_path=outputs.swc_morphology_file,
        file_content_type=ContentType.application_swc,
        asset_label=AssetLabel.morphology,
    )
    client.upload_file(
        entity_id=morphology.id,  # ty:ignore[invalid-argument-type]
        entity_type=models.CellMorphology,
        file_path=outputs.asc_morphology_file,
        file_content_type=ContentType.application_asc,
        asset_label=AssetLabel.morphology,
    )
    client.upload_file(
        entity_id=morphology.id,  # ty:ignore[invalid-argument-type]
        entity_type=models.CellMorphology,
        file_path=outputs.h5_morphology_file,
        file_content_type=ContentType.application_x_hdf5,
        asset_label=AssetLabel.morphology,
    )
    client.upload_file(
        entity_id=morphology.id,  # ty:ignore[invalid-argument-type]
        entity_type=models.CellMorphology,
        file_path=outputs.h5_combined_morphology_file,
        file_content_type=ContentType.application_x_hdf5,
        asset_label=AssetLabel.morphology_with_spines,
    )
    L.debug(f"Upload complete for {morphology.id}")
    return morphology
