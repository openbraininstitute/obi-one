"""A pack read back into arrays: the reader the tests check the writer against."""

from dataclasses import dataclass

import numpy as np

from obi_one.scientific.library.morphology_pack.codec import (
    Chunk,
    Index,
    LevelEntry,
    Runs,
    decode_chunk,
    decode_somas,
    radii_um,
    take_apart,
    towards,
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


@dataclass(frozen=True)
class Segments:
    """Segments as whole numbers of the grid and of the radius' steps: a row an end."""

    near: np.ndarray
    far: np.ndarray
    cells: np.ndarray
    types: np.ndarray

    @staticmethod
    def none() -> "Segments":
        ends = np.zeros((0, 4), dtype=np.int64)
        return Segments(ends, ends, np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.uint8))

    @staticmethod
    def joined(parts: list["Segments"]) -> "Segments":
        return Segments(
            *(
                np.concatenate([getattr(p, name) for p in parts])
                for name in ("near", "far", "cells", "types")
            )
        )


def run_segments(runs: Runs, corner: np.ndarray) -> Segments:
    begin = np.cumsum(runs.lengths) - runs.lengths
    starts = runs.starts.copy()
    starts[:, :3] += corner
    walked = np.cumsum(runs.steps, axis=0)
    before = walked[begin] - runs.steps[begin]
    far = walked + np.repeat(starts - before, runs.lengths, axis=0)
    near = np.roll(far, 1, axis=0)
    near[begin] = starts
    return Segments(
        near, far, np.repeat(runs.cells, runs.lengths), np.repeat(runs.types, runs.lengths)
    )


def following(chunk: Chunk, coarser: Segments) -> Segments:
    """The segments that follow the coarser ones, rebuilt from them and the inner points."""
    if len(chunk.counts) != len(coarser.far):
        msg = "A chunk's counts at odds with the coarser level's segments in its box"
        raise ValueError(msg)
    followed = np.flatnonzero(chunk.counts)
    counts = chunk.counts[followed]
    inner_counts = counts - 1
    first = np.cumsum(inner_counts) - inner_counts
    inner = np.zeros((int(inner_counts.sum()), 4), dtype=np.int64)
    before = coarser.near[followed].copy()
    far = coarser.far[followed]
    for place in range(int(inner_counts.max()) if len(followed) else 0):
        on = inner_counts > place
        rows = first[on] + place
        inner[rows] = (
            towards(before[on], far[on], (counts[on] - place)[:, None]) + chunk.inner[rows]
        )
        before[on] = inner[rows]
    ends = np.zeros((int(counts.sum()), 4), dtype=np.int64)
    last = np.cumsum(counts) - 1
    is_inner = np.ones(len(ends), dtype=bool)
    is_inner[last] = False
    ends[is_inner] = inner
    ends[last] = far
    near = np.roll(ends, 1, axis=0)
    near[last - counts + 1] = coarser.near[followed]
    return Segments(
        near,
        ends,
        np.repeat(coarser.cells[followed], counts),
        np.repeat(coarser.types[followed], counts),
    )


def in_micrometres(segments: Segments, index: Index) -> np.ndarray:
    return np.column_stack(
        [
            segments.near[:, :3] * index.grid_um,
            radii_um(segments.near[:, 3], index.radius_steps),
            segments.far[:, :3] * index.grid_um,
            radii_um(segments.far[:, 3], index.radius_steps),
        ]
    )


def read_level(
    entry: LevelEntry, blocks: memoryview, coarser: dict[tuple[int, ...], Segments]
) -> dict[tuple[int, ...], Segments]:
    """Each box's segments of a level, read: those following the coarser level's, then its runs."""
    boxes = np.array(entry.chunks.box, dtype=np.int64).reshape(-1, 3)
    read = {}
    at = entry.offset
    for box, size, segments in zip(boxes, entry.chunks.bytes, entry.chunks.segments, strict=True):
        chunk = decode_chunk(bytes(blocks[at : at + size]))
        at += size
        key = tuple(box.tolist())
        parts = Segments.joined(
            [
                following(chunk, coarser.get(key, Segments.none())),
                run_segments(chunk.runs, box * entry.chunk_steps),
            ]
        )
        if len(parts.far) != segments:
            msg = "A chunk's segments at odds with the index"
            raise ValueError(msg)
        read[key] = parts
    return read


def read_pack(pack: bytes) -> Pack:
    index, blocks = take_apart(pack)
    somas = blocks[index.somas.offset : index.somas.offset + index.somas.bytes]
    read: list[dict[tuple[int, ...], Segments]] = [{} for _ in index.levels]
    for level in reversed(range(len(index.levels))):
        entry = index.levels[level]
        coarser = {} if entry.base is None else read[entry.base]
        read[level] = read_level(entry, blocks, coarser)
    levels = []
    for entry, boxes in zip(index.levels, read, strict=True):
        segments = Segments.joined([Segments.none(), *boxes.values()])
        levels.append(
            PackedLevel(entry, in_micrometres(segments, index), segments.cells, segments.types)
        )
    return Pack(index=index, somas=decode_somas(bytes(somas)), levels=tuple(levels))
