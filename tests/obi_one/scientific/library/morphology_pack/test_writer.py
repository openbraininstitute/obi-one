import json
import zlib

import numpy as np
import pytest

from obi_one.scientific.library.morphology_pack import writer as writer_module
from obi_one.scientific.library.morphology_pack.codec import (
    GRID_UM,
    HEADER,
    Chunks,
    decode_chunk,
    take_apart,
)
from obi_one.scientific.library.morphology_pack.geometry import FAR, FINEST, LEVELS, simplified
from obi_one.scientific.library.morphology_pack.parallel import ALONE, Processes
from obi_one.scientific.library.morphology_pack.reader import read_pack, run_segments
from obi_one.scientific.library.morphology_pack.writer import PackWriter, placed

from tests.obi_one.scientific.library.morphology_pack.utils import (
    AXON,
    DENDRITE,
    load,
    load_with_a_branch_apart,
)

QUARTER_TURN = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
PLACES = [
    (np.eye(3), np.zeros(3)),
    (QUARTER_TURN, np.array([1000.0, -2000.0, 3000.0])),
    (np.eye(3), np.array([40.0, 0.0, 0.0])),
]
ENDS = [0, 1, 2, 4, 5, 6]
RADII = [3, 7]


def in_order(segments):
    return segments[np.lexsort(np.rint(segments[:, ENDS] / GRID_UM).T)]


def placed_segments(shape, rotation, position):
    points = shape.points @ rotation.T + position
    far = np.flatnonzero(~shape.opens)
    return np.column_stack([points[far - 1], shape.radii[far - 1], points[far], shape.radii[far]])


def pack_of(morphology, levels, **options):
    shapes = simplified(morphology, levels)
    writer = PackWriter([("first", 2), ("second", 1)], levels, **options)
    for cell, (rotation, position) in enumerate(PLACES):
        writer.add_cell(cell, shapes, rotation, position)
    return shapes, writer.pack()


def chunks_of(data, level):
    """Each chunk of a level, decoded, with its entry's box."""
    index, blocks = take_apart(data)
    entry = index.levels[level]
    at = entry.offset
    for box, size in zip(np.reshape(entry.chunks.box, (-1, 3)), entry.chunks.bytes, strict=True):
        yield box, decode_chunk(bytes(blocks[at : at + size]))
        at += size


def own_segments(data, level):
    """The segments of a level that follow no coarser segment."""
    return sum(len(chunk.runs.steps) for _, chunk in chunks_of(data, level))


def assert_placed(level, shape):
    """The segments read back for each cell are the shape's, where the cell was placed."""
    for cell, (rotation, position) in enumerate(PLACES):
        expected = in_order(placed_segments(shape, rotation, position))
        read = in_order(level.segments[level.cells == cell])
        np.testing.assert_allclose(read[:, ENDS], expected[:, ENDS], atol=GRID_UM / 2 + 1e-9)
        assert np.abs(np.log2(read[:, RADII] / expected[:, RADII])).max() <= 1 / 32 + 1e-9


