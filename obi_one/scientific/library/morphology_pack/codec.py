"""The bytes of a morphology pack.

The format is specified in docs/format.md beside this module.
"""

import struct
import zlib
from dataclasses import dataclass
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

MAGIC = b"MPCK"
VERSION = 1
GRID_UM = 0.025
RADIUS_STEPS = 16
SMALLEST_RADIUS_UM = 1 / 1024
HEADER = struct.Struct("<4sHHI")
# A chunk's coarser segments, inner points, runs and segments of its runs.
COUNTS = struct.Struct("<IIII")
WIDEST = 4
DEFLATE_LEVEL = 6
PLAIN_DEFLATE_BYTES = 1024


class Entry(BaseModel):
    """A part of the index. Its fields are spelled in camelCase in a pack."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PopulationEntry(Entry):
    """A population's cells, and the box of their points at the first level of each section type
    they have; `boxes` is None in a pack written before populations had them.
    """

    name: str
    cells: int
    boxes: dict[int, list[list[int]]] | None = None


class SomasEntry(Entry):
    offset: int
    bytes: int


class Chunks(Entry):
    """The chunks of a level: three numbers of `box` and one of the others a chunk."""

    box: list[int]
    bytes: list[int]
    segments: list[int]
    reach: list[int]


class LevelEntry(Entry):
    tolerance_um: float
    prune_um: float
    chunk_steps: int
    segments: int
    runs: int
    offset: int
    base: int | None
    chunks: Chunks


class Index(Entry):
    layout: Literal["space"] = "space"
    grid_um: float = GRID_UM
    radius_steps: int = RADIUS_STEPS
    bounds: list[list[int]]
    populations: list[PopulationEntry]
    somas: SomasEntry
    levels: list[LevelEntry]


def on_grid(points_um: np.ndarray) -> np.ndarray:
    return np.rint(points_um / GRID_UM).astype(np.int32)


def radius_steps(radii_um: np.ndarray) -> np.ndarray:
    widest = np.maximum(radii_um, SMALLEST_RADIUS_UM, dtype=np.float64)
    return np.rint(np.log2(widest) * RADIUS_STEPS).astype(np.int32)


def radii_um(steps: np.ndarray, steps_a_doubling: int) -> np.ndarray:
    return 2.0 ** (steps / steps_a_doubling)


def zigzag(values: np.ndarray) -> np.ndarray:
    wide = values.astype(np.int64)
    return ((wide << 1) ^ (wide >> 63)).astype(np.uint32)


def unzigzag(values: np.ndarray) -> np.ndarray:
    wide = values.astype(np.int64)
    return (wide >> 1) ^ -(wide & 1)


def byte_planes(values: np.ndarray) -> list[bytes]:
    """A stream as its width byte with its first byte plane, then each further plane."""
    numbers = np.ascontiguousarray(values, dtype="<u4")
    most = int(numbers.max()) if len(numbers) else 0
    width = max(1, (most.bit_length() + 7) // 8)
    stored = numbers.view(np.uint8).reshape(-1, WIDEST)[:, :width].T
    return [bytes([width]) + stored[0].tobytes(), *(plane.tobytes() for plane in stored[1:])]


def planes(values: np.ndarray) -> bytes:
    return b"".join(byte_planes(values))


def read_planes(data: bytes, at: int, count: int) -> tuple[np.ndarray, int]:
    """The `count` numbers of the stream that starts at `at`, and where the next one starts."""
    width = data[at]
    stored = np.frombuffer(data, dtype=np.uint8, count=width * count, offset=at + 1)
    numbers = np.zeros((count, WIDEST), dtype=np.uint8)
    numbers[:, :width] = stored.reshape(width, count).T
    return numbers.view("<u4").ravel(), at + 1 + width * count


@dataclass(frozen=True)
class Runs:
    """Runs of segments, as whole numbers of the grid and of the radius' steps.

    `starts` and `steps` have a row a run and a row a segment: x, y, z and radius. A run's first
    point is given against its chunk's corner.
    """

    cells: np.ndarray
    types: np.ndarray
    lengths: np.ndarray
    starts: np.ndarray
    steps: np.ndarray


def deflate_planes(parts: list[bytes]) -> bytes:
    """One zlib stream, a deflate block a byte plane: each plane gets Huffman tables of its own."""
    if sum(map(len, parts)) <= PLAIN_DEFLATE_BYTES:
        return zlib.compress(b"".join(parts), DEFLATE_LEVEL)
    deflate = zlib.compressobj(
        DEFLATE_LEVEL, zlib.DEFLATED, zlib.MAX_WBITS, zlib.DEF_MEM_LEVEL, zlib.Z_FILTERED
    )
    blocks = [deflate.compress(part) + deflate.flush(zlib.Z_BLOCK) for part in parts[:-1]]
    return b"".join([*blocks, deflate.compress(parts[-1]), deflate.flush()])


@dataclass(frozen=True)
class Chunk:
    """A chunk's block: its additions over the coarser level's segments in its box, then its runs.

    `counts` has a number a coarser segment, in the order the coarser level's box is read in: 0
    where none of this level's segments follow it, else how many do. `inner` has the points
    between, a row each of x, y, z and radius, each less the chord's guess (`towards`). `runs`
    holds this level's segments that follow no coarser one.
    """

    counts: np.ndarray
    inner: np.ndarray
    runs: Runs


def guessed_step(before: np.ndarray) -> np.ndarray:
    """A step's x, y and z guessed from the step before it in its run: three quarters of it."""
    return (3 * before + 2) >> 2


