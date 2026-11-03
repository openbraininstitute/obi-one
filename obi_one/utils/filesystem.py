"""Filesystem helpers for path creation and temporary working-directory changes."""

import hashlib
import os
import shutil
import urllib.request
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from obi_one.core.exception import OBIONEError
from obi_one.types import StrOrPath


def create_dir(path: StrOrPath) -> Path:
    """Create directory and parents if it doesn't already exist."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def filter_extension(file_list: list, extension: str) -> list:
    """Filter a list of files by extension."""
    return [f for f in file_list if Path(f).suffix.lower() == f".{extension}"]


@contextmanager
def chdir(path: Path) -> Generator[None, None, None]:
    """Temporarily change the working directory to ``path``."""
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def copy_tree(source: Path, target: Path) -> None:
    """Copy ``source`` (file or directory) to ``target``, creating parents."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
    else:
        shutil.copy2(source, target)


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of the file at ``path``."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(url: str, destination: Path, sha256: str, timeout: float = 600) -> Path:
    """Download ``url`` to ``destination``, keeping it only if its SHA-256 is ``sha256``."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    with (
        urllib.request.urlopen(url, timeout=timeout) as response,  # ruff: ignore[suspicious-url-open-usage]
        partial.open("wb") as handle,
    ):
        shutil.copyfileobj(response, handle)
    actual = sha256_file(partial)
    if actual != sha256:
        partial.unlink(missing_ok=True)
        msg = f"Checksum mismatch for {url}: expected {sha256}, got {actual}."
        raise OBIONEError(msg)
    partial.replace(destination)
    return destination
