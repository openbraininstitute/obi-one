from pathlib import Path

from obi_one.types import StrOrPath


def create_dir(path: StrOrPath) -> Path:
    """Create directory and parents if it doesn't already exist."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path
