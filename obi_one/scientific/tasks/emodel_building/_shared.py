"""Shared helpers for the emodel-building tasks.

BluePyEModel reads and writes relative paths (e.g. ``./config/recipes.json``,
``./figures/``, ``./final.json``), so a task writes its recipe and ``chdir``s
into the working directory (the single config's ``coordinate_output_root``)
before invoking the BluePyEModel API.
"""

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def chdir(path: Path) -> Iterator[None]:
    """Temporarily change the working directory to ``path``."""
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def write_recipes(recipes: dict, recipes_path: Path) -> None:
    """Write a ``recipes.json`` file with the standard BluePyEModel layout."""
    recipes_path.parent.mkdir(parents=True, exist_ok=True)
    with recipes_path.open("w", encoding="utf-8") as f:
        json.dump(recipes, f, indent=4)
