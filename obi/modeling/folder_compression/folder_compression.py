from obi.modeling.core.form import Form
from obi.modeling.core.block import Block
from obi.modeling.core.single import SingleCoordinateMixin
from obi.modeling.core.base import NamedPath

class FolderCompressions(Form):
    """
    """

    _single_coord_class_name = "FolderCompression"

    class Initialize(Block):
        folder_path: NamedPath | list[NamedPath]
        file_format: None | str | list[None | str] = "xz"
        file_name: None | str | list[None | str] = "compressed"

    initialize: Initialize


import os
import tarfile
from typing import ClassVar

class FolderCompression(FolderCompressions, SingleCoordinateMixin):
    """
    """
    FILE_FORMATS: ClassVar[tuple[str, ...]] = ("xz", "gz", "bz2")  # Supported compression formats

    def run(self) -> None:

        try:
            assert os.path.isdir(self.initialize.folder_path.path), f"Folder path '{self.initialize.folder_path}' is not a valid directory!"
            assert self.initialize.folder_path.path[-1] != os.path.sep, f"Please remove trailing separator '{os.path.sep}' from path!"
            assert self.initialize.file_format in self.FILE_FORMATS, f"File format '{self.initialize.file_format}' not supported! Supported formats: {self.FILE_FORMATS}"
            
            output_file = os.path.join(self.coordinate_output_root, f"{self.initialize.file_name}.{self.initialize.file_format}")
            assert not os.path.exists(output_file), f"Output file '{output_file}' already exists!"

            # Compress
            print(f"Info: Running {self.initialize.file_format} compression on {self.initialize.folder_path}...", end="", flush=True)
            with tarfile.open(output_file, f"w:{self.initialize.file_format}") as tar:
                tar.add(self.initialize.folder_path.path, arcname=os.path.basename(self.initialize.folder_path.path))
            print("DONE", flush=True)

        except Exception as e:
            print(f"Error: {e}")
