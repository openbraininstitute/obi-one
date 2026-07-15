"""Optional GLB mesh generation from SWC morphology data."""

import logging
import tempfile
import uuid
from pathlib import Path

from entitysdk import Client
from entitysdk.exception import EntitySDKError
from entitysdk.models.asset import Asset
from entitysdk.models.cell_morphology import CellMorphology
from entitysdk.types import AssetLabel, ContentType

L = logging.getLogger(__name__)

try:
    from nmm.common import NEURON_COLORS
    from nmm.morphology import NeuronMorphology

    HAS_MESHING = True
except ImportError:
    HAS_MESHING = False


def _mesh_swc(swc_path: str, output_directory: str) -> str:
    morphology = NeuronMorphology(
        swc_path,
        smooth_sections=True,
        soma_color=NEURON_COLORS.SOMA,
        axon_color=NEURON_COLORS.AXON,
        basal_dendrite_color=NEURON_COLORS.BASAL_DENDRITE,
        apical_dendrite_color=NEURON_COLORS.APICAL_DENDRITE,
    )
    return morphology.export_annotated_glb_mesh(output_directory=output_directory, show_stats=False)


def _validate_mesh_output(glb_path: Path, glb_path_str: str) -> None:
    if not glb_path.exists():
        msg = f"Meshing produced no output at {glb_path_str}"
        raise RuntimeError(msg)

    if glb_path.stat().st_size == 0:
        msg = f"Meshing produced blank output at {glb_path_str}"
        raise RuntimeError(msg)


def mesh_and_upload(
    client: Client,
    cell_morphology_id: uuid.UUID,
    swc_bytes: bytes,
) -> Asset:
    """Convert SWC bytes to a GLB mesh and upload it as an asset on the given morphology."""
    L.info("Meshing morphology %s", cell_morphology_id)
    with tempfile.TemporaryDirectory() as tmp_dir:
        swc_path = Path(tmp_dir) / f"{uuid.uuid4()}.swc"
        swc_path.write_bytes(swc_bytes)

        glb_path_str = _mesh_swc(str(swc_path), output_directory=tmp_dir)
        glb_path = Path(glb_path_str)

        _validate_mesh_output(glb_path, glb_path_str)

        try:
            return client.upload_file(
                entity_id=cell_morphology_id,
                entity_type=CellMorphology,
                file_path=glb_path,
                file_content_type=ContentType.model_gltf_binary,
                asset_label=AssetLabel.cell_surface_mesh,
            )
        except EntitySDKError as err:
            msg = f"Failed to upload GLB asset for {cell_morphology_id}"
            raise RuntimeError(msg) from err
