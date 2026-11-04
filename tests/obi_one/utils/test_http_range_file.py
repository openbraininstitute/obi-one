"""Tests for reading a remote file by HTTP range requests."""

import io

import h5py
import httpx
import numpy as np
import pytest

from obi_one.utils.http_range_file import BLOCK_SIZE, HttpRangeFile

URL = "https://storage/file"


def serving(content: bytes, ranged: list[str]) -> httpx.Client:
    """A client of a server that answers range requests from the content, noting each."""

    def answer(request: httpx.Request) -> httpx.Response:
        ranged.append(request.headers["Range"])
        start, end = request.headers["Range"].removeprefix("bytes=").split("-")
        part = content[int(start) : int(end) + 1]
        last = int(start) + len(part) - 1
        return httpx.Response(
            206, content=part, headers={"Content-Range": f"bytes {start}-{last}/{len(content)}"}
        )

    return httpx.Client(transport=httpx.MockTransport(answer))


class TestHttpRangeFile:
    def test_it_reads_across_blocks(self):
        content = bytes(i % 251 for i in range(2 * BLOCK_SIZE + 10))
        file = HttpRangeFile(URL, serving(content, []))

        file.seek(BLOCK_SIZE - 5)

        assert file.read(10) == content[BLOCK_SIZE - 5 : BLOCK_SIZE + 5]
        assert file.tell() == BLOCK_SIZE + 5

    def test_it_stops_at_the_end_of_the_file(self):
        file = HttpRangeFile(URL, serving(b"abc", []))

        assert file.read() == b"abc"
        assert file.read(1) == b""

    def test_it_knows_its_size_and_seeks_from_either_end(self):
        file = HttpRangeFile(URL, serving(b"abcdef", []))

        assert file.seek(0, io.SEEK_END) == 6
        assert file.seek(-2, io.SEEK_END) == 4
        assert file.seek(1, io.SEEK_CUR) == 5

    def test_it_fetches_each_block_once(self):
        ranged: list[str] = []
        file = HttpRangeFile(URL, serving(bytes(2 * BLOCK_SIZE), ranged))

        for position in (0, 10, BLOCK_SIZE, BLOCK_SIZE + 10, 0):
            file.seek(position)
            file.read(1)

        assert ranged == [f"bytes=0-{BLOCK_SIZE - 1}", f"bytes={BLOCK_SIZE}-{2 * BLOCK_SIZE - 1}"]

    def test_it_only_goes_through_a_redirect_once(self):
        content = bytes(2 * BLOCK_SIZE)
        asked: list[str] = []

        def answer(request: httpx.Request) -> httpx.Response:
            asked.append(str(request.url))
            if request.url.host == "archive":
                return httpx.Response(302, headers={"Location": "https://storage/signed"})
            start, end = request.headers["Range"].removeprefix("bytes=").split("-")
            part = content[int(start) : int(end) + 1]
            last = int(start) + len(part) - 1
            headers = {"Content-Range": f"bytes {start}-{last}/{len(content)}"}
            return httpx.Response(206, content=part, headers=headers)

        client = httpx.Client(transport=httpx.MockTransport(answer), follow_redirects=True)
        file = HttpRangeFile("https://archive/asset", client)
        file.seek(BLOCK_SIZE)
        file.read(1)

        assert asked == [
            "https://archive/asset",
            "https://storage/signed",
            "https://storage/signed",
        ]

    def test_h5py_reads_a_file_through_it_without_all_of_it(self, tmp_path):
        path = tmp_path / "file.h5"
        with h5py.File(path, "w") as file:
            file["small"] = np.arange(5)
            file.create_dataset("large", data=np.random.default_rng(0).random(2_000_000))
        ranged: list[str] = []
        size = path.stat().st_size

        with h5py.File(HttpRangeFile(URL, serving(path.read_bytes(), ranged)), "r") as file:
            small = file["small"][()]

        assert small.tolist() == [0, 1, 2, 3, 4]
        assert len(ranged) * BLOCK_SIZE < size / 2

    def test_a_server_ignoring_ranges_is_an_error(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200)))

        with pytest.raises(OSError, match="not 206"):
            HttpRangeFile(URL, client)

    def test_a_failed_request_is_an_error(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(403)))

        with pytest.raises(httpx.HTTPStatusError):
            HttpRangeFile(URL, client)

    def test_a_short_answer_is_an_error_rather_than_a_hang(self):
        def answer(_: httpx.Request) -> httpx.Response:
            return httpx.Response(206, content=b"ab", headers={"Content-Range": "bytes 0-1/5"})

        file = HttpRangeFile(URL, httpx.Client(transport=httpx.MockTransport(answer)))

        with pytest.raises(OSError, match="ends before byte"):
            file.read()
