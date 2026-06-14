"""Mechanisms-related utility functions."""

import shutil
import subprocess
from pathlib import Path


def compile_mechanisms(mechanisms_dir: str | Path) -> None:
    """Compile mechanisms in the given directory.

    Args:
        mechanisms_dir (str or Pathlib.Path): path to the directory with mechanisms
    """
    subprocess.run(
        [
            "nrnivmodl",
            "-incflags",
            "-DDISABLE_REPORTINGLIB",
            str(mechanisms_dir),
        ],
        check=True,
    )


def clean_compiled_mechanisms() -> None:
    """Remove compiled mechanisms in the current directory."""
    compiled_mech_possible_dirs = [
        Path("x86_64"),
        Path("arm64"),
    ]
    for compiled_dir in compiled_mech_possible_dirs:
        if compiled_dir.exists():
            shutil.rmtree(compiled_dir)