def towards(near: np.ndarray, far: np.ndarray, left: np.ndarray) -> np.ndarray:
    """The chord's guess of the next point: a `left`-th of the way on to `far`, rounded down."""
    return near + (far - near) // left


def travel(steps: np.ndarray, lengths: np.ndarray) -> np.ndarray:
    """Each run's steps summed: from its first point to its last."""
    if not len(lengths):
        return np.zeros((0, steps.shape[1]), dtype=np.int64)
    return np.add.reduceat(steps, np.cumsum(lengths) - lengths, axis=0)


def alike(rows: np.ndarray) -> np.ndarray:
    """A number for each row of `rows`, the same for rows alike."""
    order = np.lexsort(rows.T[::-1])
    ordered = rows[order]
    new = np.ones(len(rows), dtype=bool)
    new[1:] = np.any(ordered[1:] != ordered[:-1], axis=1)
    group = np.empty(len(rows), dtype=np.int64)
    group[order] = np.cumsum(new) - 1
    return group


def back_references(runs: Runs, chunk_steps: int) -> tuple[np.ndarray, np.ndarray]:
    """For each run, 0 or how many runs back the nearest run of its cell ends where it starts.

    Only a start within the chunk's cube is looked for, on x, y and z, an end with the start's
    radius as well preferred. Returns the counts and each start's radius less that end's.
    """
    count = len(runs.cells)
    if not count:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
    ends = runs.starts + travel(runs.steps, runs.lengths)
    inside = np.all((runs.starts[:, :3] >= 0) & (runs.starts[:, :3] < chunk_steps), axis=1)
    order = np.arange(count, dtype=np.int64)
    refs = np.zeros(count, dtype=np.int64)
    for width in (3, 4):
        rows = np.concatenate(
            [
                np.column_stack([runs.cells, ends[:, :width]]),
                np.column_stack([runs.cells, runs.starts[:, :width]]),
            ]
        )
        group = alike(rows)
        span = count + 1
        end_keys = np.sort(group[:count] * span + order)
        at = np.searchsorted(end_keys, group[count:] * span + order, side="left") - 1
        nearest = end_keys[np.maximum(at, 0)]
        found = (at >= 0) & (nearest // span == group[count:]) & inside
        refs = np.where(found, order - nearest % span, refs)
    referred = np.where(refs > 0, runs.starts[:, 3] - ends[order - refs, 3], 0)
    return refs, referred


def run_parts(runs: Runs, chunk_steps: int) -> list[bytes]:
    refs, referred = back_references(runs, chunk_steps)
    first = np.cumsum(runs.lengths) - runs.lengths
    steps = runs.steps.copy()
    later = np.ones(len(steps), dtype=bool)
    later[first] = False
    steps[later, :3] -= guessed_step(runs.steps[np.flatnonzero(later) - 1, :3])
    whole = refs == 0
    columns = [np.diff(runs.cells, prepend=0), runs.types, runs.lengths, refs]
    columns += [zigzag(column) for column in runs.starts[whole].T]
    columns += [zigzag(referred[~whole])]
    columns += [zigzag(column) for column in steps.T]
    return [part for column in columns for part in byte_planes(column)]


def read_streams(
    data: bytes, at: int, count: int, streams: int, *, signed: bool = False
) -> tuple[np.ndarray, int]:
    """`streams` streams of `count` numbers from `at`, a column each, and where they end."""
    columns = np.zeros((count, streams), dtype=np.int64)
    for stream in range(streams):
        numbers, at = read_planes(data, at, count)
        columns[:, stream] = unzigzag(numbers) if signed else numbers
    return columns, at


def unguessed(steps: np.ndarray, lengths: np.ndarray) -> np.ndarray:
    """Steps as stored back to steps: each with its guess from the one before added, in order."""
    first = np.cumsum(lengths) - lengths
    for place in range(1, int(lengths.max()) if len(lengths) else 0):
        rows = first[lengths > place] + place
        steps[rows, :3] += guessed_step(steps[rows - 1, :3])
    return steps


def read_runs(data: bytes, at: int, count: int, segments: int) -> tuple[Runs, int]:
    """The `count` runs of `segments` segments laid from `at`, and where they end."""
    head, at = read_streams(data, at, count, 4)
    whole = head[:, 3] == 0
    starts = np.zeros((count, 4), dtype=np.int64)
    starts[whole], at = read_streams(data, at, int(whole.sum()), 4, signed=True)
    referred, at = read_streams(data, at, count - int(whole.sum()), 1, signed=True)
    stored, at = read_streams(data, at, segments, 4, signed=True)
    lengths = head[:, 2]
    steps = unguessed(stored, lengths)
    travelled = travel(steps, lengths)
    for run, radius in zip(np.flatnonzero(~whole), referred[:, 0], strict=True):
        back = run - head[run, 3]
        starts[run] = starts[back] + travelled[back]
        starts[run, 3] += radius
    return Runs(np.cumsum(head[:, 0]), head[:, 1].astype(np.uint8), lengths, starts, steps), at


def encode_chunk(chunk: Chunk, chunk_steps: int) -> bytes:
    """A chunk's block: `chunk_steps` is the side of its cube, which a run's start is given in."""
    runs = chunk.runs
    parts = byte_planes(chunk.counts)
    parts += [part for column in chunk.inner.T for part in byte_planes(zigzag(column))]
    parts += run_parts(runs, chunk_steps)
    header = COUNTS.pack(len(chunk.counts), len(chunk.inner), len(runs.cells), len(runs.steps))
    parts[0] = header + parts[0]
    return deflate_planes(parts)


def decode_chunk(block: bytes) -> Chunk:
    data = zlib.decompress(block)
    coarser, inner, count, segments = COUNTS.unpack_from(data)
    counts, at = read_streams(data, COUNTS.size, coarser, 1)
    points, at = read_streams(data, at, inner, 4, signed=True)
    runs, at = read_runs(data, at, count, segments)
    if at != len(data):
        msg = "A chunk's block with bytes left over"
        raise ValueError(msg)
    return Chunk(counts[:, 0], points, runs)


def encode_somas(somas: np.ndarray) -> bytes:
    """The block of somas: a row a cell, x, y, z and radius in micrometres."""
    return zlib.compress(np.ascontiguousarray(somas, dtype="<f4").tobytes(), DEFLATE_LEVEL)


def decode_somas(block: bytes) -> np.ndarray:
    return np.frombuffer(zlib.decompress(block), dtype="<f4").reshape(-1, 4)


def assemble(index: Index, blocks: list[bytes]) -> bytes:
    packed = zlib.compress(index.model_dump_json(by_alias=True).encode(), DEFLATE_LEVEL)
    return b"".join([HEADER.pack(MAGIC, VERSION, 0, len(packed)), packed, *blocks])


def take_apart(pack: bytes) -> tuple[Index, memoryview]:
    """The index of a pack, and its blocks as one stretch of bytes."""
    magic, version, _, length = HEADER.unpack_from(pack)
    if magic != MAGIC or version != VERSION:
        msg = f"Not a morphology pack of version {VERSION}: {magic!r}, version {version}"
        raise ValueError(msg)
    index = Index.model_validate_json(zlib.decompress(pack[HEADER.size : HEADER.size + length]))
    return index, memoryview(pack)[HEADER.size + length :]
