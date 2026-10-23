"""A circuit's morphology pack, built from its files on disk.

The format is specified in docs/format.md beside this module.
"""

import gc
import logging
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import libsonata
import morphio

from obi_one.scientific.library.morphology_pack.circuit import (
    PRELOAD,
    MorphologyKey,
    Population,
    biophysical_populations,
    distinct_morphologies,
    morphologies_source,
    place_cells,
    read_morphology,
    read_population,
    simplified_all,
)
from obi_one.scientific.library.morphology_pack.geometry import (
    LEVELS,
    Morphology,
    MorphologyLevels,
)
from obi_one.utils.memory import hand_back_freed, memory_left
from obi_one.utils.parallel import Processes, available_cpus

L = logging.getLogger(__name__)

# Segments over every level a pack may hold, however much memory the machine has: above the whole
# FlyWire brain's, about 255 million.
MAX_SEGMENTS = 300_000_000
# The memory a build holds at its peak beyond what the process held as it began, on two processes,
# both included: `BASE_BYTES`, and `BYTES_A_SEGMENT` a segment over every level. Measured on 2 CPUs
# in a Linux container, in the memory that cannot be reclaimed: 300 MB and 40 B a segment where
# cells share their morphologies (CA1), 290 MB and 43 B where none share one.
BASE_BYTES = 400 * 2**20
BYTES_A_SEGMENT = 50
# What each process past two holds beside them, measured at about 110 MB while simplifying.
BYTES_A_WORKER = 128 * 2**20
# Past about eight processes, what the main process does alone, chunk by chunk, keeps the others
# waiting, while each holds its own memory.
MAX_WORKERS = 8
# What reading a morphology raises for a file that is not one, or a name its container lacks.
UNREADABLE = (morphio.MorphioError, OSError, RuntimeError)


class NoPackError(Exception):
    """A circuit that cannot have a pack: why is the message."""


class Stages:
    """Logs each stage of a build as it ends, with the seconds it took."""

    def __init__(self) -> None:
        """Time from now on."""
        self.began = time.perf_counter()

    def done(self, what: str, *args: object) -> None:
        now = time.perf_counter()
        L.info("Morphology pack: " + what + " in %.1f s", *args, now - self.began)
        self.began = now


def processes_for(workers: int | None) -> int:
    """The processes a build runs over: `workers`, or one a CPU up to `MAX_WORKERS`."""
    return workers or min(available_cpus(), MAX_WORKERS)


def segment_cap(limit: int | None = None, workers: int | None = None) -> int:
    """The segments a pack built here over `workers` processes, as `build_morphology_pack` counts
    them, may hold: `MAX_SEGMENTS`, or fewer where the memory left under `limit`, the container's
    where none is given, holds fewer, once what the process freed is handed back.
    """
    gc.collect()
    hand_back_freed()
    left = memory_left(limit)
    base = BASE_BYTES + BYTES_A_WORKER * max(0, processes_for(workers) - 2)
    cap = min(max(0, left - base) // BYTES_A_SEGMENT, MAX_SEGMENTS)
    if cap < MAX_SEGMENTS:
        L.info("Morphology pack capped at %d segments by %d bytes of memory left", cap, left)
    else:
        L.info("Morphology pack capped at %d segments", MAX_SEGMENTS)
    return cap


def read_populations(config: libsonata.CircuitConfig) -> list[Population]:
    names = biophysical_populations(config)
    if not names:
        msg = "The circuit has no biophysical population"
        raise NoPackError(msg)
    return [read_population(config, name, *morphologies_source(config, name)) for name in names]


def read_morphologies(populations: Sequence[Population]) -> dict[MorphologyKey, Morphology]:
    """Every distinct morphology of the populations that can be read."""
    morphologies = {}
    for key, collection in distinct_morphologies(populations):
        try:
            morphologies[key] = read_morphology(key, collection)
        except UNREADABLE:
            L.warning("Morphology %s left out: it could not be read", key[1], exc_info=True)
    if not morphologies:
        msg = "None of the circuit's morphologies could be read"
        raise NoPackError(msg)
    return morphologies


def every_level_within(
    morphologies: dict[MorphologyKey, Morphology],
    cells: Counter[MorphologyKey],
    max_segments: int,
    processes: Processes,
) -> dict[MorphologyKey, MorphologyLevels]:
    """Every morphology at each of `LEVELS`, which come to at most `max_segments` together:
    the build stops at the first morphology past them. Each is taken out of `morphologies` as
    it is simplified.
    """
    library = {}
    segments = 0
    for key, levels in simplified_all(morphologies, LEVELS, processes):
        segments += cells[key] * sum(shape.segments for shape in levels.shapes)
        if segments > max_segments:
            msg = (
                f"The circuit's levels come to over the {max_segments} segments a pack may hold"
                " here"
            )
            raise NoPackError(msg)
        library[key] = levels
    return library


def build_morphology_pack(
    config_path: Path, max_segments: int, workers: int | None = None
) -> bytes:
    """The pack of every level of the circuit at `config_path`, over `workers` processes, one a
    CPU up to `MAX_WORKERS` unless given.

    Raises NoPackError for a circuit without a biophysical population, none of whose
    morphologies can be read, or whose levels come to over `max_segments` segments.
    """
    stages = Stages()
    config = libsonata.CircuitConfig.from_file(str(config_path))
    populations = read_populations(config)
    cells = Counter(key for population in populations for key in population.morphology_keys())
    with Processes(processes_for(workers), PRELOAD) as processes:
        morphologies = read_morphologies(populations)
        stages.done("%d morphologies read", len(morphologies))
        shapes = every_level_within(morphologies, cells, max_segments, processes)
        stages.done("%d levels simplified", len(LEVELS))
        hand_back_freed()
        writer = place_cells(populations, LEVELS, shapes)
        del shapes
        hand_back_freed()
        stages.done("%d cells placed", sum(cells.values()))
        pack = writer.pack(processes)
    stages.done("%d bytes packed", len(pack))
    return pack
