"""Mechanisms-related utility functions."""

from pathlib import Path

_SUFFIX_DECLARATION_PARTS = 2


def get_suffix_from_mod_file(fpath: str | Path) -> str:
    """Returns the SUFFIX declared in a .mod file."""
    with Path(fpath).open(encoding="utf-8") as f:
        for raw_line in f:
            stripped_line = raw_line.strip()
            splitted_line = stripped_line.split()
            if len(splitted_line) == _SUFFIX_DECLARATION_PARTS and splitted_line[0] == "SUFFIX":
                return splitted_line[1]

    msg = f"Could not find SUFFIX declaration in {fpath}"
    raise ValueError(msg)
