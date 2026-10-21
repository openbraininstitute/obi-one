"""A circuit's morphologies as one pack, built while the viewer waits.

Temporary: it goes once circuit registration stores the pack on the circuit and the circuits
already registered have theirs. Until then it serves the circuits small enough to be read in a
request, and refuses the others as early as it can tell.
"""

import os
import shutil
import threading
from collections import Counter
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from enum import StrEnum
from http import HTTPStatus
from itertools import groupby
from pathlib import Path
from typing import NoReturn
from uuid import UUID

import libsonata
import morphio
from entitysdk.client import Client
from entitysdk.models import Circuit
from entitysdk.models.asset import Asset
from fastapi import HTTPException

from app.config import settings
from app.errors import ApiErrorCode
from app.logger import L
from app.services.circuit_visualization import (
    download_circuit_config,
    get_circuit,
    resolve_morph_path,
    sonata_circuit_asset,
)
from obi_one.scientific.library.circuit_metrics import (
    TYPES_OF_BIOPHYS_NODES,
    get_names_of_typed_node_populations,
)
from obi_one.scientific.library.morphology_pack.circuit import (
    PRELOAD,
    MorphologyKey,
    Population,
    distinct_morphologies,
    place_cells,
    read_morphology,
    read_population,
    simplified_all,
)
from obi_one.scientific.library.morphology_pack.geometry import (
    LEVELS,
    Level,
    Morphology,
    MorphologyLevels,
)
from obi_one.scientific.library.morphology_pack.writer import PackWriter
from obi_one.utils.filesystem import remove_oldest_past, write_whole
from obi_one.utils.memory import malloc_trim
from obi_one.utils.parallel import Processes, available_cpus

DEFAULT_MAX_SEGMENTS = 2_000_000
# Processes a build uses unless set: past about eight, what the main process does alone, chunk
# by chunk, keeps the others waiting, while each holds its own memory.
DEFAULT_MAX_WORKERS = 8
FETCHES_AT_ONCE = 8
# How long a request waits for the build before it.
PATIENCE_SECONDS = 120
# What reading a morphology raises for a file that is not one, or a name its container lacks.
UNREADABLE = (morphio.MorphioError, OSError, RuntimeError)

KEPT_SUFFIX = ".mpack"

# One build at a time: two would hold twice the memory.
BUILDING = threading.Lock()


class Refusal(StrEnum):
    TOO_MANY_NEURONS = "too_many_neurons"
    FILES_TOO_LARGE = "files_too_large"
    TOO_MANY_POINTS = "too_many_points"
    TOO_MANY_SEGMENTS = "too_many_segments"
    NO_MORPHOLOGIES = "no_morphologies"
    BUSY = "busy"


def refuse(
    reason: Refusal, detail: str, status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY
) -> NoReturn:
    raise HTTPException(
        status_code=status,
        detail={"code": ApiErrorCode.INVALID_REQUEST, "reason": reason, "detail": detail},
    )


class Staging:
    """Fetches a circuit's files into a directory, within the bytes a pack may read in all."""

    def __init__(self, client: Client, circuit_id: UUID, asset: Asset, directory: Path) -> None:
        """Read the sizes of the circuit's files; nothing is fetched yet."""
        self.client = client
        self.circuit_id = circuit_id
        self.asset = asset
        self.directory = directory
        listing = client.list_directory(
            entity_id=circuit_id, entity_type=Circuit, asset_id=asset.id
        )
        self.sizes = {Path(path): file.size for path, file in listing.files.items()}
        self.staged = 0

    def fetch(self, paths: Iterable[Path]) -> None:
        """Fetch files given by their place in the directory, unless they are too large."""
        asset_paths = [path.relative_to(self.directory) for path in paths]
        missing = [str(path) for path in asset_paths if path not in self.sizes]
        if missing:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail={
                    "code": ApiErrorCode.INVALID_REQUEST,
                    "detail": f"The circuit has no file {missing[0]}",
                },
            )
        self.staged += sum(self.sizes[path] for path in asset_paths)
        limit = settings.CIRCUIT_MORPHOLOGY_PACK_MAX_STAGED_BYTES
        if self.staged > limit:
            refuse(
                Refusal.FILES_TOO_LARGE,
                f"The circuit's nodes and morphologies take {self.staged} bytes or more, over the"
                f" {limit} a pack built on request may read",
            )
        with ThreadPoolExecutor(max_workers=FETCHES_AT_ONCE) as pool:
            list(pool.map(self.fetch_one, asset_paths))

    def fetch_one(self, asset_path: Path) -> None:
        self.client.fetch_file(
            entity_id=self.circuit_id,
            entity_type=Circuit,
            # the asset, not its id: given an id, the client looks the asset up for every file
            asset_id=self.asset,
            output_path=self.directory / asset_path,
            asset_path=asset_path,
        )


