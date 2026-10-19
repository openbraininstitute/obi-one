from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from obi_one.scientific.library.morphology_pack.codec import (
    GRID_UM,
    Chunk,
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
    towards,
)
from obi_one.scientific.library.morphology_pack.geometry import (
    Level,
    MorphologyLevels,
    Polylines,
    spans,
)

CHUNK_UM = 50.0
MAX_CHUNKS = 4096
NONE = np.zeros(0, dtype=np.int64)
NO_POINTS = np.zeros((0, 4), dtype=np.int64)


@dataclass(frozen=True)
class Points:
    """The points of a level, every cell's: a row a point.

    `counts` gives how many of the finer level's segments follow the segment each point ends,
    and `follows` the points of this level that end the segments following the coarser level's.
    """

    values: np.ndarray
    opens: np.ndarray
    types: np.ndarray
    cell: np.ndarray
    counts: np.ndarray
    follows: np.ndarray


@dataclass
class Placed:
    """The cells of one level, placed on the grid. Each list has an entry a cell."""

    grid: list[np.ndarray] = field(default_factory=list)
    radius: list[np.ndarray] = field(default_factory=list)
    opens: list[np.ndarray] = field(default_factory=list)
    types: list[np.ndarray] = field(default_factory=list)
    cell: list[int] = field(default_factory=list)
    counts: list[np.ndarray | None] = field(default_factory=list)
    follows: list[np.ndarray | None] = field(default_factory=list)

    def add(
        self,
        cell: int,
        shape: Polylines,
        rotation: np.ndarray,
        position: np.ndarray,
        counts: np.ndarray | None,
        follows: np.ndarray | None,
    ) -> None:
        self.grid.append(on_grid(shape.points @ rotation.T + position))
        self.radius.append(radius_steps(shape.radii))
        self.opens.append(shape.opens)
        self.types.append(shape.types)
        self.cell.append(cell)
        self.counts.append(counts)
        self.follows.append(follows)

    def joined(self) -> Points:
        if not self.grid:
            return Points(NO_POINTS, NONE.astype(bool), NONE, NONE, NONE, NONE)
        points = [len(opens) for opens in self.opens]
        values = np.empty((sum(points), 4), dtype=np.int32)
        np.concatenate(self.grid, out=values[:, :3])
        np.concatenate(self.radius, out=values[:, 3])
        first = np.cumsum(points) - points
        counts = [
            np.zeros(n, dtype=np.int64) if c is None else c
            for c, n in zip(self.counts, points, strict=True)
        ]
        follows = [f + at for f, at in zip(self.follows, first, strict=True) if f is not None]
        return Points(
            values,
            np.concatenate(self.opens),
            np.concatenate(self.types),
            np.repeat(np.array(self.cell, dtype=np.int32), points),
            np.concatenate(counts),
            np.concatenate([NONE, *follows]),
        )


@dataclass(frozen=True)
class Boxes:
    """The chunks of the pack: numbered in the order of their boxes, x first."""

    chunk_steps: int
    least: np.ndarray
    span: np.ndarray

    def key(self, box: np.ndarray) -> np.ndarray:
        return np.ravel_multi_index(tuple((box - self.least).T), tuple(self.span))

    def box(self, key: np.ndarray) -> np.ndarray:
        return np.column_stack(np.unravel_index(key, tuple(self.span))) + self.least


