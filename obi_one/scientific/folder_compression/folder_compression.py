import logging
from typing import ClassVar

L = logging.getLogger(__name__)

from obi_one.core.block import Block
from obi_one.core.form import Form
from obi_one.core.path import NamedPath
from obi_one.core.single import SingleCoordinateMixin


class FolderCompressions(Form):
    """ """

    single_coord_class_name: ClassVar[str] = "FolderCompression"
    name: ClassVar[str] = "Folder Compression"
    description: ClassVar[str] = "Compresses a folder using the specified compression format."

    class Initialize(Block):
        folder_path: NamedPath | list[NamedPath]
        file_format: None | str | list[None | str] = "gz"
        file_name: None | str | list[None | str] = "compressed"

    initialize: Initialize


import os
import tarfile
import time
import traceback
from typing import ClassVar


class FolderCompression(FolderCompressions, SingleCoordinateMixin):
    """Compression of an entire folder (e.g., circuit) using the given compression file format.
    The following compression formats are available: gzip (.gz; default), bzip2 (.bz2), LZMA (.xz)
    """

    FILE_FORMATS: ClassVar[tuple[str, ...]] = ("gz", "bz2", "xz")  # Supported compression formats

    def run(self) -> None:
        try:
            # Initial checks
            assert os.path.isdir(self.initialize.folder_path.path), (
                f"Folder path '{self.initialize.folder_path}' is not a valid directory!"
            )
            assert self.initialize.folder_path.path[-1] != os.path.sep, (
                f"Please remove trailing separator '{os.path.sep}' from path!"
            )
            assert self.initialize.file_format in self.FILE_FORMATS, (
                f"File format '{self.initialize.file_format}' not supported! Supported formats: {self.FILE_FORMATS}"
            )

            output_file = os.path.join(
                self.coordinate_output_root,
                f"{self.initialize.file_name}.{self.initialize.file_format}",
            )
            assert not os.path.exists(output_file), f"Output file '{output_file}' already exists!"

            # Compress using specified file format
            L.info(
                f"Info: Running {self.initialize.file_format} compression on '{self.initialize.folder_path}'...",
            )
            t0 = time.time()
            with tarfile.open(output_file, f"w:{self.initialize.file_format}") as tar:
                tar.add(
                    self.initialize.folder_path.path,
                    arcname=os.path.basename(self.initialize.folder_path.path),
                )

            # Once done, check elapsed time and resulting file size for reporting
            dt = time.time() - t0
            t_str = time.strftime("%Hh:%Mmin:%Ss", time.gmtime(dt))
            file_size = os.stat(output_file).st_size / (1024 * 1024)  # (MB)
            if file_size < 1024:
                file_unit = "MB"
            else:
                file_size = file_size / 1024
                file_unit = "GB"
            L.info(f"DONE (Duration {t_str}; File size {file_size:.1f}{file_unit})", flush=True)

        except Exception as e:
            traceback.print_exception(e)
