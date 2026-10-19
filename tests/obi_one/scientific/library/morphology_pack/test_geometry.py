from itertools import pairwise

import numpy as np
import pytest

from obi_one.scientific.library.morphology_pack.geometry import (
    FAR,
    FINEST,
    LEVELS,
    MIDDLE,
    NO_PARENT,
    Level,
    chains,
    pruned,
    simplified,
)

from tests.obi_one.scientific.library.morphology_pack.utils import (
    AXON,
    DENDRITE,
    load,
    load_with_a_branch_apart,
)

NO_SOMA = """\
1 3 5 0 0 1 -1
2 3 10 0 0 1 1
3 3 10 9 0 1 2
"""
# The soma as three points, a centre and two ends: a cylinder 5 um in radius and 10 um long.
THREE_POINT_SOMA = """\
1 1 0 0 0 5 -1
2 1 0 -5 0 5 1
3 1 0 5 0 5 1
4 3 5 0 0 1 1
5 3 20 0 0 1 4
"""


def polylines(shape):
    """Each polyline of a shape as its type and its points."""
    edges = np.append(np.flatnonzero(shape.opens), len(shape.points))
    return [
        (int(shape.types[a]), shape.points[a:b].tolist(), shape.radii[a:b].tolist())
        for a, b in pairwise(edges)
    ]


class TestMorphology:
    def test_a_neurite_reaches_the_soma_at_its_own_width(self):
        morphology = load()
        roots = np.flatnonzero(morphology.parents == NO_PARENT)
        assert len(roots) == 2
        for root in roots:
            stem = morphology.offsets[root]
            np.testing.assert_array_equal(morphology.points[stem], [0, 0, 0])
            assert morphology.radii[stem] == morphology.radii[stem + 1]

    def test_a_branch_starts_with_its_fork(self):
        morphology = load()
        branches = np.flatnonzero(morphology.parents != NO_PARENT)
        assert len(branches) == 2
        for branch in branches:
            np.testing.assert_array_equal(morphology.points[morphology.offsets[branch]], [20, 0, 0])
            assert morphology.types[morphology.parents[branch]] == DENDRITE

    def test_sections_keep_their_types_and_every_traced_point(self):
        morphology = load()
        assert sorted(morphology.types.tolist()) == [AXON, DENDRITE, DENDRITE, DENDRITE]
        # 11 traced points, the fork once more for each of its branches, and a stem a neurite
        assert len(morphology.points) == 11 + 2 + 2
        assert morphology.offsets[-1] == len(morphology.points)

    def test_soma(self):
        morphology = load()
        np.testing.assert_array_equal(morphology.soma_center, [0, 0, 0])
        assert morphology.soma_radius == pytest.approx(5.0)

    def test_a_soma_of_cylinders_is_the_sphere_of_their_area(self):
        assert load(THREE_POINT_SOMA).soma_radius == pytest.approx(5.0)

    def test_lengths_follow_the_path(self):
        lengths = sorted(load().lengths().tolist())
        bend = np.hypot(3, 50)
        assert lengths == pytest.approx([2.0, 20.0, 30.0, 50.0 + 2 * bend])

    def test_without_a_soma_there_are_no_stems(self):
        morphology = load(NO_SOMA)
        assert len(morphology.points) == 3
        np.testing.assert_array_equal(morphology.points[0], [5, 0, 0])
        assert morphology.soma_radius == 0


class TestPruning:
    def test_a_short_end_branch_goes(self):
        morphology = load()
        alive = pruned(morphology, FAR.prune_um)
        np.testing.assert_array_equal(morphology.lengths()[~alive], [2.0])

    def test_nothing_goes_without_a_length(self):
        assert pruned(load(), 0).all()

    def test_a_short_branch_alone_on_its_fork_stays(self):
        assert pruned(load(NO_SOMA), 100).all()

    def test_a_fork_left_with_one_branch_is_joined_to_it(self):
        morphology = load()
        joined = chains(morphology, pruned(morphology, FAR.prune_um))
        assert sorted(len(chain) for chain in joined) == [1, 2]
        whole = chains(morphology, pruned(morphology, 0))
        assert sorted(len(chain) for chain in whole) == [1, 1, 1, 1]