def morphology_files(population: Population) -> list[Path]:
    """The container, or a file for each of the population's distinct morphologies."""
    path = population.morphologies_path
    if path.suffix:
        return [path]
    return [
        path / f"{name}.{population.morphology_format}"
        for name in sorted(set(population.morphologies))
    ]


def stage_populations(config: libsonata.CircuitConfig, staging: Staging) -> list[Population]:
    """Fetch the biophysical populations' nodes and morphologies, and read the nodes."""
    names = sorted(get_names_of_typed_node_populations(config, TYPES_OF_BIOPHYS_NODES))
    if not names:
        refuse(Refusal.NO_MORPHOLOGIES, "The circuit has no biophysical population")
    staging.fetch({Path(config.node_population_properties(name).elements_path) for name in names})
    populations = []
    for name in names:
        source = resolve_morph_path(name, config)
        populations.append(read_population(config, name, source.path, source.format))
    staging.fetch({file for population in populations for file in morphology_files(population)})
    return populations


def read_within_limit(
    populations: list[Population], cells: Counter[MorphologyKey]
) -> dict[MorphologyKey, Morphology]:
    """Every distinct morphology that can be read, within the points allowed over all the cells."""
    limit = settings.CIRCUIT_MORPHOLOGY_PACK_MAX_POINTS
    morphologies = {}
    points = 0
    for key, collection in distinct_morphologies(populations):
        try:
            morphology = read_morphology(key, collection)
        except UNREADABLE:
            L.warning("Morphology %s left out: it could not be read", key[1], exc_info=True)
            continue
        morphologies[key] = morphology
        points += cells[key] * len(morphology.points)
        if points > limit:
            refuse(Refusal.TOO_MANY_POINTS, f"The circuit's morphologies have over {limit} points")
    return morphologies


def workers() -> int:
    return settings.CIRCUIT_MORPHOLOGY_PACK_WORKERS or min(available_cpus(), DEFAULT_MAX_WORKERS)


def finest_level_within(
    morphologies: dict[MorphologyKey, Morphology],
    cells: Counter[MorphologyKey],
    max_segments: int,
    processes: Processes,
) -> tuple[Level, dict[MorphologyKey, MorphologyLevels]]:
    """The finest level of at most `max_segments` segments, and every morphology at it."""
    segments = 0
    # Levels that prune alike come out of one pass over the morphologies, so the far level's
    # pass is made only for a circuit the finer ones are too many segments for.
    for _, together in groupby(LEVELS, key=lambda level: level.prune_um):
        levels = tuple(together)
        library = simplified_all(morphologies, levels, processes)
        for place, level in enumerate(levels):
            segments = sum(
                cells[key] * found.shapes[place].segments for key, found in library.items()
            )
            if segments <= max_segments:
                return level, {key: found.only(place) for key, found in library.items()}
    refuse(
        Refusal.TOO_MANY_SEGMENTS,
        f"The circuit's coarsest level has {segments} segments, over the {max_segments} the pack"
        " may hold",
    )


def every_level_within(
    morphologies: dict[MorphologyKey, Morphology],
    cells: Counter[MorphologyKey],
    max_segments: int,
    processes: Processes,
) -> dict[MorphologyKey, MorphologyLevels]:
    """Every morphology at each of `LEVELS`, which come to at most `max_segments` together."""
    library = simplified_all(morphologies, LEVELS, processes)
    segments = sum(
        cells[key] * shape.segments for key, found in library.items() for shape in found.shapes
    )
    if segments > max_segments:
        refuse(
            Refusal.TOO_MANY_SEGMENTS,
            f"The circuit's levels have {segments} segments together, over the {max_segments}"
            " the pack may hold",
        )
    return library


