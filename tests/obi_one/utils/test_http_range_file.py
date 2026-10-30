import io
from pathlib import Path

import h5py
import httpx2
import numpy as np
import pytest

from obi_one.utils.http_range_file import HttpRangeFile

TINY_NODES = Path("examples/data/tiny_circuits/N_10__top_nodes_dim6/S1nonbarrel_neurons/nodes.h5")


class RangeServer:
    """An httpx2 transport serving one blob with ``Range`` GETs, like S3 behind a presigned
    URL signed for GET: ``HEAD`` is refused with 403."""

    def __init__(self, blob: bytes, *, ranges: bool = True):
        self.blob = blob
        self.ranges = ranges
        self.requests: list[str] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(f"{request.method} {request.headers.get('range', '')}".strip())
        if request.method == "HEAD":
            return httpx2.Response(403)
        if not self.ranges or "range" not in request.headers:
            return httpx2.Response(200, content=self.blob)
        start, end = request.headers["range"].removeprefix("bytes=").split("-")
        return httpx2.Response(206, content=self.blob[int(start) : int(end) + 1])


def _client(server: RangeServer) -> httpx2.Client:
    return httpx2.Client(transport=httpx2.MockTransport(server))


class TestHttpRangeFile:
    def test_nothing_is_fetched_before_the_first_read(self):
        server = RangeServer(b"x" * 100)
        remote = HttpRangeFile("http://s/f", _client(server), 100)
        assert remote.size == 100
        assert server.requests == []
        assert remote.readable()
        assert remote.seekable()

    def test_server_without_ranges_is_refused_on_the_first_read(self):
        server = RangeServer(b"x" * 10, ranges=False)
        remote = HttpRangeFile("http://s/f", _client(server), 10, block_size=4)
        with pytest.raises(OSError, match="Expected 206"):
            remote.read(1)
        assert server.requests == ["GET bytes=0-3"]

    def test_a_size_larger_than_the_file_is_an_error_not_short_bytes(self):
        """Storage answers a range past the end with the bytes it has, as S3 does."""
        remote = HttpRangeFile("http://s/f", _client(RangeServer(b"x" * 10)), 12)
        with pytest.raises(OSError, match="wrong file size"):
            remote.read(12)

    def test_small_reads_share_one_block(self):
        blob = bytes(range(256)) * 4
        server = RangeServer(blob)
        remote = HttpRangeFile("http://s/f", _client(server), len(blob), block_size=512)
        assert remote.read(4) == blob[:4]
        remote.seek(500)
        assert remote.read(4) == blob[500:504]
        assert server.requests == ["GET bytes=0-511"]
        remote.seek(600)
        assert remote.read(4) == blob[600:604]
        assert remote.requests == 2
        assert server.requests[-1] == "GET bytes=512-1023"

    def test_a_block_covers_a_read_that_crosses_its_boundary(self):
        blob = bytes(range(256)) * 4
        server = RangeServer(blob)
        remote = HttpRangeFile("http://s/f", _client(server), len(blob), block_size=512)
        remote.seek(500)
        assert remote.read(100) == blob[500:600]
        assert server.requests == ["GET bytes=0-599"]

    def test_a_large_read_is_one_exact_request(self):
        blob = bytes(range(256)) * 16
        server = RangeServer(blob)
        remote = HttpRangeFile("http://s/f", _client(server), len(blob), block_size=512)
        remote.seek(300)
        assert remote.read(2000) == blob[300:2300]
        assert server.requests == ["GET bytes=300-2299"]

    def test_reads_stop_at_the_end_of_the_file(self):
        blob = b"abcdef"
        remote = HttpRangeFile("http://s/f", _client(RangeServer(blob)), len(blob), block_size=4)
        remote.seek(-2, io.SEEK_END)
        assert remote.read(10) == b"ef"
        assert remote.read(10) == b""
        assert remote.tell() == 6
        remote.seek(-3, io.SEEK_CUR)
        assert remote.read(1) == b"d"

    def test_h5py_reads_one_dataset_without_the_rest(self):
        blob = TINY_NODES.read_bytes()
        server = RangeServer(blob)
        remote = HttpRangeFile("http://s/f", _client(server), len(blob), block_size=4096)
        with h5py.File(remote, "r") as h5:
            group = h5["nodes/S1nonbarrel_neurons/0"]
            library = group["@library/model_template"].asstr()[:]
            indices = np.unique(group["model_template"][:])
        with h5py.File(TINY_NODES, "r") as h5:
            group = h5["nodes/S1nonbarrel_neurons/0"]
            assert list(library) == list(group["@library/model_template"].asstr()[:])
            assert list(indices) == list(np.unique(group["model_template"][:]))
        fetched = sum(len(block) for block in remote._blocks)
        assert fetched < len(blob)
        assert remote.requests == len(server.requests)
