import zlib

import numpy as np
import pytest

from obi_one.scientific.library.morphology_pack.codec import (
    COUNTS,
    GRID_UM,
    HEADER,
    MAGIC,
    PLAIN_DEFLATE_BYTES,
    RADIUS_STEPS,
    VERSION,
    Chunk,
    Index,
    Runs,
    SomasEntry,
    assemble,
    back_references,
    decode_chunk,
    decode_somas,
    encode_chunk,
    encode_somas,
    guessed_step,
    on_grid,
    planes,
    radii_um,
    radius_steps,
    read_planes,
    read_runs,
    run_parts,
    take_apart,
    towards,
    unzigzag,
    zigzag,
)


class TestPlanes:
    @pytest.mark.parametrize(
        ("most", "width"), [(0, 1), (255, 1), (256, 2), (65535, 2), (65536, 3), (2**32 - 1, 4)]
    )
    def test_a_stream_is_as_wide_as_its_largest_number(self, most, width):
        numbers = np.array([0, 1, most], dtype=np.uint32)
        stored = planes(numbers)
        assert stored[0] == width
        assert len(stored) == 1 + width * len(numbers)
        read, after = read_planes(stored, 0, len(numbers))
        np.testing.assert_array_equal(read, numbers)
        assert after == len(stored)

    def test_the_lowest_bytes_come_first(self):
        assert planes(np.array([0x0102, 0x0304])) == bytes([2, 0x02, 0x04, 0x01, 0x03])

    def test_an_empty_stream_is_its_width_alone(self):
        stored = planes(np.zeros(0, dtype=np.uint32))
        assert stored == b"\x01"
        read, after = read_planes(stored, 0, 0)
        assert len(read) == 0
        assert after == 1

    def test_streams_are_read_one_after_another(self):
        first, second = np.array([1, 2, 3]), np.array([70000, 5])
        stored = planes(first) + planes(second)
        read, after = read_planes(stored, 0, 3)
        np.testing.assert_array_equal(read, first)
        read, after = read_planes(stored, after, 2)
        np.testing.assert_array_equal(read, second)
        assert after == len(stored)


class TestZigzag:
    def test_small_numbers_of_either_sign_stay_small(self):
        np.testing.assert_array_equal(zigzag(np.array([0, -1, 1, -2, 2])), [0, 1, 2, 3, 4])

    def test_round_trip(self):
        numbers = np.array([0, -1, 1, -(2**31), 2**31 - 1, 123456, -654321])
        np.testing.assert_array_equal(unzigzag(zigzag(numbers)), numbers)


class TestQuantities:
    def test_a_position_is_within_half_a_step(self):
        points = np.array([[0.0, 0.012, -0.013], [1234.5678, -4321.0001, 0.0375]])
        np.testing.assert_allclose(on_grid(points) * GRID_UM, points, atol=GRID_UM / 2 + 1e-12)

    def test_a_radius_is_within_a_thirty_second_of_an_octave(self):
        radii = np.array([0.03, 0.1, 0.5, 1.0, 7.3, 40.0])
        back = radii_um(radius_steps(radii), RADIUS_STEPS)
        assert np.abs(np.log2(back / radii)).max() <= 1 / 32 + 1e-12

    def test_a_radius_of_zero_takes_the_smallest_step(self):
        back = radii_um(radius_steps(np.array([0.0])), RADIUS_STEPS)
        assert back[0] == pytest.approx(1 / 1024)

    def test_a_radius_held_in_single_precision_takes_the_step_of_its_double(self):
        radii = np.geomspace(0.01, 50, 2000)
        np.testing.assert_array_equal(
            radius_steps(radii.astype(np.float32)),
            radius_steps(radii.astype(np.float32).astype(np.float64)),
        )