def placed_cells(
    client: Client,
    circuit_id: UUID,
    asset: Asset,
    directory: Path,
    max_segments: int,
    processes: Processes,
    *,
    all_levels: bool,
) -> PackWriter:
    """The circuit's cells, read and placed at every level, or else at the finest that fits.

    What was staged and read is let go of on the way, so that the writer alone is held while
    it packs.
    """
    config = download_circuit_config(client, circuit_id, asset.id, directory)
    populations = stage_populations(config, Staging(client, circuit_id, asset, directory))
    cells = Counter(key for population in populations for key in population.morphology_keys())
    morphologies = read_within_limit(populations, cells)
    # a private circuit's files were downloaded, in production into memory
    shutil.rmtree(directory)
    if not morphologies:
        refuse(Refusal.NO_MORPHOLOGIES, "None of the circuit's morphologies could be read")
    cap = settings.CIRCUIT_MORPHOLOGY_PACK_MAX_SEGMENTS
    if all_levels:
        levels, shapes = LEVELS, every_level_within(morphologies, cells, cap, processes)
    else:
        level, shapes = finest_level_within(morphologies, cells, min(max_segments, cap), processes)
        levels = (level,)
    del morphologies
    trim = malloc_trim()
    if trim is not None:
        trim(0)
    return place_cells(populations, levels, shapes)


def kept_path(asset: Asset) -> Path | None:
    """Where the pack of every level of the circuit's `asset` is kept, or None where none are."""
    directory = settings.CIRCUIT_MORPHOLOGY_PACK_CACHE_DIR
    if directory is None:
        return None
    return directory / f"{asset.id}.{settings.COMMIT_SHA or 'local'}{KEPT_SUFFIX}"


def kept(path: Path) -> bytes | None:
    """The pack kept at `path`, marked as used, if it is there."""
    try:
        pack = path.read_bytes()
    except FileNotFoundError:
        return None
    with suppress(FileNotFoundError):
        os.utime(path)
    return pack


def keep(path: Path, pack: bytes) -> None:
    """Keep `pack` at `path`, first letting go of the packs used longest ago to make room."""
    path.parent.mkdir(parents=True, exist_ok=True)
    remove_oldest_past(
        path.parent.glob(f"*{KEPT_SUFFIX}*"),
        settings.CIRCUIT_MORPHOLOGY_PACK_CACHE_MAX_BYTES - len(pack),
    )
    write_whole(path, pack)


def build_circuit_morphology_pack(
    client: Client,
    circuit_id: UUID,
    directory: Path,
    max_segments: int,
    *,
    all_levels: bool = False,
) -> bytes:
    """Build the pack of a circuit, or refuse one too large for a request, unless it is kept.

    With `all_levels`, the pack holds every level and `max_segments` is not used.
    """
    circuit = get_circuit(client, circuit_id)
    limit = settings.CIRCUIT_MORPHOLOGY_PACK_MAX_NEURONS
    if circuit.number_neurons > limit:
        refuse(
            Refusal.TOO_MANY_NEURONS,
            f"The circuit has {circuit.number_neurons} neurons, over the {limit} a pack built on"
            " request may hold",
        )
    asset = sonata_circuit_asset(client, circuit)
    path = kept_path(asset) if all_levels else None
    if path is not None and (pack := kept(path)) is not None:
        return pack
    if not BUILDING.acquire(timeout=PATIENCE_SECONDS):
        refuse(
            Refusal.BUSY, "Another pack is being built; try again", HTTPStatus.SERVICE_UNAVAILABLE
        )
    try:
        # the build waited for may have been this one's
        if path is not None and (pack := kept(path)) is not None:
            return pack
        with Processes(workers(), PRELOAD) as processes:
            pack = placed_cells(
                client, circuit_id, asset, directory, max_segments, processes, all_levels=all_levels
            ).pack(processes)
        # under the lock, so that a request waiting for it finds the pack kept
        if path is not None and len(pack) <= settings.CIRCUIT_MORPHOLOGY_PACK_CACHE_MAX_BYTES:
            try:
                keep(path, pack)
            except OSError:
                L.warning("The pack %s could not be kept", path.name, exc_info=True)
        return pack
    finally:
        BUILDING.release()
