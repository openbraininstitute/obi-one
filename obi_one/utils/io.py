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
