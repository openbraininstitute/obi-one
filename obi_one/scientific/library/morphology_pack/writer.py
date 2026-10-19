from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field, replace
from functools import partial

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
from obi_one.scientific.library.morphology_pack.memory import give_back
from obi_one.scientific.library.morphology_pack.parallel import ALONE, Processes

CHUNK_UM = 50.0
MAX_CHUNKS = 4096
CHUNKS_A_JOB = 8
NONE = np.zeros(0, dtype=np.int64)
NO_POINTS = np.zeros((0, 4), dtype=np.int32)
NO_BOXES = np.zeros((0, 3), dtype=np.int64)


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


def placed(points: np.ndarray, rotation: np.ndarray, position: np.ndarray) -> np.ndarray:
    """Points turned by `rotation` and moved, each alike wherever it sits in `points`.

    Not a matrix product: BLAS may round a row by where it sits, and a point a coarser level
    shares with a finer one has to land on the same point of the grid at both.
    """
    turned = points[:, :1] * rotation[:, 0] + points[:, 1:2] * rotation[:, 1]
    return turned + points[:, 2:3] * rotation[:, 2] + position


def distinct_rows(rows: np.ndarray) -> np.ndarray:
    """Each row of `rows`, whole numbers spanning little, once."""
    if not len(rows):
        return NO_BOXES
    least = rows.min(axis=0)
    span = tuple(rows.max(axis=0) - least + 1)
    keys = np.unique(np.ravel_multi_index(tuple((rows - least).T), span))
    return np.column_stack(np.unravel_index(keys, span)) + least


