import json
import os
import shutil
import tarfile
from pathlib import Path

PathLike = str | os.PathLike[str]


def write_json(data: dict, path: PathLike, **json_kwargs) -> None:
    """Write dictionary to file as JSON."""
    Path(path).write_text(json.dumps(data, **json_kwargs), encoding="utf-8")


def load_json(path: PathLike) -> dict:
    """Load JSON file to dict."""
    return json.loads(Path(path).read_bytes())


def extract_tar_gz(
    archive_path: Path, output_dir: Path | None = None, *, clean: bool = False
) -> Path:
    """Extract a gzip-compressed tar archive (.tar.gz or .gz).

    Supports both ``.tar.gz`` and ``.gz`` file names — in both cases the file
    is expected to be a gzip-compressed tar archive (as produced by the
    folder compression task).

    Args:
        archive_path: Path to the compressed archive file.
        output_dir: Directory to extract into. Defaults to a sibling directory
            named after the archive stem (stripping .gz and .tar suffixes).
        clean: If True, delete the output directory before extraction (if it exists).

    Returns:
        Path to the extraction directory.
    """
    if output_dir is None:
        stem = archive_path.stem  # removes .gz
        stem = stem.removesuffix(".tar")
        output_dir = archive_path.parent / stem

    if clean and output_dir.exists():
        shutil.rmtree(output_dir)

    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(path=output_dir)  # noqa: S202

    return output_dir


def convert_image_to_webp(
    image_path: Path, *, overwrite: bool = False, quality: int = 80, method: int = 6
) -> Path:
    """Converts an image file (e.g., .png) to .webp format."""
    from PIL import Image  # noqa: PLC0415

    if not image_path.exists():
        msg = f"Input file '{image_path}' does not exist!"
        raise FileNotFoundError(msg)
    output_path = image_path.with_suffix(".webp")
    if not overwrite and output_path.exists():
        msg = f"Output file '{output_path}' already exists!"
        raise FileExistsError(msg)
    with Image.open(image_path) as img:
        image = img.convert("RGBA")
        image.save(output_path, "webp", quality=quality, method=method)
    return output_path
