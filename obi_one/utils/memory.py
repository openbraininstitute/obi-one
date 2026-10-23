"""Memory a process may hold, and what it has freed handed back to the system."""

import ctypes
import ctypes.util
import sys
from collections.abc import Callable
from functools import cache
from pathlib import Path

import psutil

MEMORY_LIMIT = Path("/sys/fs/cgroup/memory.max")
MEMORY_LIMIT_V1 = Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")


@cache
def malloc_trim() -> Callable[[int], int] | None:
    """The C library's malloc_trim, or None where it has none: off Linux, or a C library other
    than glibc.

    glibc keeps freed memory for the process to reuse, and arrays freed between the stages of a
    long job leave much of it in holes the next stage does not fill: held, unused, counted
    against the container. `malloc_trim(0)` hands it back.
    """
    if sys.platform != "linux":
        return None
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6")
    except OSError:
        return None
    return getattr(libc, "malloc_trim", None)


def hand_back_freed() -> None:
    """What the process freed handed back to the system, where the C library can."""
    trim = malloc_trim()
    if trim is not None:
        trim(0)


def memory_limit() -> int:
    """The bytes the container's cgroup, v2 or v1, lets this process hold, or the machine's where
    those are fewer or it sets no limit.
    """
    machine = psutil.virtual_memory().total
    for path in (MEMORY_LIMIT, MEMORY_LIMIT_V1):
        if path.exists():
            limit = path.read_text(encoding="ascii").strip()
            return machine if limit == "max" else min(machine, int(limit))
    return machine


def memory_left(limit: int | None = None) -> int:
    """The bytes this process may hold beyond what it holds now, under `limit`, or
    `memory_limit()` where none is given.
    """
    held = psutil.Process().memory_info().rss
    return max(0, (memory_limit() if limit is None else limit) - held)
