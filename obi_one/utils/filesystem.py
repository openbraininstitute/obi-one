from pathlib import Path

from obi_one.types import StrOrPath


def create_dir(path: StrOrPath) -> Path:
    """Create directory and parents if it doesn't already exist."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def filter_extension(file_list: list, extension: str) -> list:
    """Filter a list of files by extension."""
    return [f for f in file_list if Path(f).suffix.lower() == f".{extension}"]


def find_file(*, directory: Path, pattern: str, recursive: bool = False) -> Path:

    glob_func = directory.rglob if recursive else directory.glob

    try:
        return next(glob_func(pattern))
    except StopIteration:
        msg = f"No file found for pattern '{pattern}' in directory {directory}."
        raise FileNotFoundError(msg) from None
