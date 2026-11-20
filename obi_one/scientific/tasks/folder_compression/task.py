"""Folder compression task."""

import logging
import os
import tarfile
import time
from pathlib import Path
from typing import ClassVar

import entitysdk.client

from obi_one.core.task import Task
from obi_one.scientific.tasks.folder_compression.config import FolderCompressionSingleConfig

L = logging.getLogger(__name__)

_KIB_FACTOR = 1024


class FolderCompressionTask(Task):
    config: FolderCompressionSingleConfig

    FILE_FORMATS: ClassVar[tuple[str, ...]] = ("gz", "bz2", "xz")  # Supported compression formats

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client | None = None,  # ruff: ignore[unused-method-argument]
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: str | None = None,  # ruff: ignore[unused-method-argument]
    ) -> None:
        # Initial checks
        if not Path(self.config.initialize.folder_path.path).is_dir():  # ty:ignore[unresolved-attribute]
            msg = f"Folder path '{self.config.initialize.folder_path}' is not a valid directory!"
            raise ValueError(msg)
        if self.config.initialize.folder_path.path[-1] == os.path.sep:  # ty:ignore[unresolved-attribute]
            msg = f"Please remove trailing separator '{os.path.sep}' from path!"
            raise ValueError(msg)
        if self.config.initialize.file_format not in self.FILE_FORMATS:
            msg = (
                f"File format '{self.config.initialize.file_format}' not supported! Supported"
                f" formats: {self.FILE_FORMATS}"
            )
            raise ValueError(msg)

        output_file = self.config.output_path
        if Path(output_file).exists():
            msg = f"Output file '{output_file}' already exists!"
            raise ValueError(msg)

        # Compress using specified file format
        L.info(
            f"Info: Running {self.config.initialize.file_format} compression on"
            f" '{self.config.initialize.folder_path}'...",
        )
        t0 = time.time()

        # Determine archive name: use provided value or default to folder name
        archive_name = (
            self.config.initialize.archive_name
            or Path(self.config.initialize.folder_path.path).name  # ty:ignore[unresolved-attribute]
        )

        # dereference=True follows symlinks and archives the files they point to, rather
        # than the links themselves. Circuits staged by the launch-system are symlinks into
        # the mounted EFS asset store, so without this the archive would contain only dangling
        # links once extracted elsewhere.
        with tarfile.open(  # ty:ignore[no-matching-overload]
            output_file, f"w:{self.config.initialize.file_format}", dereference=True
        ) as tar:
            tar.add(
                self.config.initialize.folder_path.path,  # ty:ignore[unresolved-attribute]
                arcname=archive_name,
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