def some_runs():
    return Runs(
        cells=np.array([3, 3, 70000]),
        types=np.array([2, 3, 4], dtype=np.uint8),
        lengths=np.array([2, 1, 3]),
        starts=np.array([[5, -7, 0, -40], [1999, 2000, -1, 16], [-300000, 12, 9, 0]]),
        steps=np.array(
            [
                [1, 0, 0, 0],
                [-2, 3, 0, 1],
                [0, 0, 70000, -1],
                [5, 5, 5, 0],
                [0, -1, 0, 0],
                [9, 9, 9, 9],
            ]
        ),
    )


CHUNK_STEPS = 2000
NO_INNER = np.zeros((0, 4), dtype=np.int64)


def assert_same_runs(back, runs):
    for name in ("cells", "types", "lengths", "starts", "steps"):
        np.testing.assert_array_equal(getattr(back, name), getattr(runs, name))


def runs_that_chain():
    """Runs of one cell that start where an earlier one ends: on x, y and z, and in radius too."""
    return Runs(
        cells=np.array([4, 4, 4, 4, 9]),
        types=np.array([3, 3, 3, 2, 3], dtype=np.uint8),
        lengths=np.array([2, 1, 2, 1, 1]),
        starts=np.array(
            [[10, 20, 30, 5], [13, 18, 30, 7], [13, 18, 30, 4], [14, 18, 31, 0], [10, 20, 30, 5]]
        ),
        steps=np.array(
            [
                [1, -1, 0, 1],
                [2, -1, 0, 1],
                [1, 0, 1, -4],
                [-5, 0, 0, 0],
                [3, 3, 3, 3],
                [0, 0, 0, 0],
                [1, 1, 1, 1],
            ]
        ),
    )


def random_runs(rng, count):
    lengths = rng.integers(1, 40, count)
    return Runs(
        cells=np.sort(rng.integers(0, 5000, count)),
        types=rng.integers(2, 5, count).astype(np.uint8),
        lengths=lengths,
        starts=rng.integers(-80000, 80000, (count, 4)),
        steps=rng.integers(-300, 300, (int(lengths.sum()), 4)),
    )


class TestRuns:
    def test_a_start_where_a_run_of_its_cell_ends_refers_back_to_it(self):
        refs, radii = back_references(runs_that_chain(), CHUNK_STEPS)
        # the second starts where the first ends, radius and all; the third and the fourth where
        # the first and the second end, but for the radius; the last is another cell's
        np.testing.assert_array_equal(refs, [0, 1, 2, 2, 0])
        np.testing.assert_array_equal(radii, [0, 0, -3, -3, 0])

    def test_a_start_outside_the_chunk_is_given_whole(self):
        runs = runs_that_chain()
        shifted = Runs(
            runs.cells, runs.types, runs.lengths, runs.starts - [20, 0, 0, 0], runs.steps
        )
        refs, _ = back_references(shifted, CHUNK_STEPS)
        assert not refs.any()

    def test_a_step_is_stored_less_the_guess_from_the_one_before(self):
        np.testing.assert_array_equal(guessed_step(np.array([4, -4, 1, -1, 0])), [3, -3, 1, -1, 0])
        runs = runs_that_chain()
        data = b"".join(run_parts(runs, CHUNK_STEPS))
        back, after = read_runs(data, 0, 5, 7)
        assert after == len(data)
        assert_same_runs(back, runs)

    def test_round_trip_of_many(self):
        runs = random_runs(np.random.default_rng(3), 400)
        data = b"".join(run_parts(runs, CHUNK_STEPS))
        back, _ = read_runs(data, 0, 400, len(runs.steps))
        assert_same_runs(back, runs)


class TestChord:
    def test_the_guess_is_a_share_of_the_way_rounded_down(self):
        near, far = np.array([0, 0, 10, -7]), np.array([10, -10, 10, 0])
        np.testing.assert_array_equal(towards(near, far, 3), [3, -4, 10, -5])
        np.testing.assert_array_equal(towards(near, far, 1), far)


