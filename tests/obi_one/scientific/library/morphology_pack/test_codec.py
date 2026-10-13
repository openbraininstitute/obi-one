import zlib

import numpy as np
import pytest

from obi_one.scientific.library.morphology_pack.codec import (
    GRID_UM,
    HEADER,
    MAGIC,
    RADIUS_STEPS,
    VERSION,
    Index,
    Runs,
    SomasEntry,
    assemble,
    decode_chunk,
    decode_somas,
    encode_chunk,
    encode_somas,
    on_grid,
    planes,
    radii_um,
    radius_steps,
    read_planes,
    take_apart,
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


class TestChunk:
    def test_round_trip(self):
        runs = some_runs()
        back = decode_chunk(encode_chunk(runs))
        for name in ("cells", "types", "lengths", "starts", "steps"):
            np.testing.assert_array_equal(getattr(back, name), getattr(runs, name))

    def test_a_block_starts_with_its_counts(self):
        data = zlib.decompress(encode_chunk(some_runs()))
        assert int.from_bytes(data[:4], "little") == 3
        assert int.from_bytes(data[4:8], "little") == 6

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
