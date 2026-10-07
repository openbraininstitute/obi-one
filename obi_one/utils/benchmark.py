"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.utils.benchmark import (
    BenchmarkTracker,
    ClassVar,
    contextmanager,
    Generator,
    json,
    L,
    log_timing,
    logging,
    Path,
    psutil,
    threading,
    time,
)

__all__ = [
    "BenchmarkTracker",
    "ClassVar",
    "contextmanager",
    "Generator",
    "json",
    "L",
    "log_timing",
    "logging",
    "Path",
    "psutil",
    "threading",
    "time",
]
