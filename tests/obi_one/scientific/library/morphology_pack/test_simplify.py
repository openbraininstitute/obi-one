import numpy as np
import pytest

from obi_one.scientific.library.morphology_pack.simplify import kept_until


def plain_recursion(points, tolerance):
    """Ramer-Douglas-Peucker on one stretch, a split at a time."""
    keep = np.zeros(len(points), dtype=bool)
    keep[[0, -1]] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        chord = points[last] - points[first]
        length = chord @ chord
        offset = points[first + 1 : last] - points[first]
        share = np.clip(offset @ chord / length, 0, 1) if length > 0 else np.zeros(len(offset))
        distance = np.linalg.norm(offset - share[:, None] * chord, axis=1)
        farthest = int(distance.argmax())
        if distance[farthest] > tolerance:
            middle = first + 1 + farthest
            keep[middle] = True
            stack += [(first, middle), (middle, last)]
    return keep


def random_stretches(seed, lengths):
    rng = np.random.default_rng(seed)
    points = np.cumsum(rng.normal(scale=0.3, size=(sum(lengths), 4)), axis=0)
    last = np.cumsum(lengths) - 1
    return points, last - np.array(lengths) + 1, last


class TestKeptUntil:
    @pytest.mark.parametrize("tolerance", [0.125, 0.25, 1.0, 4.0])
    def test_keeps_the_points_of_the_plain_recursion(self, tolerance):
        points, first, last = random_stretches(7, [400, 2, 3, 150, 1000, 40])
        until = kept_until(points, first, last, finest=0.125)
        for a, b in zip(first, last, strict=True):
            expected = plain_recursion(points[a : b + 1], tolerance)
            np.testing.assert_array_equal(until[a : b + 1] > tolerance, expected)

    def test_a_coarser_tolerance_keeps_a_part_of_a_finer_one(self):
        points, first, last = random_stretches(3, [600])
        until = kept_until(points, first, last, finest=0.125)
        assert ((until > 1.0) <= (until > 0.25)).all()
        assert (until > 1.0).sum() < (until > 0.25).sum() < len(points)

    def test_ends_are_kept_at_any_tolerance(self):
        points, first, last = random_stretches(5, [30, 2, 80])
        until = kept_until(points, first, last, finest=0.125)
        assert np.isinf(until[first]).all()
        assert np.isinf(until[last]).all()

    def test_a_straight_stretch_keeps_only_its_ends(self):
        points = np.outer(np.arange(50.0), [1.0, 2.0, -1.0, 0.1])
        until = kept_until(points, np.array([0]), np.array([49]), finest=0.125)
        assert (until > 0.125).sum() == 2

    def test_points_dropped_at_the_finest_tolerance_are_zero(self):
        points = np.zeros((5, 4))
        points[:, 0] = np.arange(5)
        points[2, 1] = 0.05
        until = kept_until(points, np.array([0]), np.array([4]), finest=0.125)
        np.testing.assert_array_equal(until[1:4], 0)

    def test_a_stretch_that_ends_where_it_starts(self):
        points = np.array([[0, 0, 0, 1], [3, 0, 0, 1], [3, 4, 0, 1], [0, 0, 0, 1]], dtype=float)
        until = kept_until(points, np.array([0]), np.array([3]), finest=0.125)
        assert until[2] == pytest.approx(5.0)
        assert until[1] == pytest.approx(2.4)