class TestRoundTrip:
    @pytest.mark.parametrize("chunk_um", [50.0, 7.0, 100000.0])
    @pytest.mark.parametrize("morphology", [load, load_with_a_branch_apart])
    def test_every_segment_comes_back_where_it_was_placed(self, chunk_um, morphology):
        shapes, data = pack_of(morphology(), LEVELS, chunk_um=chunk_um)
        pack = read_pack(data)
        for shape, level in zip(shapes.shapes, pack.levels, strict=True):
            assert len(level.segments) == shape.segments * len(PLACES)
            assert_placed(level, shape)

    def test_finer_levels_follow_the_coarser(self):
        _, data = pack_of(load(), LEVELS, chunk_um=7.0)
        finest, middle, far = take_apart(data)[0].levels
        assert (finest.base, middle.base, far.base) == (1, 2, None)
        # the finest follows the middle wholly; of the middle, the twig the far level prunes is left
        assert own_segments(data, 0) == 0
        assert own_segments(data, 1) == len(PLACES)
        assert own_segments(data, 2) == far.segments

    def test_a_branch_that_starts_apart_from_its_fork_is_not_followed(self):
        _, data = pack_of(load_with_a_branch_apart(), LEVELS)
        # the twig, and the branch's two segments
        assert own_segments(data, 1) == 3 * len(PLACES)

    def test_segments_keep_their_section_type(self):
        _, data = pack_of(load(), [FINEST])
        level = read_pack(data).levels[0]
        first = level.cells == 0
        below = level.segments[:, 5] < 0
        assert set(level.types[first & below]) == {AXON}
        assert set(level.types[first & ~below]) == {DENDRITE}

    def test_levels_keep_their_settings(self):
        _, data = pack_of(load(), [FAR, FINEST])
        far, finest = read_pack(data).levels
        assert (far.entry.tolerance_um, far.entry.prune_um) == (1.0, 5.0)
        assert (finest.entry.tolerance_um, finest.entry.prune_um) == (0.125, 0.0)
        assert len(far.segments) < len(finest.segments)

    def test_somas_are_placed(self):
        _, data = pack_of(load(), [FINEST])
        somas = read_pack(data).somas
        np.testing.assert_allclose(somas[1], [1000, -2000, 3000, 5])
        np.testing.assert_allclose(somas[2], [40, 0, 0, 5])

    def test_cells_may_be_added_in_any_order(self):
        shapes = simplified(load(), [FINEST])
        writer = PackWriter([("only", 3)], [FINEST], chunk_um=100000.0)
        for cell in (2, 0, 1):
            writer.add_cell(cell, shapes, *PLACES[cell])
        assert_placed(read_pack(writer.pack()).levels[0], shapes.shapes[0])


