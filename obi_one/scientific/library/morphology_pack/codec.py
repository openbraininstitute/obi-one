"""The bytes of a morphology pack.

The format is specified in docs/internal/circuit-morphology-pack.md.
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
COUNTS = struct.Struct("<II")
WIDEST = 4
DEFLATE_LEVEL = 6
PLAIN_DEFLATE_BYTES = 1024


class Entry(BaseModel):
    """A part of the index. Its fields are spelled in camelCase in a pack."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PopulationEntry(Entry):
    name: str
    cells: int


class SomasEntry(Entry):
    offset: int
    bytes: int


class Chunks(Entry):
    """The chunks of a level: three numbers of `box` and one of the others a chunk."""

    box: list[int]
    bytes: list[int]
    segments: list[int]


class LevelEntry(Entry):
    tolerance_um: float
    prune_um: float
    chunk_steps: int
    segments: int
    runs: int
    offset: int
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

    def part(self, runs: slice, segments: slice) -> "Runs":
        return Runs(
            self.cells[runs],
            self.types[runs],
            self.lengths[runs],
            self.starts[runs],
            self.steps[segments],
        )


def deflate_planes(parts: list[bytes]) -> bytes:
    """One zlib stream, a deflate block a byte plane: each plane gets Huffman tables of its own."""
    if sum(map(len, parts)) <= PLAIN_DEFLATE_BYTES:
        return zlib.compress(b"".join(parts), DEFLATE_LEVEL)
    deflate = zlib.compressobj(
        DEFLATE_LEVEL, zlib.DEFLATED, zlib.MAX_WBITS, zlib.DEF_MEM_LEVEL, zlib.Z_FILTERED
    )
    blocks = [deflate.compress(part) + deflate.flush(zlib.Z_BLOCK) for part in parts[:-1]]
    return b"".join([*blocks, deflate.compress(parts[-1]), deflate.flush()])


def encode_chunk(runs: Runs) -> bytes:
    columns = [np.diff(runs.cells, prepend=0), runs.types, runs.lengths]
    columns += [zigzag(column) for column in (*runs.starts.T, *runs.steps.T)]
    parts = [part for column in columns for part in byte_planes(column)]
    parts[0] = COUNTS.pack(len(runs.cells), len(runs.steps)) + parts[0]
    return deflate_planes(parts)


def decode_chunk(block: bytes) -> Runs:
    data = zlib.decompress(block)
    runs, segments = COUNTS.unpack_from(data)
    at = COUNTS.size
    streams = []
    for count in [runs] * 7 + [segments] * 4:
        numbers, at = read_planes(data, at, count)
        streams.append(numbers)
    signed = [unzigzag(numbers) for numbers in streams[3:]]
    return Runs(
        cells=np.cumsum(streams[0].astype(np.int64)),
        types=streams[1].astype(np.uint8),
        lengths=streams[2].astype(np.int64),
        starts=np.column_stack(signed[:4]),
        steps=np.column_stack(signed[4:]),
    )


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
