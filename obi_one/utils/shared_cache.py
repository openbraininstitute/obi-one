"""Shared filesystem cache for reusable artifacts."""

from pathlib import Path


class SharedCache:
    """Filesystem cache for reusable artifacts.

    Instantiation creates known sub-directories under ``path``. Only sub-directory
    accessors are public.
    """

    def __init__(self, path: Path | str) -> None:
        """Create a cache at ``path``.

        Args:
            path: Existing cache root directory.
        """
        self._path = Path(path)
        self.mechanisms_dir.mkdir(parents=True, exist_ok=True)

    @property
    def mechanisms_dir(self) -> Path:
        """Directory used to cache compiled NEURON/neurodamus mechanisms."""
        return self._path / "mechanisms"