@dataclass
class Placed:
    """The cells of one level, placed on the grid. Each list has an entry a cell.

    `boxes` has the chunks of side `chunk_steps` that the cell's segments end in.
    """

    chunk_steps: int
    values: list[np.ndarray] = field(default_factory=list)
    opens: list[np.ndarray] = field(default_factory=list)
    types: list[np.ndarray] = field(default_factory=list)
    cell: list[int] = field(default_factory=list)
    counts: list[np.ndarray] = field(default_factory=list)
    follows: list[np.ndarray] = field(default_factory=list)
    boxes: list[np.ndarray] = field(default_factory=list)

    def add(
        self,
        cell: int,
        shape: Polylines,
        rotation: np.ndarray,
        position: np.ndarray,
        counts: np.ndarray,
        follows: np.ndarray,
    ) -> None:
        values = np.empty((len(shape.points), 4), dtype=np.int32)
        values[:, :3] = on_grid(placed(shape.points, rotation, position))
        values[:, 3] = radius_steps(shape.radii)
        self.values.append(values)
        self.boxes.append(distinct_rows(values[~shape.opens, :3] // self.chunk_steps))
        self.opens.append(shape.opens)
        self.types.append(shape.types)
        self.cell.append(cell)
        self.counts.append(counts)
        self.follows.append(follows)

    def joined(self) -> Points:
        if not self.values:
            return Points(NO_POINTS, NONE.astype(bool), NONE, NONE, NONE, NONE)
        points = [len(opens) for opens in self.opens]
        follows = np.empty(sum(map(len, self.follows)), dtype=np.int32)
        at = 0
        for first, cell_follows in zip(np.cumsum(points) - points, self.follows, strict=True):
            follows[at : at + len(cell_follows)] = cell_follows + first
            at += len(cell_follows)
        return Points(
            np.concatenate(self.values),
            np.concatenate(self.opens),
            np.concatenate(self.types),
            np.repeat(np.array(self.cell, dtype=np.int32), points),
            np.concatenate(self.counts, dtype=np.int32),
            follows,
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


def boxes_of(levels: Sequence[Placed], chunk_steps: int) -> Boxes:
    """The chunks every level's segments end in, their side doubled from `chunk_steps` until
    there are at most `MAX_CHUNKS`.
    """
    boxes = distinct_rows(
        np.concatenate([NO_BOXES, *(boxes for level in levels for boxes in level.boxes)])
    )
    while len(boxes) > MAX_CHUNKS:
        chunk_steps *= 2
        boxes = distinct_rows(boxes >> 1)
    if not len(boxes):
        return Boxes(chunk_steps, np.zeros(3, dtype=np.int32), np.ones(3, dtype=np.int64))
    least = boxes.min(axis=0)
    return Boxes(chunk_steps, least.astype(np.int32), boxes.max(axis=0) - least + 1)


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


@dataclass(frozen=True)
class Ends:
    """Segments and the points that end them: `at` names each by its far point, and `near` and
    `far` have the level's rows of its two points.
    """

    at: np.ndarray
    near: np.ndarray
    far: np.ndarray

    @classmethod
    def of(cls, points: Points, at: np.ndarray) -> "Ends":
        return cls(at, points.values[at - 1], points.values[at])

    def __getitem__(self, part: slice) -> "Ends":
        """The segments `part` of these."""
        return Ends(self.at[part], self.near[part], self.far[part])

    def reach(self, corner: np.ndarray, chunk_steps: int) -> int:
        """How far, in steps, the points lie outside the cube at `corner` at most."""
        least = np.minimum(self.near[:, :3].min(axis=0), self.far[:, :3].min(axis=0))
        most = np.maximum(self.near[:, :3].max(axis=0), self.far[:, :3].max(axis=0))
        return max(int(np.maximum(corner - least, most - (corner + chunk_steps - 1)).max()), 0)


def runs_in(points: Points, lengths: np.ndarray, segments: Ends, corner: np.ndarray) -> Runs:
    """Runs of `lengths` segments, one after another in `segments`, in the chunk whose corner is
    `corner`.
    """
    first = np.cumsum(lengths) - lengths
    head = segments.at[first]
    starts = segments.near[first]
    starts[:, :3] -= corner
    steps = segments.far - segments.near
    return Runs(points.cell[head], points.types[head], lengths, starts, steps)


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


@dataclass(frozen=True)
class Followers:
    """A level's segments that follow the coarser level's, in the order the coarser is read.

    `far` has a row a segment, its far point, and `counts` a row a coarser segment; `edges` has
    where each of the coarser level's chunks starts in `far`.
    """

    far: np.ndarray
    counts: np.ndarray
    edges: np.ndarray


def followers(points: Points, coarser: Read) -> Followers:
    counts = coarser.counts[coarser.order]
    first = (np.cumsum(coarser.counts, dtype=np.int32) - coarser.counts)[coarser.order]
    ends = np.cumsum(counts, dtype=np.int32)
    # spans in 32 bits, made in place: the finest level's followers are the most held at once
    at = np.arange(int(counts.sum()), dtype=np.int32)
    at += np.repeat(first - (ends - counts), counts)
    far = points.follows[at]
    return Followers(far, counts, np.concatenate([[0], ends])[coarser.edges])


def inner_points(segments: Ends, counts: np.ndarray) -> np.ndarray:
    """The inner points of `segments`, `counts[i]` of them following coarser segment `i`, each
    less the chord's guess.
    """
    # how many segments are left to the coarser segment's far point, this one's included
    left = np.repeat(np.cumsum(counts), counts) - np.arange(len(segments.at))
    inner = left > 1
    last = np.flatnonzero(inner) + left[inner] - 1
    guess = towards(segments.near[inner], segments.far[last], left[inner, None].astype(np.int32))
    return segments.far[inner] - guess


def own_runs(points: Points, boxes: Boxes) -> Cut:
    """The level's segments that follow no coarser segment, cut into runs."""
    claimed = np.zeros(len(points.values), dtype=bool)
    claimed[points.follows] = True
    own = np.flatnonzero(~points.opens & ~claimed).astype(np.int32)
    return cut(own, boxes.key(points.values[own, :3] // boxes.chunk_steps), points.cell)


def edges_of(keys: np.ndarray, wanted: np.ndarray) -> np.ndarray:
    """Where each of `wanted` starts in the sorted `keys`, then their end."""
    return np.append(np.searchsorted(keys, wanted), len(keys))


def places_in(keys: np.ndarray, wanted: np.ndarray) -> np.ndarray:
    """Where each of `wanted` is in the sorted `keys`, -1 where it is not."""
    at = np.searchsorted(keys, wanted)
    found = at < len(keys)
    found[found] = keys[at[found]] == wanted[found]
    return np.where(found, at, -1)


@dataclass(frozen=True)
class Layout:
    """A level's chunks: their keys, each one's place among the coarser level's chunks (-1 where
    the coarser level has none there) and where its runs start among the level's own.
    """

    keys: np.ndarray
    coarser: np.ndarray
    runs: np.ndarray


def layout_of(follow: Followers, coarser: Read, made: Cut) -> Layout:
    keys = np.union1d(coarser.keys[np.diff(follow.edges) > 0], made.key)
    return Layout(keys, places_in(coarser.keys, keys), edges_of(made.key, keys))


@dataclass(frozen=True)
class Order:
    """A level's segments' far points in the order they are read, chunk by chunk: a chunk's
    followers from `edges[c]`, then its runs from `runs[c]` to `edges[c + 1]`.
    """

    far: np.ndarray
    edges: np.ndarray
    runs: np.ndarray


def read_order(layout: Layout, follow: Followers, made: Cut) -> Order:
    own = made.read()
    own_edges = np.append(np.cumsum(made.length) - made.length, len(own))[layout.runs]
    following = np.append(np.diff(follow.edges), 0)[layout.coarser]
    edges = np.concatenate([[0], np.cumsum(following + np.diff(own_edges))])
    runs = edges[:-1] + following
    far = np.empty(edges[-1], dtype=np.int32)
    for c, k in enumerate(layout.coarser):
        if k >= 0:
            far[edges[c] : runs[c]] = follow.far[follow.edges[k] : follow.edges[k + 1]]
        far[runs[c] : edges[c + 1]] = own[own_edges[c] : own_edges[c + 1]]
    return Order(far, edges, runs)


def chunk_parts(
    points: Points,
    layout: Layout,
    coarser: Read,
    follow: Followers,
    made: Cut,
    order: Order,
    boxes: Boxes,
    reach: np.ndarray,
) -> Iterator[Chunk]:
    """Each chunk as it is encoded, its reach set in `reach` on the way."""
    corners = boxes.box(layout.keys) * boxes.chunk_steps
    for c, k in enumerate(layout.coarser):
        segments = Ends.of(points, order.far[order.edges[c] : order.edges[c + 1]])
        reach[c] = segments.reach(corners[c], boxes.chunk_steps)
        split = order.runs[c] - order.edges[c]
        if k >= 0:
            counts = follow.counts[coarser.edges[k] : coarser.edges[k + 1]]
            inner = inner_points(segments[:split], counts)
        else:
            counts, inner = NONE, NO_POINTS
        lengths = made.length[layout.runs[c] : layout.runs[c + 1]]
        yield Chunk(counts, inner, runs_in(points, lengths, segments[split:], corners[c]))


@dataclass(frozen=True)
class Packed:
    """A level's chunks, a row each: key, block, segments and reach; and its number of runs."""

    keys: np.ndarray
    blocks: list[bytes]
    segments: np.ndarray
    reach: np.ndarray
    runs: int


def packed_level(
    points: Points, boxes: Boxes, coarser: Read, follow: Followers, processes: Processes
) -> tuple[Packed, Read]:
    """A level's chunks: its `follow`ers of the coarser level's segments first, in the order the
    coarser level's chunk is read, then the level's own runs, cut as the coarser segments leave
    them. Returns them with the level as the finer level reads over it.
    """
    made = own_runs(points, boxes)
    layout = layout_of(follow, coarser, made)
    order = read_order(layout, follow, made)
    reach = np.zeros(len(layout.keys), dtype=np.int64)
    parts = chunk_parts(points, layout, coarser, follow, made, order, boxes, reach)
    encode = partial(encode_chunk, chunk_steps=boxes.chunk_steps)
    blocks = list(processes.map(encode, parts, per_job=CHUNKS_A_JOB))
    packed = Packed(layout.keys, blocks, np.diff(order.edges), reach, len(made.run))
    return packed, Read(layout.keys, order.far, order.edges, points.counts)


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
        self.chunk_steps = round(chunk_um / GRID_UM)
        self.somas = np.zeros((sum(count for _, count in populations), 4), dtype="<f4")
        self.placed = [Placed(self.chunk_steps) for _ in self.levels]

    def add_cell(
        self, cell: int, morphology: MorphologyLevels, rotation: np.ndarray, position: np.ndarray
    ) -> None:
        """Place a cell: each point is turned by `rotation`, a 3 by 3 matrix, then moved."""
        self.somas[cell, :3] = morphology.soma_center @ rotation.T + position
        self.somas[cell, 3] = morphology.soma_radius
        shapes, nestings = morphology.shapes, morphology.nestings
        if len(nestings) != len(shapes) - 1:
            msg = "A morphology's nestings at odds with its levels"
            raise ValueError(msg)
        none = np.broadcast_to(np.int32(0), len(shapes[0].opens))
        counts = [none, *(n.counts for n in nestings)]
        follows = [*(n.follows for n in nestings), NONE]
        for placed, shape, count, follow in zip(self.placed, shapes, counts, follows, strict=True):
            placed.add(cell, shape, rotation, position, count, follow)

    def add_soma(self, cell: int, position: np.ndarray) -> None:
        """Place a cell that has no morphology: its soma alone, with a radius of zero."""
        self.somas[cell, :3] = position

    def pack(self, processes: Processes = ALONE) -> bytes:
        """The pack of the cells added, its chunks encoded over `processes`.

        A writer packs once. The coarsest level is packed first; each level's cells are joined
        only when it comes to be packed, and its points let go of once the finer level is
        packed over it; what each level frees is handed back to the system.
        """
        if not self.placed:
            msg = "A writer packs once"
            raise RuntimeError(msg)
        placed, self.placed = self.placed, []
        boxes = boxes_of(placed, self.chunk_steps)
        made: list[Packed] = []
        coarser = Read(NONE, NONE, np.zeros(1, dtype=np.int64), NONE)
        while placed:
            points = placed.pop().joined()
            bounds = bounds_of(points.values)
            follow = followers(points, coarser)
            # past its followers, only the coarser level's chunks are read
            coarser = replace(coarser, order=NONE, counts=NONE)
            packed, coarser = packed_level(points, boxes, coarser, follow, processes)
            made.insert(0, packed)
            del points, follow
            give_back()
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
