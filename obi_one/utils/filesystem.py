"""Filesystem helpers for path creation and temporary working-directory changes."""

import os
import shutil
import stat
from collections.abc import Generator, Iterable
from contextlib import contextmanager, suppress
from pathlib import Path
from uuid import uuid4

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


def write_whole(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` by way of a file beside it, so ``path`` is never part-written."""
    part = path.with_name(f"{path.name}.{uuid4().hex}.part")
    try:
        part.write_bytes(data)
        part.replace(path)
    finally:
        part.unlink(missing_ok=True)


def remove_oldest_past(paths: Iterable[Path], limit: int) -> None:
    """Remove the files of ``paths`` modified longest ago, past ``limit`` bytes in all."""
    files = []
    for path in paths:
        with suppress(FileNotFoundError):
            found = path.stat()
            if stat.S_ISREG(found.st_mode):
                files.append((found, path))
    held = 0
    for found, path in sorted(files, key=lambda file: file[0].st_mtime_ns, reverse=True):
        held += found.st_size
        if held > limit:
            path.unlink(missing_ok=True)


def copy_tree(source: Path, target: Path) -> None:
    """Copy ``source`` (file or directory) to ``target``, creating parents."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
    else:
        shutil.copy2(source, target)
