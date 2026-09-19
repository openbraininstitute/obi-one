"""Filesystem helpers for path creation and temporary working-directory changes."""

import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
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


@contextmanager
def chdir(path: Path) -> Iterator[None]:
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
