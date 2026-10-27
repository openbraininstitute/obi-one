from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Self

import morphio
import numpy as np
from neurom.core.soma import get_radius

from obi_one.scientific.library.morphology_pack.simplify import kept_until

# A radius error counts as an error on the diameter, as in the morphology viewer's simplification.
RADIUS_WEIGHT = 2.0
NO_PARENT = -1


@dataclass(frozen=True)
class Level:
    """A level of detail.

    End branches shorter than `prune_um` are dropped, then the points within `tolerance_um` of
    the path and of the diameter.
    """

    tolerance_um: float
    prune_um: float = 0.0


FINEST = Level(tolerance_um=0.125)
MIDDLE = Level(tolerance_um=0.25)
FAR = Level(tolerance_um=1.0, prune_um=5.0)
LEVELS = (FINEST, MIDDLE, FAR)


@dataclass(frozen=True)
class Morphology:
    """A morphology's neurites as sections of traced points, in its own frame.

    A section that leaves the soma starts with a point at the soma's centre, as wide as the
    section's first traced point, so that a neurite reaches its soma at its own width. Any other
    section starts with its parent's last point. Points and radii stay in MorphIO's float32.
    """

    points: np.ndarray
    radii: np.ndarray
    offsets: np.ndarray
    types: np.ndarray
    parents: np.ndarray
    soma_center: np.ndarray
    soma_radius: float

    @classmethod
    def from_morphio(cls, morphology: morphio.Morphology) -> Self:
        types = np.asarray(morphology.section_types, dtype=np.uint8)
        parents = np.full(len(types), NO_PARENT, dtype=np.int64)
        for parent, children in morphology.connectivity.items():
            parents[children] = parent
        points = np.asarray(morphology.points, dtype=np.float32)
        radii = np.asarray(morphology.diameters, dtype=np.float32) / 2
        offsets = np.asarray(morphology.section_offsets, dtype=np.int64)
        soma = morphology.soma
        if not len(soma.points):
            return cls(points, radii, offsets, types, parents, np.zeros(3), 0.0)
        center = np.asarray(soma.center, dtype=np.float64)
        stems = offsets[:-1][parents == NO_PARENT]
        return cls(
            points=np.insert(points, stems, center, axis=0),
            radii=np.insert(radii, stems, radii[stems]),
            offsets=offsets + np.concatenate([[0], np.cumsum(parents == NO_PARENT)]),
            types=types,
            parents=parents,
            soma_center=center,
            soma_radius=float(get_radius(soma)),
        )

    def lengths(self) -> np.ndarray:
        """Path length of each section."""
        steps = np.linalg.norm(np.diff(self.points.astype(np.float64), axis=0), axis=1)
        along = np.concatenate([[0.0], np.cumsum(steps)])
        return along[self.offsets[1:] - 1] - along[self.offsets[:-1]]


@dataclass(frozen=True)
class Polylines:
    """A morphology at one level: unbranched polylines, in the morphology's own frame.

    `opens` marks the first point of each polyline, and `types` gives every point the section
    type of its polyline.
    """

    points: np.ndarray
    radii: np.ndarray
    opens: np.ndarray
    types: np.ndarray

    @property
    def segments(self) -> int:
        return len(self.points) - int(self.opens.sum())


@dataclass(frozen=True)
class Nesting:
    """A level's segments as they follow a coarser level's.

    `counts` has a number a point of the coarser level: how many of the finer level's segments
    run from the coarser segment's near point to the far point it ends, 0 where none do or it
    opens a polyline. `follows` has the finer level's points that end those segments, a coarser
    segment's together, in the coarser level's order.
    """

    counts: np.ndarray
    follows: np.ndarray


@dataclass(frozen=True)
class MorphologyLevels:
    """The morphology at each level; `nestings[i]` gives level `i` over level `i + 1`."""

    shapes: tuple[Polylines, ...]
    soma_center: np.ndarray
    soma_radius: float
    nestings: tuple[Nesting, ...]


def pruned(morphology: Morphology, prune_um: float) -> np.ndarray:
    """Which sections stay: an end branch shorter than `prune_um` goes unless alone on its fork.

    One pass: a branch this leaves as an end is not pruned in its turn.
    """
    parents = morphology.parents
    children = np.bincount(parents[parents != NO_PARENT], minlength=len(parents))
    roots = int((parents == NO_PARENT).sum())
    siblings = np.where(parents == NO_PARENT, roots, children[parents])
    return ~((children == 0) & (morphology.lengths() < prune_um) & (siblings > 1))


def chains(morphology: Morphology, alive: np.ndarray) -> list[list[int]]:
    """Sections joined end to end where a fork was left with one branch of its own type."""
    types, parents = morphology.types, morphology.parents
    forked = alive & (parents != NO_PARENT)
    branches = np.bincount(parents[forked], minlength=len(parents))
    continues = forked & (branches[parents] == 1) & (types[parents] == types)
    following = np.full(len(parents), NO_PARENT)
    following[parents[continues]] = np.flatnonzero(continues)
    joined = []
    for head in np.flatnonzero(alive & ~continues):
        chain = [int(head)]
        while following[chain[-1]] != NO_PARENT:
            chain.append(int(following[chain[-1]]))
        joined.append(chain)
    return joined


