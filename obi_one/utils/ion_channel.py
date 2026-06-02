"""Mechanisms-related utility functions."""

from pathlib import Path

def get_suffix_from_mod_file(fpath: str|Path) -> str:
    """Returns the SUFFIX declared in a .mod file."""
    with open(fpath, "r") as f:
        for line in f:
            line = line.strip()
            splitted_line = line.split()
            if len(splitted_line) == 2 and splitted_line[0] == "SUFFIX":
                return splitted_line[1]
    
    raise ValueError(f"Could not find SUFFIX declaration in {fpath}")
