"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.utils.io import (
    compressed_archive_filename,
    convert_image_to_webp,
    extract_tar_gz,
    json,
    load_json,
    os,
    Path,
    PathLike,
    shutil,
    tarfile,
    write_json,
)

__all__ = [
    "compressed_archive_filename",
    "convert_image_to_webp",
    "extract_tar_gz",
    "json",
    "load_json",
    "os",
    "Path",
    "PathLike",
    "shutil",
    "tarfile",
    "write_json",
]
