import logging
from pathlib import Path

import morphio

from obi_one.core.exception import OBIONEError
from obi_one.scientific.tasks.skeletonization.constants import SPINY_MORPH_PATH_SUFFIX
from obi_one.scientific.tasks.skeletonization.schemas import (
    ProcessParameters,
    SkeletonizationOutputs,
    WorkDir,
)

L = logging.getLogger(__name__)


def run_process(parameters: ProcessParameters, work_dir: WorkDir) -> SkeletonizationOutputs:
    L.info("Running executable process...")
    _run_process_executable(
        parameters=parameters,
        output_dir=work_dir.outputs,
    )
    L.info("Collecting process outputs...")
    return _create_process_outputs(
        mesh_path=parameters.mesh_path,
        output_dir=work_dir.outputs,
    )


def _run_process_executable(parameters: ProcessParameters, output_dir: Path) -> None:
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
            - write_raw_spines: Whether to include raw segmented spines in the output.
        output_dir: Directory where skeletonization outputs will be written.
    """
    import ultraliser  # noqa: PLC0415  # ty:ignore[unresolved-import]

    ultraliser.skeletonize_neuron_mesh(
        mesh_path=str(parameters.mesh_path),
        output_path=str(output_dir),
        segment_spines=parameters.segment_spines,
        neuron_voxel_size=parameters.neuron_voxel_size,
        spines_voxel_size=parameters.spines_voxel_size,
        write_raw_spines=parameters.write_raw_spines,
    )


def _create_process_outputs(mesh_path: Path, output_dir: Path) -> SkeletonizationOutputs:
    """Collect, post-process, and organize skeletonization output files.

    This function:
        1. Locates the combined morphology H5 file and renames it by appending
           the `_with_spines` suffix.
        2. Locates the generated SWC morphology file.
        3. Produces complementary H5 and ASC morphology files derived from the SWC file.
        4. Returns a structured `SkeletonizationOutputs` object containing all outputs.

    Args:
        mesh_path: Input mesh path
        output_dir: Directory where skeletonization output files were generated.

    Returns:
        SkeletonizationOutputs
            Object containing paths to:
            - H5 morphology file (derived from SWC)
            - SWC morphology file
            - ASC morphology file
            - Combined H5 morphology file (with reconstructed spines,
                and optional raw segmented spines)

    Raises:
        OBIONEError
            If required morphology files (.h5 or .swc) cannot be found in the output directory.
    """
    stem_name = mesh_path.stem  # e.g. foo/bar.h5 -> bar

    spiny_morph_path = output_dir / f"{stem_name}.h5"

    if not spiny_morph_path.exists():
        msg = (
            f"No combined morphology h5 file {spiny_morph_path.name} found in the output location."
        )
        raise OBIONEError(msg)

    swc_path = output_dir / f"{stem_name}-morphology.swc"

    if not swc_path.exists():
        msg = f"No SWC morphology file {swc_path.name} found in the output location"
        raise OBIONEError(msg)

    h5_path = output_dir / f"{stem_name}-morphology.h5"

    if not h5_path.exists():
        msg = f"No HDF5 morphology file {swc_path.name} found in the output location"
        raise OBIONEError(msg)

    # Rename the combined morphology by adding "_with_spines" suffix
    spiny_morph_path = spiny_morph_path.rename(
        spiny_morph_path.with_name(f"{stem_name}{SPINY_MORPH_PATH_SUFFIX}.h5")
    )

    # Produce complimentary ASC morphologies from the original SWC
    morpho = morphio.mut.Morphology(str(h5_path))
    asc_path = swc_path.with_suffix(".asc")
    morpho.write(str(asc_path))

    return SkeletonizationOutputs(
        h5_morphology_file=h5_path,
        swc_morphology_file=swc_path,
        asc_morphology_file=asc_path,
        h5_combined_morphology_file=spiny_morph_path,
    )
