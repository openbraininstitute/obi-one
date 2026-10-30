"""Read parts of a remote file over HTTP without downloading the whole file.

An HTTP ``Range`` request asks a server for a slice of a file, for example
``Range: bytes=0-4095`` for its first 4 KB, and the server answers ``206 Partial Content``
with only those bytes. ``HttpRangeFile`` turns such a URL into a normal Python file object,
so libraries that read files with ``seek`` and ``read`` (h5py, for example) work on it
unchanged and fetch only the bytes they actually read.
"""

import io
import logging
from bisect import bisect_right
from collections.abc import Buffer
from typing import override

from entitysdk.utils.http import HTTPClient

L = logging.getLogger(__name__)

# Smallest amount fetched per request. HDF5 keeps its metadata (the file header and the
# group and dataset headers) in small pieces close together, and h5py reads them a few
# hundred bytes at a time. Fetching 4 MB at once covers many of those reads with one
# request: opening a file costs a few requests instead of hundreds. A read larger than
# this is fetched exactly, in one request.
DEFAULT_BLOCK_SIZE = 4 * 1024 * 1024
HTTP_PARTIAL_CONTENT = 206


class HttpRangeFile(io.RawIOBase):
    """A read-only, seekable file whose bytes are fetched from a URL on demand.

    Each read that is not already in memory sends one ``Range`` request. Fetched blocks
    are kept until the object is dropped, so reading the same bytes twice costs one
    request. Memory grows with the bytes read, not with the file size.

    The caller passes the file size (for example from ``Client.list_directory``), so no
    ``HEAD`` request is needed. S3 answers ``HEAD`` with 403 on a presigned URL signed for
    ``GET`` only, while a ``Range`` ``GET`` on the same URL works.

    A read fails with ``OSError`` when the server does not answer 206, or answers with a
    different number of bytes than asked (a wrong ``size``). Falling back to the whole
    file silently would hide the problem, so the caller decides what to do.

    Example:
        Read one dataset of a large remote HDF5 file::

            remote = HttpRangeFile(url, http_client, size=742_603_632)
            with h5py.File(remote, "r") as h5:
                names = h5["nodes/All/0/@library/model_template"].asstr()[:]
            print(remote.requests)  # a handful, not the 743 MB file

    Attributes:
        size: File size in bytes, as given by the caller.
        requests: Number of ``Range`` requests sent so far.
    """

    def __init__(
        self,
        url: str,
        http_client: HTTPClient,
        size: int,
        block_size: int = DEFAULT_BLOCK_SIZE,
    ) -> None:
        """Store the URL and the size; nothing is fetched before the first read.

        Args:
            url: Address of the file. It must accept ``GET`` with a ``Range`` header.
            http_client: Client used for every request (connection pool, timeouts).
            size: File size in bytes.
            block_size: Smallest number of bytes fetched per request.
        """
        super().__init__()
        self._url = url
        self._http = http_client
        self._block_size = block_size
        self._position = 0
        # Fetched windows sorted by start (parallel lists for bisect); they may overlap.
        self._starts: list[int] = []
        self._blocks: list[bytes] = []
        self.requests = 0
        self.size = size

    @override
    def readable(self) -> bool:
        return True

    @override
    def seekable(self) -> bool:
        return True

    @override
    def tell(self) -> int:
        return self._position

    @override
    def seek(self, offset: int, whence: int = io.SEEK_SET, /) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._position, io.SEEK_END: self.size}[whence]
        self._position = base + offset
        return self._position

    @override
    def readinto(self, buffer: Buffer, /) -> int:
        """Copy bytes from the current position into ``buffer``; at most one request.

        Returns:
            The number of bytes copied; 0 at the end of the file.
        """
        view = memoryview(buffer).cast("B")
        start = self._position
        length = min(len(view), self.size - start)
        if length <= 0:
            return 0
        block_start, block = self._block_covering(start, length)
        offset = start - block_start
        view[:length] = block[offset : offset + length]
        self._position += length
        return length

    def _block_covering(self, start: int, length: int) -> tuple[int, bytes]:
        """Return a fetched block that holds bytes ``[start, start + length)``.

        The block already in memory is used when it covers the range; otherwise one is
        fetched and kept, sorted by start so the next lookup is a binary search.
        """
        index = bisect_right(self._starts, start) - 1
        if index >= 0:
            block_start, block = self._starts[index], self._blocks[index]
            if start + length <= block_start + len(block):
                return block_start, block
        # A small read starts at a block boundary, so the nearby reads that follow are
        # already in memory. A read larger than a block is fetched as asked.
        fetch_start = start if length >= self._block_size else start - start % self._block_size
        fetch_end = min(max(fetch_start + self._block_size, start + length), self.size)
        block = self._fetch(fetch_start, fetch_end)
        position = bisect_right(self._starts, fetch_start)
        self._starts.insert(position, fetch_start)
        self._blocks.insert(position, block)
        return fetch_start, block

    def _fetch(self, start: int, end: int) -> bytes:
        """Fetch bytes ``[start, end)`` of the file in one request.

        Raises:
            OSError: The server ignored the range or returned a different length.
        """
        self.requests += 1
        response = self._http.get(
            self._url, headers={"Range": f"bytes={start}-{end - 1}"}, follow_redirects=True
        )
        response.raise_for_status()
        if response.status_code != HTTP_PARTIAL_CONTENT:
            msg = f"Expected 206 for a range request, got {response.status_code}"
            raise OSError(msg)
        if len(response.content) != end - start:
            msg = f"Expected {end - start} bytes, got {len(response.content)}: wrong file size?"
            raise OSError(msg)
        L.debug("Range read %s-%s (%d bytes)", start, end - 1, len(response.content))
        return response.content
