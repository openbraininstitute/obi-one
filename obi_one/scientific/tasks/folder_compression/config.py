"""Folder compression task configuration."""

from pathlib import Path
from typing import ClassVar

from obi_one.core.block import Block
from obi_one.core.path import NamedPath
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.utils.io import compressed_archive_filename


class FolderCompressionScanConfig(ScanConfig):
    """Compression of an entire folder (e.g., circuit) using the given compression file format.

    The following compression formats are available: gzip (.gz; default), bzip2 (.bz2), LZMA (.xz)
    """

    name: ClassVar[str] = "Folder Compression"
    description: ClassVar[str] = "Compresses a folder using the specified compression format."

    class Initialize(Block):
        folder_path: NamedPath | list[NamedPath]
        file_format: str | list[str | None] | None = "gz"
        file_name: str | list[str | None] | None = "compressed"
        archive_name: str | None = None

        @property
        def output_filename(self) -> str:
            """Archive filename, e.g. "circuit.tar.gz"."""
            return compressed_archive_filename(self.file_name, self.file_format)  # ty:ignore[invalid-argument-type]

    initialize: Initialize


class FolderCompressionSingleConfig(FolderCompressionScanConfig, SingleConfigMixin):
    @property
    def output_path(self) -> Path:
        """Full path where the compressed archive is written."""
        return Path(self.coordinate_output_root) / self.initialize.output_filename
