from pathlib import Path

import morphio

from obi_one.core.exception import OBIONEError
from obi_one.scientific.tasks.skeletonization.constants import SPINY_MORPH_PATH_SUFFIX
from obi_one.scientific.tasks.skeletonization.schemas import (
    ProcessParameters,
    SkeletonizationOutputs,
)
from obi_one.scientific.tasks.skeletonization.utils import find_file


def run_process(parameters: ProcessParameters, output_dir: Path) -> None:
    """Run neuron mesh skeletonization.

    This function calls `ultraliser.skeletonize_neuron_mesh` to generate
    neuron skeletons and associated morphology files from a mesh input.

    Args:
        parameters:
            Configuration parameters required for skeletonization, including:
            - mesh_path: Path to the input neuron mesh.
            - segment_spines: Whether to segment dendritic spines.
            - neuron_voxel_size: Voxel size for neuron processing.
            - spines_voxel_size: Voxel size for spine processing.
        output_dir: Directory where skeletonization outputs will be written.
    """
    import ultraliser  # noqa: PLC0415

    ultraliser.skeletonize_neuron_mesh(
        mesh_path=str(parameters.mesh_path),
        output_path=str(output_dir),
        segment_spines=parameters.segment_spines,
        neuron_voxel_size=parameters.neuron_voxel_size,
        spines_voxel_size=parameters.spines_voxel_size,
    )


def create_process_outputs(output_dir: Path) -> SkeletonizationOutputs:
    """Collect, post-process, and organize skeletonization output files.

    This function:
        1. Locates the combined morphology H5 file and renames it by appending
           the `_with_spines` suffix.
        2. Locates the generated SWC morphology file.
        3. Produces complementary H5 and ASC morphology files derived from the SWC file.
        4. Returns a structured `SkeletonizationOutputs` object containing all outputs.

    Args:
        output_dir: Directory where skeletonization output files were generated.

    Returns:
        SkeletonizationOutputs
            Object containing paths to:
            - H5 morphology file (derived from SWC)
            - SWC morphology file
            - ASC morphology file
            - Combined H5 morphology file (with spines)

    Raises:
        OBIONEError
            If required morphology files (.h5 or .swc) cannot be found in the output directory.
    """
    spiny_morph_path = find_file(output_dir, extension=".h5")

    if not spiny_morph_path:
        msg = "No combined morphology h5 file found in the output location."
        raise OBIONEError(msg)

    swc_path = find_file(output_dir, extension=".swc")

    if not swc_path:
        msg = "No SWC morphology file found in the output location"
        raise OBIONEError(msg)

    # Rename the combined morphology by adding "_with_spines" suffix
    spiny_morph_path.rename(
        spiny_morph_path.with_name(
            spiny_morph_path.stem + SPINY_MORPH_PATH_SUFFIX + spiny_morph_path.suffix
        )
    )

    # Produce complimentary H5 and ASC morphologies from the original SWC
    morpho = morphio.mut.Morphology(str(swc_path))
    h5_path = swc_path.with_name(swc_path.stem + ".h5")
    asc_path = swc_path.with_name(swc_path.stem + ".asc")

    morpho.write(str(h5_path))
    morpho.write(str(asc_path))

    return SkeletonizationOutputs(
        h5_morphology_file=h5_path,
        swc_morphology_file=swc_path,
        asc_morphology_file=asc_path,
        h5_combined_morphology_file=spiny_morph_path,
    )
