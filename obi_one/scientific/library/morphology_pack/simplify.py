import numpy as np


def squared_distance_to_chord(
    points: np.ndarray, index: np.ndarray, first: np.ndarray, last: np.ndarray, count: np.ndarray
) -> np.ndarray:
    """How far each of the points `index` lies from the chord of its stretch, squared.

    `index` holds the `count[i]` points of stretch `i` together, one stretch after another.
    """
    origin = points.take(first, axis=0)
    chord = points.take(last, axis=0)
    chord -= origin
    length = np.repeat(np.einsum("ij,ij->i", chord, chord), count)
    offset = points.take(index, axis=0)
    offset -= np.repeat(origin, count, axis=0)
    chord = np.repeat(chord, count, axis=0)
    along = np.einsum("ij,ij->i", offset, chord)
    share = np.clip(np.divide(along, length, out=np.zeros_like(along), where=length > 0), 0, 1)
    chord *= share[:, None]
    offset -= chord
    return np.einsum("ij,ij->i", offset, offset)


def farthest_points(
    points: np.ndarray, first: np.ndarray, last: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """The point strictly between each stretch's ends that lies farthest from its chord.

    Returns its squared distance and its index, a stretch each. Of points equally far, the first.
    """
    count = last - first - 1
    begin = np.cumsum(count) - count
    index = np.arange(int(count.sum()))
    index += np.repeat(first + 1 - begin, count)
    distance = squared_distance_to_chord(points, index, first, last, count)
    farthest = np.maximum.reduceat(distance, begin)
    at = np.flatnonzero(distance == np.repeat(farthest, count))
    return farthest, index[at[np.searchsorted(at, begin)]]


def kept_until(
    points: np.ndarray, first: np.ndarray, last: np.ndarray, finest: float
) -> np.ndarray:
    """The largest tolerance each point survives Ramer-Douglas-Peucker at.

    Every stretch from `first[i]` to `last[i]` is simplified at once: a round splits each open
    stretch at its farthest point, which is the point the recursion would split it at. A point
    is kept at a tolerance when its value here is larger, so one pass at `finest` serves every
    coarser tolerance. Ends are kept at any tolerance; a point dropped at `finest` gets 0.

    Args:
        points: A row of floats a point, of any width. The distance is the Euclidean one over
            all columns.
        first: Index of each stretch's first point.
        last: Index of each stretch's last point.
        finest: The smallest tolerance that will be asked for.
    """
    kept = np.zeros(len(points))
    kept[first] = kept[last] = np.inf
    first, last = first.astype(np.int64), last.astype(np.int64)
    limit = np.full(len(first), np.inf)
    while True:
        open_ = last - first > 1
        first, last, limit = first[open_], last[open_], limit[open_]
        if not len(first):
            return kept
        farthest, middle = farthest_points(points, first, last)
        split = farthest > finest * finest
        middle = middle[split]
        until = np.minimum(limit, np.sqrt(farthest))[split]
        kept[middle] = until
        first = np.concatenate([first[split], middle])
        last = np.concatenate([middle, last[split]])
        limit = np.concatenate([until, until])
