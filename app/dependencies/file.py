import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends


def _create_temp_dir() -> Iterator[Path]:
    """Create a temporary directory, to be used as a dependency with scope=request.

    The directory is deleted only after the response is sent back to the client,
    and even in case of uncaught exception.
    """
    temp_dir = Path(tempfile.mkdtemp())
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


TempDirDep = Annotated[Path, Depends(_create_temp_dir, scope="request")]