def boxes_of(levels: Sequence[Points], chunk_um: float) -> Boxes:
    """Chunks of `chunk_um`, doubled until every level's segments lie in at most `MAX_CHUNKS`."""
    chunk_steps = round(chunk_um / GRID_UM)
    boxes = np.unique(
        np.concatenate([np.unique(p.values[~p.opens, :3] // chunk_steps, axis=0) for p in levels]),
        axis=0,
    )
    while len(boxes) > MAX_CHUNKS:
        chunk_steps *= 2
        boxes = np.unique(boxes >> 1, axis=0)
    if not len(boxes):
        return Boxes(chunk_steps, np.zeros(3, dtype=np.int64), np.ones(3, dtype=np.int64))
    return Boxes(chunk_steps, boxes.min(axis=0), boxes.max(axis=0) - boxes.min(axis=0) + 1)


@dataclass(frozen=True)
class Cut:
    """Segments cut into runs: segments one after another in a polyline and a chunk.

    A segment is named by its far point. `far` has the segments' far points; the other arrays
    have a row a run: its first segment, its length and its chunk's key. Runs are ordered by
    chunk and then by cell.
    """

    far: np.ndarray
    run: np.ndarray
    length: np.ndarray
    key: np.ndarray

    def read(self) -> np.ndarray:
        """The segments' far points, run by run."""
        return self.far[spans(self.run, self.length)]


def cut(far: np.ndarray, key: np.ndarray, cell: np.ndarray) -> Cut:
    """Cut the segments `far`, each in the chunk `key` gives it, into runs."""
    begins = np.ones(len(far), dtype=bool)
    begins[1:] = (key[1:] != key[:-1]) | (far[1:] - 1 != far[:-1])
    run = np.flatnonzero(begins)
    length = np.diff(np.append(run, len(far)))
    order = np.lexsort((cell[far[run]], key[run]))
    return Cut(far, run[order], length[order], key[run[order]])


def runs_of(points: Points, made: Cut, corners: np.ndarray) -> Runs:
    """The runs of `made`; `corners` has the corner of each run's chunk."""
    end = made.read()
    head = made.far[made.run]
    starts = points.values[head - 1]
    starts[:, :3] -= corners
    steps = points.values[end] - points.values[end - 1]
    return Runs(points.cell[head], points.types[head], made.length, starts, steps)


@dataclass(frozen=True)
class Read:
    """A level as the reader rebuilds it.

    `keys` has its chunks' keys, `order` its segments' far points chunk by chunk and `edges`
    where each chunk starts in it; `counts` how many of the finer level's segments follow the
    segment each of its points ends.
    """

    keys: np.ndarray
    order: np.ndarray
    edges: np.ndarray
    counts: np.ndarray


def reach_of(
    points: Points, order: np.ndarray, edges: np.ndarray, corners: np.ndarray, chunk_steps: int
) -> np.ndarray:
    """How far, in steps, the ends of each chunk's segments lie outside its cube at most."""
    if not len(order):
        return NONE
    near, far = points.values[order - 1, :3], points.values[order, :3]
    least = np.minimum.reduceat(np.minimum(near, far), edges[:-1], axis=0)
    most = np.maximum.reduceat(np.maximum(near, far), edges[:-1], axis=0)
    out = np.maximum(corners - least, most - (corners + chunk_steps - 1))
    return np.maximum(out.max(axis=1), 0)


@dataclass(frozen=True)
class Followers:
    """A level's segments that follow the coarser level's, in the order the coarser is read.

    `far` and `keys` have a row a segment: its far point and its chunk's key. `counts` has a row a
    coarser segment, and `inner` a row an inner point as stored, with `inner_edges` where each
    of the coarser level's chunks starts in it.
    """

    far: np.ndarray
    keys: np.ndarray
    counts: np.ndarray
    inner: np.ndarray
    inner_edges: np.ndarray


def followers(points: Points, coarser: Read) -> Followers:
    counts = coarser.counts[coarser.order]
    first = np.cumsum(coarser.counts) - coarser.counts
    far = points.follows[spans(first[coarser.order], counts)]
    keys = np.repeat(np.repeat(coarser.keys, np.diff(coarser.edges)), counts)
    last = np.repeat(np.cumsum(counts) - 1, counts)
    inner = np.arange(len(far)) < last
    # how many segments are left to the coarser segment's far point, this one's included
    left = np.repeat(np.cumsum(counts), counts) - np.arange(len(far))
    at = far[inner]
    stored = points.values[at] - towards(
        points.values[at - 1], points.values[far[last[inner]]], left[inner, None]
    )
    inner_edges = np.concatenate([[0], np.cumsum(np.maximum(counts - 1, 0))])[coarser.edges]
    return Followers(far, keys, counts, stored, inner_edges)


def own_runs(points: Points, boxes: Boxes) -> tuple[Cut, Runs]:
    """The level's segments that follow no coarser segment, as runs."""
    claimed = np.zeros(len(points.values), dtype=bool)
    claimed[points.follows] = True
    own = np.flatnonzero(~points.opens & ~claimed)
    made = cut(own, boxes.key(points.values[own, :3] // boxes.chunk_steps), points.cell)
    return made, runs_of(points, made, boxes.box(made.key) * boxes.chunk_steps)


def edges_of(keys: np.ndarray, wanted: np.ndarray) -> np.ndarray:
    """Where each of `wanted` starts in the sorted `keys`, then their end."""
    return np.append(np.searchsorted(keys, wanted), len(keys))


def read_order(follow: Followers, made: Cut) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The level's chunk keys, and its segments' far points in the order they are read, with
    where each chunk starts: the followers of a chunk first, then its runs.
    """
    keys = np.concatenate([follow.keys, np.repeat(made.key, made.length)])
    first = np.lexsort((np.arange(len(keys)) >= len(follow.keys), keys))
    keys = keys[first]
    chunks = np.unique(keys)
    return chunks, np.concatenate([follow.far, made.read()])[first], edges_of(keys, chunks)


def chunk_blocks(
    chunks: np.ndarray, follow: Followers, coarser: Read, own: tuple[Cut, Runs], chunk_steps: int
) -> list[bytes]:
    made, runs = own
    run_edges = edges_of(made.key, chunks)
    segment_edges = np.append(np.cumsum(made.length) - made.length, len(runs.steps))[run_edges]
    in_coarser = np.searchsorted(coarser.keys, chunks)
    blocks = []
    for c, (key, k) in enumerate(zip(chunks, in_coarser, strict=True)):
        if k < len(coarser.keys) and coarser.keys[k] == key:
            counts = follow.counts[coarser.edges[k] : coarser.edges[k + 1]]
            inner = follow.inner[follow.inner_edges[k] : follow.inner_edges[k + 1]]
        else:
            counts, inner = NONE, NO_POINTS
        part = runs.part(
            slice(run_edges[c], run_edges[c + 1]), slice(segment_edges[c], segment_edges[c + 1])
        )
        blocks.append(encode_chunk(Chunk(counts, inner, part), chunk_steps))
    return blocks


@dataclass(frozen=True)
class Packed:
    """A level's chunks, a row each: key, block, segments and reach; its runs and how it is read."""

    keys: np.ndarray
    blocks: list[bytes]
    segments: np.ndarray
    reach: np.ndarray
    runs: int
    read: Read


def packed_level(points: Points, boxes: Boxes, coarser: Read | None) -> Packed:
    """A level's chunks: the segments that follow the coarser level's first, in the order the
    coarser level's chunk is read, then the level's own runs, cut as the coarser segments leave
    them.
    """
    coarser = coarser or Read(NONE, NONE, np.zeros(1, dtype=np.int64), NONE)
    follow = followers(points, coarser)
    own = own_runs(points, boxes)
    chunks, order, edges = read_order(follow, own[0])
    blocks = chunk_blocks(chunks, follow, coarser, own, boxes.chunk_steps)
    corners = boxes.box(chunks) * boxes.chunk_steps
    reach = reach_of(points, order, edges, corners, boxes.chunk_steps)
    read = Read(chunks, order, edges, points.counts)
    return Packed(chunks, blocks, np.diff(edges), reach, len(own[0].run), read)


def bounds_of(values: np.ndarray) -> np.ndarray:
    """The box of the points on the grid; the origin alone where there are none."""
    if not len(values):
        return np.zeros((2, 3), dtype=np.int64)
    return np.array([values[:, :3].min(axis=0), values[:, :3].max(axis=0)])


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
            levels: The levels every cell is added at, finest first.
            chunk_um: The edge of a chunk. It is doubled for a pack whose segments would
                otherwise lie in more than `MAX_CHUNKS` chunks at some level.
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
        nestings = morphology.nestings
        if len(nestings) != len(morphology.shapes) - 1:
            msg = "A morphology's nestings at odds with its levels"
            raise ValueError(msg)
        for i, (placed, shape) in enumerate(zip(self.placed, morphology.shapes, strict=True)):
            counts = nestings[i - 1].counts if i > 0 else None
            follows = nestings[i].follows if i < len(nestings) else None
            placed.add(cell, shape, rotation, position, counts, follows)

    def add_soma(self, cell: int, position: np.ndarray) -> None:
        """Place a cell that has no morphology: its soma alone, with a radius of zero."""
        self.somas[cell, :3] = position

    def pack(self) -> bytes:
        """The pack of the cells added.

        A writer packs once: it lets go of the cells as it joins them, and of each level's points
        once the finer level is packed over it. The coarsest level is packed first.
        """
        if not self.placed:
            msg = "A writer packs once"
            raise RuntimeError(msg)
        levels: list[Points] = [placed.joined() for placed in self.placed]
        self.placed = []
        boxes = boxes_of(levels, self.chunk_um)
        bounds = bounds_of(levels[0].values)
        made: list[Packed] = []
        coarser = None
        while levels:
            made.insert(0, packed_level(levels.pop(), boxes, coarser))
            coarser = made[0].read
        blocks = [encode_somas(self.somas)]
        offset = len(blocks[0])
        entries = []
        for i, (level, packed) in enumerate(zip(self.levels, made, strict=True)):
            entries.append(
                LevelEntry(
                    tolerance_um=level.tolerance_um,
                    prune_um=level.prune_um,
                    chunk_steps=boxes.chunk_steps,
                    segments=int(packed.segments.sum()),
                    runs=packed.runs,
                    offset=offset,
                    base=i + 1 if i + 1 < len(made) else None,
                    chunks=Chunks(
                        box=boxes.box(packed.keys).ravel().tolist(),
                        bytes=[len(block) for block in packed.blocks],
                        segments=packed.segments.tolist(),
                        reach=packed.reach.tolist(),
                    ),
                )
            )
            offset += sum(map(len, packed.blocks))
            blocks += packed.blocks
        index = Index(
            bounds=bounds.tolist(),
            populations=[
                PopulationEntry(name=name, cells=count) for name, count in self.populations
            ],
            somas=SomasEntry(offset=0, bytes=len(blocks[0])),
            levels=entries,
        )
        return assemble(index, blocks)
