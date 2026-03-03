from pathlib import Path

from obi_one.scientific.tasks.skeletonization.schemas import WorkDir


def create_work_dir(output_dir: Path) -> WorkDir:
    """Create and initialize a working directory structure.

    This function ensures the existence of the main output directory and
    creates an `inputs` subdirectory inside it. The corresponding `outputs`
    path is also defined and returned as part of the WorkDir object.

    Args:
        output_dir: Base directory where the working structure should be created.

    Returns:
        A WorkDir instance containing paths to the `inputs` and `outputs` directories.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs_dir = output_dir / "inputs"
    outputs_dir = output_dir / "outputs"
    inputs_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    return WorkDir(
        inputs=inputs_dir,
        outputs=outputs_dir,
    )
