"""Shared resource-estimation helpers encoding launch-system machine limits."""

import numpy as np


def get_required_cpu_memory_combo(mem_gb_required: float) -> tuple[int, int]:
    """Returns the required CPU/memory combination."""
    # From launch-system
    cpu_memory_combinations: dict[int, set[int]] = {
        1: {2, 4, 6, 8},
        2: {4, 8, 12, 16},
        4: {8, 16, 24, 30},
        8: {16, 32, 48, 60},
        16: {32, 64, 96, 120},
    }

    max_mem = 0
    for ncpu, mem_values in cpu_memory_combinations.items():
        for mem in sorted(mem_values):
            max_mem = max(max_mem, mem)
            if mem > mem_gb_required:
                return (ncpu, mem)
    msg = (
        f"No CPU/memory combination found"
        f" (required: {mem_gb_required:.1f} GB, available: {max_mem:.1f} GB)!"
    )
    raise ValueError(msg)


def get_required_extra_storage_space(disk_space_gb_required: float) -> int | None:
    """Return the required extra storage space."""
    # From launch-system
    default_disk_space_limit_gb = 20
    extra_disk_space_limit_gb = 200

    if disk_space_gb_required <= default_disk_space_limit_gb:
        # No extra space requires, use default
        return None
    if disk_space_gb_required <= extra_disk_space_limit_gb:
        # Allocate extra space
        return np.ceil(disk_space_gb_required).astype(int)

    msg = (
        f"Not enough disk space"
        f" (required: {disk_space_gb_required:.1f} GB,"
        f" available: {extra_disk_space_limit_gb:.1f} GB)!"
    )
    raise ValueError(msg)