class TestIndex:
    def test_names_what_a_reader_needs(self):
        shapes, data = pack_of(load(), [FINEST])
        index, blocks = take_apart(data)
        assert index.layout == "space"
        assert index.grid_um == GRID_UM
        assert [(entry.name, entry.cells) for entry in index.populations] == [
            ("first", 2),
            ("second", 1),
        ]
        level = index.levels[0]
        assert level.segments == shapes.shapes[0].segments * len(PLACES)
        assert sum(level.chunks.segments) == level.segments
        assert level.offset == index.somas.bytes
        assert level.offset + sum(level.chunks.bytes) == len(blocks)

    def test_is_spelled_as_the_format_says(self):
        _, data = pack_of(load(), [FINEST])
        *_, length = HEADER.unpack_from(data)
        index = json.loads(zlib.decompress(data[HEADER.size : HEADER.size + length]))
        assert set(index) == {
            "layout",
            "gridUm",
            "radiusSteps",
            "bounds",
            "populations",
            "somas",
            "levels",
        }
        assert index["populations"][0] == {"name": "first", "cells": 2}
        assert set(index["somas"]) == {"offset", "bytes"}
        level = index["levels"][0]
        assert set(level) == {
            "toleranceUm",
            "pruneUm",
            "chunkSteps",
            "segments",
            "runs",
            "offset",
            "base",
            "chunks",
        }
        assert level["base"] is None
        assert set(level["chunks"]) == {"box", "bytes", "segments", "reach"}

    def test_bounds_hold_every_point(self):
        _, data = pack_of(load(), [FINEST])
        pack = read_pack(data)
        low, high = np.array(pack.index.bounds) * GRID_UM
        ends = pack.levels[0].segments.reshape(-1, 4)[:, :3]
        assert (ends >= low - 1e-9).all()
        assert (ends <= high + 1e-9).all()
        np.testing.assert_allclose(low, [0, -2000, 0])
        np.testing.assert_allclose(high, [1150, 30, 3000])

    def test_a_run_is_in_the_chunk_its_far_ends_lie_in(self):
        _, data = pack_of(load(), [FINEST], chunk_um=7.0)
        level = take_apart(data)[0].levels[0]
        boxes = np.array(level.chunks.box).reshape(-1, 3)
        assert len(boxes) > len(PLACES)
        assert len(np.unique(boxes, axis=0)) == len(boxes)
        for _, chunk in chunks_of(data, 0):
            far = run_segments(chunk.runs, np.zeros(3, dtype=np.int64)).far[:, :3]
            assert (far >= 0).all()
            assert (far < level.chunk_steps).all()
            assert (np.diff(chunk.runs.cells) >= 0).all()

    def test_a_chunk_reaches_as_far_as_its_segments(self):
        _, data = pack_of(load(), LEVELS, chunk_um=7.0)
        pack = read_pack(data)
        reaching = 0
        for level, entry in enumerate(pack.index.levels):
            assert entry.chunk_steps == pack.index.levels[0].chunk_steps
            # the reader's segments come chunk by chunk
            first = 0
            for box, segments, reach in zip(
                np.reshape(entry.chunks.box, (-1, 3)),
                entry.chunks.segments,
                entry.chunks.reach,
                strict=True,
            ):
                ends = pack.levels[level].segments[first : first + segments]
                first += segments
                points = np.rint(ends.reshape(-1, 4)[:, :3] / GRID_UM)
                low, high = box * entry.chunk_steps, (box + 1) * entry.chunk_steps - 1
                outside = np.maximum(low - points, points - high).max(initial=0)
                assert max(outside, 0) == reach
                reaching += reach > 0
        assert reaching

    def test_chunks_are_doubled_until_there_are_few_enough(self, monkeypatch):
        morphology = load()
        _, small = pack_of(morphology, [FINEST], chunk_um=7.0)
        chunks = len(take_apart(small)[0].levels[0].chunks.bytes)
        monkeypatch.setattr(writer_module, "MAX_CHUNKS", chunks // 3)
        _, data = pack_of(morphology, [FINEST], chunk_um=7.0)
        level = take_apart(data)[0].levels[0]
        assert len(level.chunks.bytes) <= chunks // 3
        assert level.chunk_steps > round(7.0 / GRID_UM)
        assert len(read_pack(data).levels[0].segments) == level.segments


class TestWriter:
    def test_a_pack_with_no_cell_added(self):
        writer = PackWriter([("only", 4)], [FINEST])
        pack = read_pack(writer.pack())
        assert pack.somas.shape == (4, 4)
        assert not pack.somas.any()
        assert len(pack.levels[0].segments) == 0
        assert pack.index.levels[0].chunks == Chunks(box=[], bytes=[], segments=[], reach=[])

    def test_a_cell_must_come_at_every_level(self):
        shapes = simplified(load(), [FINEST])
        writer = PackWriter([("only", 1)], LEVELS)
        with pytest.raises(ValueError, match="zip"):
            writer.add_cell(0, shapes, np.eye(3), np.zeros(3))

    def test_a_point_is_placed_alike_wherever_it_sits(self):
        rng = np.random.default_rng(7)
        points = (rng.normal(size=(256, 3)) * 800).astype(np.float32)
        rotation, _ = np.linalg.qr(rng.normal(size=(3, 3)))
        position = rng.normal(size=3) * 3000
        every = placed(points, rotation, position)
        # A matrix product rounds a short array's last rows apart from the same rows in a long one.
        for start in range(9):
            for n in range(1, 40):
                part = placed(points[start : start + n], rotation, position)
                assert np.array_equal(part, every[start : start + n])

    def test_processes_write_the_same_pack(self):
        shapes = simplified(load(), LEVELS)
        packs = []
        for processes in (ALONE, Processes(2)):
            writer = PackWriter([("only", len(PLACES))], LEVELS, chunk_um=7.0)
            for cell, (rotation, position) in enumerate(PLACES):
                writer.add_cell(cell, shapes, rotation, position)
            with processes:
                packs.append(writer.pack(processes))
        same = packs[0] == packs[1]
        assert same

    def test_a_writer_packs_once(self):
        writer = PackWriter([("only", 1)], [FINEST])
        writer.pack()
        with pytest.raises(RuntimeError, match="packs once"):
            writer.pack()
