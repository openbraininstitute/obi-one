"""Shared filesystem cache for reusable artifacts."""

import os
from pathlib import Path
from typing import Self


class SharedCacheError(Exception):
    """Raised when a shared cache path cannot be used."""


class SharedCache:
    """Filesystem cache for reusable artifacts.

    Instantiation creates known sub-directories under ``path``. Only sub-directory
    accessors are public.
    """

    def __init__(self, path: Path | str) -> None:
        """Create a cache at ``path``."""
        self._path = Path(path)
        self.mechanisms_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_existing_path(cls, path: Path | str) -> Self:
        """Return a ``SharedCache`` for an existing writable directory.

        Raises:
            SharedCacheError: If ``path`` is empty, missing, not a directory, or not writable.
        """
        # Reject "" / "." (Path("") normalizes to ".") before resolve uses cwd.
        raw_path = os.fspath(path)
        if not raw_path or Path(raw_path) == Path():
            msg = "Shared cache path must not be empty"
            raise SharedCacheError(msg)

        try:
            resolved = Path(path).resolve()
        except OSError as error:
            msg = f"Shared cache path could not be resolved: {path}"
            raise SharedCacheError(msg) from error

        if not resolved.exists():
            msg = f"Shared cache path does not exist: {resolved}"
            raise SharedCacheError(msg)

        if not resolved.is_dir():
            msg = f"Shared cache path is not a directory: {resolved}"
            raise SharedCacheError(msg)

        if not os.access(resolved, os.W_OK):
            msg = f"Shared cache path is not writable: {resolved}"
            raise SharedCacheError(msg)

        try:
            return cls(resolved)
        except OSError as error:
            msg = f"Shared cache could not be initialized at {resolved}"
            raise SharedCacheError(msg) from error

    @property
    def mechanisms_dir(self) -> Path:
        """Directory used to cache compiled NEURON/neurodamus mechanisms."""
        return self._path / "mechanisms"
