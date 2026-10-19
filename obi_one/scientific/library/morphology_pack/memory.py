"""Memory a build has freed, handed back to the system."""

import ctypes
import ctypes.util
import sys
from collections.abc import Callable
from functools import cache


@cache
def malloc_trim() -> Callable[[int], int] | None:
    """The C library's malloc_trim, glibc's, or None where it has none."""
    if sys.platform != "linux":
        return None
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6")
    except OSError:
        return None
    return getattr(libc, "malloc_trim", None)


def give_back() -> None:
    """Hand the memory freed so far back to the system.

    glibc keeps freed memory for the process to reuse, and arrays freed between the stages of a
    build leave much of it in holes the next stage does not fill: held, unused, counted against
    the container.
    """
    trim = malloc_trim()
    if trim is not None:
        trim(0)
