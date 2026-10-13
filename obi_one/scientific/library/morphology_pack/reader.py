"""A pack read back into arrays: the reader the tests check the writer against."""

from dataclasses import dataclass

import numpy as np

from obi_one.scientific.library.morphology_pack.codec import (
    Index,
    LevelEntry,
    Runs,
    decode_chunk,
    decode_somas,
    radii_um,
    take_apart,
)


@dataclass(frozen=True)
class PackedLevel:
    """A level read back: a row a segment.

    `segments` holds both ends in micrometres: x, y, z and radius of the near end, then of the
    far end.
    """

    entry: LevelEntry
    segments: np.ndarray
    cells: np.ndarray
    types: np.ndarray


@dataclass(frozen=True)
class Pack:
    index: Index
    somas: np.ndarray
    levels: tuple[PackedLevel, ...]


def segment_ends(runs: Runs, corner: np.ndarray, index: Index) -> np.ndarray:
    """Both ends of every segment of a chunk, in micrometres."""
    begin = np.cumsum(runs.lengths) - runs.lengths
    starts = runs.starts.copy()
    starts[:, :3] += corner
    walked = np.cumsum(runs.steps, axis=0)
    before = walked[begin] - runs.steps[begin]
    far = walked + np.repeat(starts - before, runs.lengths, axis=0)
    near = np.roll(far, 1, axis=0)
    near[begin] = starts
    return np.column_stack(
        [
            near[:, :3] * index.grid_um,
            radii_um(near[:, 3], index.radius_steps),
            far[:, :3] * index.grid_um,
            radii_um(far[:, 3], index.radius_steps),
        ]
    )


def read_level(entry: LevelEntry, blocks: memoryview, index: Index) -> PackedLevel:
    boxes = np.array(entry.chunks.box, dtype=np.int64).reshape(-1, 3)
    segments, cells, types = [np.zeros((0, 8))], [np.zeros(0, np.int64)], [np.zeros(0, np.uint8)]
    at = entry.offset
    for box, size in zip(boxes, entry.chunks.bytes, strict=True):
        runs = decode_chunk(bytes(blocks[at : at + size]))
        at += size
        segments.append(segment_ends(runs, box * entry.chunk_steps, index))
        cells.append(np.repeat(runs.cells, runs.lengths))
        types.append(np.repeat(runs.types, runs.lengths))
    return PackedLevel(
        entry, np.concatenate(segments), np.concatenate(cells), np.concatenate(types)
    )


def read_pack(pack: bytes) -> Pack:
    index, blocks = take_apart(pack)
    somas = blocks[index.somas.offset : index.somas.offset + index.somas.bytes]
    return Pack(
        index=index,
        somas=decode_somas(bytes(somas)),
        levels=tuple(read_level(entry, blocks, index) for entry in index.levels),
    )