class TestSimplified:
    def test_points_on_a_straight_stretch_of_one_width_are_dropped(self):
        shape = simplified(load(), [FINEST]).shapes[0]
        dendrite = (DENDRITE, [[0, 0, 0], [20, 0, 0]], [1.0, 1.0])
        assert dendrite in polylines(shape)

    def test_a_bend_is_kept(self):
        for shape in simplified(load(), LEVELS).shapes:
            axon = [points for kind, points, _ in polylines(shape) if kind == AXON]
            assert axon == [[[0, 0, 0], [0, -50, 0], [3, -100, 0], [0, -150, 0]]]

    def test_a_change_of_width_is_kept_until_the_tolerance_passes_it(self):
        morphology = load()
        branch = [[20, 0, 0], [20, 10, 0], [20, 30, 0]]
        for level in (FINEST, MIDDLE):
            shape = simplified(morphology, [level]).shapes[0]
            assert (DENDRITE, branch, [1.0, 0.5, 0.5]) in polylines(shape)
        coarse = simplified(morphology, [Level(tolerance_um=1.0)]).shapes[0]
        assert (DENDRITE, [branch[0], branch[2]], [1.0, 0.5]) in polylines(coarse)

    def test_segments_by_level(self):
        shapes = simplified(load(), LEVELS).shapes
        assert [shape.segments for shape in shapes] == [7, 7, 5]

    def test_the_far_level_joins_what_pruning_leaves(self):
        shape = simplified(load(), [FAR]).shapes[0]
        dendrite = (DENDRITE, [[0, 0, 0], [20, 0, 0], [20, 30, 0]], [1.0, 1.0, 0.5])
        assert sorted(polylines(shape)) == sorted(
            [
                dendrite,
                (AXON, [[0, 0, 0], [0, -50, 0], [3, -100, 0], [0, -150, 0]], [0.5] * 4),
            ]
        )

    def test_levels_come_in_the_order_asked(self):
        far, finest = simplified(load(), [FAR, FINEST]).shapes
        assert (far.segments, finest.segments) == (5, 7)

    def test_a_level_alone_follows_none(self):
        assert simplified(load(), [FINEST]).nestings == ()

    def test_the_finest_follows_the_middle_wholly(self):
        finest, middle, _ = simplified(load(), LEVELS).shapes
        nesting = simplified(load(), LEVELS).nestings[0]
        assert len(nesting.counts) == len(middle.points)
        assert nesting.counts.sum() == finest.segments
        np.testing.assert_array_equal(nesting.follows, np.flatnonzero(~finest.opens))

    def test_the_middle_follows_the_far_level_but_for_what_it_prunes(self):
        levels = simplified(load(), LEVELS)
        _, middle, far = levels.shapes
        nesting = levels.nestings[1]
        # the far level's dendrite runs on through the fork; its axon is the middle's
        far_ends = [(kind, points) for kind, points, _ in polylines(far)]
        assert (DENDRITE, [[0, 0, 0], [20, 0, 0], [20, 30, 0]]) in far_ends
        counts = {
            tuple(far.points[point].tolist()): int(n) for point, n in enumerate(nesting.counts) if n
        }
        assert counts == {
            (20, 0, 0): 1,
            (20, 30, 0): 2,
            (0, -50, 0): 1,
            (3, -100, 0): 1,
            (0, -150, 0): 1,
        }
        twig = [20 + 2, 0, 0]
        left = set(np.flatnonzero(~middle.opens)) - set(nesting.follows.tolist())
        assert [middle.points[point].tolist() for point in left] == [twig]

    def test_followed_segments_rebuild_from_the_coarser(self):
        levels = simplified(load(), LEVELS)
        for (finer, coarser), nesting in zip(pairwise(levels.shapes), levels.nestings, strict=True):
            follows = iter(nesting.follows.tolist())
            for point in np.flatnonzero(nesting.counts):
                near = coarser.points[point - 1].tolist()
                for _ in range(nesting.counts[point]):
                    end = next(follows)
                    assert finer.points[end - 1].tolist() == near
                    near = finer.points[end].tolist()
                assert near == coarser.points[point].tolist()

    def test_a_branch_apart_from_its_fork_is_not_followed(self):
        levels = simplified(load_with_a_branch_apart(), LEVELS)
        far = levels.shapes[2]
        followed = [
            far.points[point].tolist() for point in np.flatnonzero(levels.nestings[1].counts)
        ]
        assert [20, 30, 0] not in followed
        assert [20, 0, 0] in followed

    def test_the_soma_is_carried(self):
        levels = simplified(load(), [FINEST])
        np.testing.assert_array_equal(levels.soma_center, [0, 0, 0])
        assert levels.soma_radius == pytest.approx(5.0)