def stretches(morphology: Morphology, prune_um: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The unbranched stretches left after pruning.

    Returns the points' indices in the stretches' order, and each stretch's first and last place
    in that order.
    """
    offsets = morphology.offsets
    if prune_um <= 0:
        return np.arange(len(morphology.points)), offsets[:-1], offsets[1:] - 1
    order, first, last = [], [], []
    count = 0
    for chain in chains(morphology, pruned(morphology, prune_um)):
        first.append(count)
        for place, section in enumerate(chain):
            # a section after the first repeats the last point of the one before
            part = np.arange(offsets[section] + (place > 0), offsets[section + 1])
            order.append(part)
            count += len(part)
        last.append(count - 1)
    if not order:
        empty = np.zeros(0, dtype=np.int64)
        return empty, empty, empty
    return np.concatenate(order), np.array(first), np.array(last)


def simplification(
    morphology: Morphology, prune_um: float, finest: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """One pass over the stretches left after pruning, good for any tolerance from `finest` up.

    Returns the points' indices in the stretches' order, which of them open a stretch, and the
    largest tolerance each is kept at.
    """
    order, first, last = stretches(morphology, prune_um)
    weighted = np.concatenate(
        [morphology.points[order], RADIUS_WEIGHT * morphology.radii[order, None]],
        axis=1,
        dtype=np.float64,
    )
    opens = np.zeros(len(order), dtype=bool)
    opens[first] = True
    return order, opens, kept_until(weighted, first, last, finest)


type Kept = tuple[np.ndarray, np.ndarray, np.ndarray]
"""A level as a pass keeps it: the pass's order and openings, and which points the level keeps."""


def spans(starts: np.ndarray, lengths: np.ndarray) -> np.ndarray:
    """The numbers from each of `starts` on, `lengths` of them, one span after another."""
    begin = np.cumsum(lengths) - lengths
    return np.arange(int(lengths.sum())) + np.repeat(starts - begin, lengths)


def finer_along(
    morphology: Morphology, finer: Kept, path: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Along a coarser level's path: each point's place in the finer level, -1 where it has none,
    and whether it ends a finer segment that starts at the finer point before it on the path, or
    at a point of the same position and radius.
    """
    order, opens, keep = finer
    fine = order[keep]
    place = np.full(len(morphology.points), -1, dtype=np.int32)
    place[fine] = np.arange(len(fine))
    along = place[path]
    there = along >= 0
    before = np.maximum.accumulate(np.where(there, np.arange(len(path)), -1))
    before = np.concatenate([[-1], before])[:-1]
    near = fine[np.maximum(along - 1, 0)]
    walked = path[np.maximum(before, 0)]
    same = np.all(morphology.points[near] == morphology.points[walked], axis=1)
    same &= morphology.radii[near] == morphology.radii[walked]
    return along, there & ~opens[keep][np.maximum(along, 0)] & (before >= 0) & same


def segments_along(level: Kept) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A level's segments: the place in the level of each one's far point, and the places on the
    pass's path of its two ends.
    """
    _, opens, keep = level
    kept = np.flatnonzero(keep)
    joined = np.flatnonzero(~opens[kept[1:]])
    return joined + 1, kept[joined], kept[joined + 1]


def nesting(morphology: Morphology, finer: Kept, coarser: Kept) -> Nesting:
    """Level `finer` as it follows level `coarser`.

    A coarser segment is followed where both its ends are finer points and every finer point
    along its path between them ends a finer segment from the finer point before it on the path
    (`finer_along`): the finer segments rebuild from the coarser one. Two passes walk the same
    points, so the finer level's are found by index.
    """
    along, ends = finer_along(morphology, finer, coarser[0])
    far, near, at = segments_along(coarser)
    there = along >= 0
    broken = np.concatenate([[0], np.cumsum(there & ~ends)])
    inside = np.concatenate([[0], np.cumsum(there)])
    followed = there[near] & there[at] & (broken[at + 1] == broken[near + 1])
    near, at = near[followed], at[followed]
    counts = np.zeros(int(coarser[2].sum()), dtype=np.int32)
    counts[far[followed]] = inside[at + 1] - inside[near + 1]
    on = np.zeros(len(along), dtype=bool)
    on[spans(near + 1, at - near)] = True
    return Nesting(counts, along[there & on])


def simplified(morphology: Morphology, levels: Sequence[Level]) -> MorphologyLevels:
    """The morphology at each of `levels`, in their order, each level following the next."""
    section_of = np.repeat(np.arange(len(morphology.types)), np.diff(morphology.offsets))
    passes = {
        prune_um: simplification(
            morphology,
            prune_um,
            min(level.tolerance_um for level in levels if level.prune_um == prune_um),
        )
        for prune_um in {level.prune_um for level in levels}
    }
    kept = []
    shapes = []
    for level in levels:
        order, opens, until = passes[level.prune_um]
        keep = until > level.tolerance_um
        kept.append((order, opens, keep))
        index = order[keep]
        shapes.append(
            Polylines(
                points=morphology.points[index],
                radii=morphology.radii[index],
                opens=opens[keep],
                types=morphology.types[section_of[index]],
            )
        )
    return MorphologyLevels(
        tuple(shapes),
        morphology.soma_center,
        morphology.soma_radius,
        tuple(nesting(morphology, *pair) for pair in pairwise(kept)),
    )
