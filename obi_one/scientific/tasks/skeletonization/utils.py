from pathlib import Path

from obi_one.scientific.tasks.skeletonization.schemas import WorkDir


def create_work_dir(output_dir: Path) -> WorkDir:
    inputs_dir = output_dir / "inputs"
    outputs_dir = output_dir / "outputs"
    inputs_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    return WorkDir(
        inputs=inputs_dir,
        outputs=outputs_dir,
    )


def find_file(directory: Path, extension: str) -> Path | None:
    """Return file with given extension or None."""
    return next(directory.rglob(f"*{extension}"), None)
