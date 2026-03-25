import json
import os
from pathlib import Path

PathLike = str | os.PathLike[str]


def write_json(data: dict, path: PathLike, **json_kwargs) -> None:
    """Write dictionary to file as JSON."""
    Path(path).write_text(json.dumps(data, **json_kwargs), encoding="utf-8")


def load_json(path: PathLike) -> dict:
    """Load JSON file to dict."""
    return json.loads(Path(path).read_bytes())


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
