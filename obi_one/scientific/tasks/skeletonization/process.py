from pathlib import Path

import morphio
import ultraliser

from obi_one.core.exception import OBIONEError
from obi_one.scientific.tasks.skeletonization.constants import SPINY_MORPH_PATH_SUFFIX
from obi_one.scientific.tasks.skeletonization.schemas import (
    ProcessParameters,
    SkeletonizationOutputs,
)
from obi_one.scientific.tasks.skeletonization.utils import find_file


def run_process(parameters: ProcessParameters, output_dir: Path) -> None:
    ultraliser.skeletonize_neuron_mesh(
        mesh_path=str(parameters.mesh_path),
        output_path=str(output_dir),
        segment_spines=parameters.segment_spines,
        neuron_voxel_size=parameters.neuron_voxel_size,
        spines_voxel_size=parameters.spines_voxel_size,
    )


def create_process_outputs(output_dir: Path) -> SkeletonizationOutputs:
    if not (spiny_morph_path := find_file(output_dir, extension=".h5")):
        msg = "No combined morphology h5 file found in the output location."
        raise OBIONEError(msg)

    # Rename the combined morphology by adding "_with_spines" suffix
    spiny_morph_path.rename(
        spiny_morph_path.with_name(
            spiny_morph_path.stem + SPINY_MORPH_PATH_SUFFIX + spiny_morph_path.suffix
        )
    )

    if not (swc_path := find_file(output_dir, extension=".swc")):
        msg = "No SWC morphology file found in the output location"
        raise OBIONEError(msg)

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
