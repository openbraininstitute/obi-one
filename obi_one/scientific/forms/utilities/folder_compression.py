import logging
import os
import tarfile
import time
from pathlib import Path
from typing import ClassVar

import entitysdk.client

from obi_one.core.block import Block
from obi_one.core.form import Form
from obi_one.core.path import NamedPath
from obi_one.core.single import SingleCoordinateMixin

L = logging.getLogger(__name__)

_KIB_FACTOR = 1024


class FolderCompressions(Form):
    """Folder compression form."""

    single_coord_class_name: ClassVar[str] = "FolderCompression"
    name: ClassVar[str] = "Folder Compression"
    description: ClassVar[str] = "Compresses a folder using the specified compression format."

    class Initialize(Block):
        folder_path: NamedPath | list[NamedPath]
        file_format: str | list[str | None] | None = "gz"
        file_name: str | list[str | None] | None = "compressed"

    initialize: Initialize


class FolderCompression(FolderCompressions, SingleCoordinateMixin):
    """Compression of an entire folder (e.g., circuit) using the given compression file format.

    The following compression formats are available: gzip (.gz; default), bzip2 (.bz2), LZMA (.xz)
    """

    FILE_FORMATS: ClassVar[tuple[str, ...]] = ("gz", "bz2", "xz")  # Supported compression formats

    def run(self, db_client: entitysdk.client.Client = None) -> None:  # noqa: ARG002
        # Initial checks
        if not Path(self.initialize.folder_path.path).isdir():
            msg = f"Folder path '{self.initialize.folder_path}' is not a valid directory!"
            raise ValueError(msg)
        if self.initialize.folder_path.path[-1] == os.path.sep:
            msg = f"Please remove trailing separator '{os.path.sep}' from path!"
            raise ValueError(msg)
        if self.initialize.file_format not in self.FILE_FORMATS:
            msg = (
                f"File format '{self.initialize.file_format}' not supported! Supported"
                f" formats: {self.FILE_FORMATS}"
            )
            raise ValueError(msg)

        output_file = (
            Path(self.coordinate_output_root)
            / f"{self.initialize.file_name}.{self.initialize.file_format}"
        )
        if Path(output_file).exists():
            msg = f"Output file '{output_file}' already exists!"
            raise ValueError(msg)

        # Compress using specified file format
        L.info(
            f"Info: Running {self.initialize.file_format} compression on"
            f" '{self.initialize.folder_path}'...",
        )
        t0 = time.time()
        with tarfile.open(output_file, f"w:{self.initialize.file_format}") as tar:
            tar.add(
                self.initialize.folder_path.path,
                arcname=Path(self.initialize.folder_path.path).name,
            )

        # Once done, check elapsed time and resulting file size for reporting
        dt = time.time() - t0
        t_str = time.strftime("%Hh:%Mmin:%Ss", time.gmtime(dt))
        file_size = Path(output_file).stat().st_size / (_KIB_FACTOR * _KIB_FACTOR)  # (MB)
        if file_size < _KIB_FACTOR:
            file_unit = "MB"
        else:
            file_size /= _KIB_FACTOR
            file_unit = "GB"
        L.info(f"DONE (Duration {t_str}; File size {file_size:.1f}{file_unit})")
