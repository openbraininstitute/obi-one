"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.utils.process import (
    L,
    logging,
    os,
    Path,
    run_and_log,
    shlex,
    subprocess,
)

__all__ = [
    "L",
    "logging",
    "os",
    "Path",
    "run_and_log",
    "shlex",
    "subprocess",
]