class TestChunk:
    def test_round_trip(self):
        chunk = Chunk(
            counts=np.array([0, 1, 3, 0, 2]),
            inner=np.array([[1, -2, 3, 0], [-70000, 5, 0, -1], [2**20, -(2**21), 0, 4]]),
            runs=some_runs(),
        )
        back = decode_chunk(encode_chunk(chunk, CHUNK_STEPS))
        np.testing.assert_array_equal(back.counts, chunk.counts)
        np.testing.assert_array_equal(back.inner, chunk.inner)
        assert_same_runs(back.runs, chunk.runs)

    def test_a_chunk_of_runs_alone(self):
        chunk = Chunk(np.zeros(0, dtype=np.int64), NO_INNER, runs_that_chain())
        back = decode_chunk(encode_chunk(chunk, CHUNK_STEPS))
        assert len(back.counts) == 0
        assert back.inner.shape == (0, 4)
        assert_same_runs(back.runs, chunk.runs)

    def test_a_chunk_of_additions_alone(self):
        none = Runs(*(np.zeros(0, dtype=np.int64) for _ in range(3)), NO_INNER, NO_INNER)
        chunk = Chunk(np.array([2, 0, 1]), np.array([[5, 5, 5, 5]]), none)
        back = decode_chunk(encode_chunk(chunk, CHUNK_STEPS))
        np.testing.assert_array_equal(back.counts, [2, 0, 1])
        assert len(back.runs.cells) == 0

    def test_a_block_starts_with_its_counts(self):
        chunk = Chunk(np.array([0, 2]), np.array([[1, 1, 1, 1]]), some_runs())
        data = zlib.decompress(encode_chunk(chunk, CHUNK_STEPS))
        assert COUNTS.unpack_from(data) == (2, 1, 3, 6)

    def test_a_large_block_deflated_by_planes_inflates_to_the_same_streams(self):
        runs = random_runs(np.random.default_rng(7), 300)
        chunk = Chunk(np.zeros(0, dtype=np.int64), NO_INNER, runs)
        data = zlib.decompress(encode_chunk(chunk, CHUNK_STEPS))
        assert len(data) > PLAIN_DEFLATE_BYTES
        streams = planes(np.zeros(0)) * 5 + b"".join(run_parts(runs, CHUNK_STEPS))
        assert data == COUNTS.pack(0, 0, 300, len(runs.steps)) + streams
        assert_same_runs(decode_chunk(encode_chunk(chunk, CHUNK_STEPS)).runs, runs)

    def test_a_part_keeps_its_runs_and_their_segments(self):
        part = some_runs().part(slice(1, 3), slice(2, 6))
        np.testing.assert_array_equal(part.cells, [3, 70000])
        np.testing.assert_array_equal(part.lengths, [1, 3])
        assert len(part.steps) == 4


class TestSomas:
    def test_round_trip(self):
        somas = np.array([[1.5, -2.0, 3.25, 5.0], [0.0, 0.0, 0.0, 0.0]])
        np.testing.assert_array_equal(decode_somas(encode_somas(somas)), somas)


def an_index() -> Index:
    return Index(
        bounds=[[0, -1, 2], [3, 4, 5]],
        populations=[],
        somas=SomasEntry(offset=0, bytes=3),
        levels=[],
    )


class TestPack:
    def test_round_trip(self):
        back, blocks = take_apart(assemble(an_index(), [b"one", b"three"]))
        assert back == an_index()
        assert bytes(blocks) == b"onethree"

    def test_the_header_names_the_format(self):
        magic, version, spare, length = HEADER.unpack_from(assemble(an_index(), []))
        assert (magic, version, spare) == (MAGIC, VERSION, 0)
        assert length > 0

    @pytest.mark.parametrize("header", [(b"NOPE", VERSION), (MAGIC, VERSION + 1)])
    def test_another_format_is_refused(self, header):
        pack = HEADER.pack(*header, 0, 0)
        with pytest.raises(ValueError, match="Not a morphology pack"):
            take_apart(pack)
