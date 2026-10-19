"""Memory a process has freed, handed back to the system."""

import ctypes
import ctypes.util
import sys
from collections.abc import Callable
from functools import cache


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
