from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import pairwise

import numpy as np

from obi_one.scientific.library.morphology_pack.codec import (
    GRID_UM,
    Chunks,
    Index,
    LevelEntry,
    PopulationEntry,
    Runs,
    SomasEntry,
    assemble,
    encode_chunk,
    encode_somas,
    on_grid,
    radius_steps,
)
from obi_one.scientific.library.morphology_pack.geometry import Level, MorphologyLevels, Polylines

CHUNK_UM = 50.0
MAX_CHUNKS = 4096


@dataclass
class Placed:
    """The cells of one level, placed on the grid. Each list has an entry a cell."""

    grid: list[np.ndarray] = field(default_factory=list)
    radius: list[np.ndarray] = field(default_factory=list)
    opens: list[np.ndarray] = field(default_factory=list)
    types: list[np.ndarray] = field(default_factory=list)
    cell: list[int] = field(default_factory=list)

    def add(self, cell: int, shape: Polylines, rotation: np.ndarray, position: np.ndarray) -> None:
        self.grid.append(on_grid(shape.points @ rotation.T + position))
        self.radius.append(radius_steps(shape.radii))
        self.opens.append(shape.opens)
        self.types.append(shape.types)
        self.cell.append(cell)

    def joined(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Every point's x, y, z and radius; which points open a polyline; type; and cell."""
        if not self.grid:
            none = np.zeros(0, dtype=np.int32)
            return np.zeros((0, 4), dtype=np.int32), none.astype(bool), none, none
        points = [len(opens) for opens in self.opens]
        values = np.empty((sum(points), 4), dtype=np.int32)
        np.concatenate(self.grid, out=values[:, :3])
        np.concatenate(self.radius, out=values[:, 3])
        return (
            values,
            np.concatenate(self.opens),
            np.concatenate(self.types),
            np.repeat(np.array(self.cell, dtype=np.int32), points),
        )


@dataclass(frozen=True)
class Cut:
    """Segments cut into runs: segments one after another in a polyline and a chunk.

    A segment is named by its far point and belongs to the chunk that point lies in. `far` has
    every segment's far point. The other arrays have a row a run: its first segment, its length
    and its chunk's box. Runs are ordered by chunk and then by cell.
    """

    far: np.ndarray
    run: np.ndarray
    length: np.ndarray
    box: np.ndarray
    chunk_steps: int

    def first_runs(self) -> np.ndarray:
        """Each chunk's first run."""
        changes = np.any(self.box[1:] != self.box[:-1], axis=1)
        return np.flatnonzero(np.append(len(self.box) > 0, changes))


def cut(
    far: np.ndarray, box: np.ndarray, opens: np.ndarray, cell: np.ndarray, chunk_steps: int
) -> Cut:
    """Cut the segments `far`, each in the chunk `box` gives it, into runs."""
    begins = np.ones(len(far), dtype=bool)
    begins[1:] = np.any(box[1:] != box[:-1], axis=1) | opens[far[1:] - 1]
    run = np.flatnonzero(begins)
    length = np.diff(np.append(run, len(far)))
    # by chunk, x first, then by cell
    order = np.lexsort((cell[far[run]], *box[run].T[::-1]))
    return Cut(far, run[order], length[order], box[run[order]], chunk_steps)


def cut_into_few(values: np.ndarray, opens: np.ndarray, cell: np.ndarray, chunk_um: float) -> Cut:
    """Cut with chunks of `chunk_um`, doubled until there are at most `MAX_CHUNKS` of them."""
    chunk_steps = round(chunk_um / GRID_UM)
    far = np.flatnonzero(~opens)
    box = values[far, :3] // chunk_steps
    while True:
        made = cut(far, box, opens, cell, chunk_steps)
        if len(made.first_runs()) <= MAX_CHUNKS:
            return made
        chunk_steps *= 2
        box >>= 1


def runs_of(values: np.ndarray, types: np.ndarray, cell: np.ndarray, made: Cut) -> Runs:
    begin = np.cumsum(made.length) - made.length
    end = made.far[np.arange(len(made.far)) - np.repeat(begin - made.run, made.length)]
    head = made.far[made.run]
    starts = values[head - 1]
    starts[:, :3] -= made.box * made.chunk_steps
    steps = values[end]
    end -= 1
    steps -= values[end]
    return Runs(cell[head], types[head], made.length, starts, steps)


def bounds_of(values: np.ndarray) -> np.ndarray:
    """The box of the points on the grid; the origin alone where there are none."""
    if not len(values):
        return np.zeros((2, 3), dtype=np.int64)
    return np.array([values[:, :3].min(axis=0), values[:, :3].max(axis=0)])


def packed_level(
    level: Level, points: tuple[np.ndarray, ...], chunk_um: float, offset: int
) -> tuple[LevelEntry, list[bytes], np.ndarray]:
    """A level's entry in the index, its chunks' blocks, and the box of its points on the grid.

    Args:
        level: The level the points were simplified to.
        points: What `Placed.joined` gives.
        chunk_um: The edge of a chunk, before any doubling.
        offset: Where the level's first block starts.
    """
    values, opens, types, cell = points
    made = cut_into_few(values, opens, cell, chunk_um)
    runs = runs_of(values, types, cell, made)
    edges = np.append(made.first_runs(), len(made.run))
    segment_edges = np.append(np.cumsum(made.length) - made.length, len(made.far))[edges]
    blocks = [
        encode_chunk(runs.part(slice(*of_runs), slice(*of_segments)))
        for of_runs, of_segments in zip(pairwise(edges), pairwise(segment_edges), strict=True)
    ]
    entry = LevelEntry(
        tolerance_um=level.tolerance_um,
        prune_um=level.prune_um,
        chunk_steps=made.chunk_steps,
        segments=len(made.far),
        runs=len(made.run),
        offset=offset,
        chunks=Chunks(
            box=made.box[edges[:-1]].ravel().tolist(),
            bytes=[len(block) for block in blocks],
            segments=np.diff(segment_edges).tolist(),
        ),
    )
    return entry, blocks, bounds_of(values)


class PackWriter:
    """Builds a pack from cells added one at a time, each already simplified to the levels."""

    def __init__(
        self,
        populations: Sequence[tuple[str, int]],
        levels: Sequence[Level],
        chunk_um: float = CHUNK_UM,
    ) -> None:
        """Start an empty pack.

        Args:
            populations: Name and number of cells of each population. A cell's number counts
                through them in this order.
            levels: The levels every cell is added at.
            chunk_um: The edge of a chunk. It is doubled for a level that would otherwise come
                to more than `MAX_CHUNKS` chunks.
        """
        self.populations = list(populations)
        self.levels = tuple(levels)
        self.chunk_um = chunk_um
        self.somas = np.zeros((sum(count for _, count in populations), 4), dtype="<f4")
        self.placed = [Placed() for _ in self.levels]

    def add_cell(
        self, cell: int, morphology: MorphologyLevels, rotation: np.ndarray, position: np.ndarray
    ) -> None:
        """Place a cell: each point is turned by `rotation`, a 3 by 3 matrix, then moved."""
        self.somas[cell, :3] = morphology.soma_center @ rotation.T + position
        self.somas[cell, 3] = morphology.soma_radius
        for placed, shape in zip(self.placed, morphology.shapes, strict=True):
            placed.add(cell, shape, rotation, position)

    def add_soma(self, cell: int, position: np.ndarray) -> None:
        """Place a cell that has no morphology: its soma alone, with a radius of zero."""
        self.somas[cell, :3] = position

    def pack(self) -> bytes:
        """The pack of the cells added.

        A writer packs once: it lets go of each level's cells as it packs them, so that they
        are not held beside their blocks.
        """
        blocks = [encode_somas(self.somas)]
        entries = []
        bounds = np.zeros((2, 3), dtype=np.int64)
        offset = len(blocks[0])
        for level in self.levels:
            entry, chunks, box = packed_level(
                level, self.placed.pop(0).joined(), self.chunk_um, offset
            )
            if not entries:
                bounds = box
            entries.append(entry)
            offset += sum(entry.chunks.bytes)
            blocks += chunks
        index = Index(
            bounds=bounds.tolist(),
            populations=[
                PopulationEntry(name=name, cells=count) for name, count in self.populations
            ],
            somas=SomasEntry(offset=0, bytes=len(blocks[0])),
            levels=entries,
        )
        return assemble(index, blocks)
