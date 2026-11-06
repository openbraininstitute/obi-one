"""Read parts of a remote file with HTTP ``Range`` requests, not the whole file.

``HttpRangeFile`` makes a URL look like a seekable file, so h5py reads only the bytes it
needs. h5py runs the file's reads inside its process-wide lock, so a long remote read
blocks every other h5py call in the process (measured: N concurrent reads take N times as
long). Read a large dataset with ``read_contiguous_dataset``, which fetches outside h5py.
"""

import io
import logging
from bisect import bisect_right
from collections.abc import Buffer
from typing import override

import h5py
import numpy as np
from entitysdk.utils.http import HTTPClient

L = logging.getLogger(__name__)

# Smallest fetch. HDF5 metadata sits in small pieces close together and h5py reads it a
# few hundred bytes at a time; 4 MB blocks turn hundreds of reads into a few requests.
DEFAULT_BLOCK_SIZE = 4 * 1024 * 1024
HTTP_PARTIAL_CONTENT = 206


class HttpRangeFile(io.RawIOBase):
    """A read-only, seekable file whose bytes are fetched from a URL on demand.

    Small reads are served from ``block_size`` blocks kept until ``close()``. A read
    larger than a block is fetched exactly and not kept. The caller gives the file size,
    so no ``HEAD`` request is sent (S3 refuses ``HEAD`` on a presigned ``GET`` URL).

    A read raises ``OSError`` when the server does not answer 206 or returns the wrong
    number of bytes (a wrong ``size``); the caller decides whether to fall back.

    Example:
        ::

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
            url: Address of a file served with ``Range`` support.
            http_client: Client used for every request (connection pool, timeouts).
            size: File size in bytes.
            block_size: Smallest number of bytes fetched per request.
        """
        super().__init__()
        self._url = url
        self._http = http_client
        self._block_size = block_size
        self._position = 0
        # Kept blocks sorted by start, as parallel lists for bisect.
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
    def close(self) -> None:
        self._starts.clear()
        self._blocks.clear()
        super().close()

    def _check_open(self) -> None:
        """Raise ``ValueError`` after ``close()``, as ``io`` requires."""
        if self.closed:
            msg = "I/O operation on closed file"
            raise ValueError(msg)

    @override
    def tell(self) -> int:
        self._check_open()
        return self._position

    @override
    def seek(self, offset: int, whence: int = io.SEEK_SET, /) -> int:
        self._check_open()
        try:
            base = {io.SEEK_SET: 0, io.SEEK_CUR: self._position, io.SEEK_END: self.size}[whence]
        except KeyError as err:
            msg = f"invalid whence ({whence}, should be 0, 1 or 2)"
            raise ValueError(msg) from err
        position = base + offset
        if position < 0:
            msg = f"negative seek position {position}"
            raise ValueError(msg)
        self._position = position
        return self._position

    @override
    def readinto(self, buffer: Buffer, /) -> int:
        """Fill ``buffer`` from the current position; at most one request.

        Never a short read: h5py calls ``readinto`` once and ignores the count returned,
        so a partial fill would hand HDF5 uninitialised memory.

        Returns:
            The number of bytes copied; 0 at the end of the file.
        """
        self._check_open()
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

    def read_at(self, start: int, length: int) -> bytes:
        """Fetch bytes ``[start, start + length)`` in one request, bypassing the cache.

        Does not touch the file position, so it is safe while h5py has the file open.

        Raises:
            ValueError: The range ends past the end of the file.
        """
        self._check_open()
        if start + length > self.size:
            msg = f"range {start}-{start + length - 1} ends past the file size {self.size}"
            raise ValueError(msg)
        return self._fetch(start, start + length)

    def _block_covering(self, start: int, length: int) -> tuple[int, bytes]:
        """Return ``(block start, block bytes)`` for a block holding ``[start, start+length)``.

        Only the kept block starting closest before ``start`` is checked. A block-sized
        fetch is kept; a larger exact fetch is not.
        """
        index = bisect_right(self._starts, start) - 1
        if index >= 0:
            block_start, block = self._starts[index], self._blocks[index]
            if start + length <= block_start + len(block):
                return block_start, block
        if length >= self._block_size:
            return start, self._fetch(start, min(start + length, self.size))
        # Block-aligned, extended when the read crosses the block end.
        fetch_start = start - start % self._block_size
        fetch_end = min(max(fetch_start + self._block_size, start + length), self.size)
        block = self._fetch(fetch_start, fetch_end)
        position = bisect_right(self._starts, fetch_start)
        self._starts.insert(position, fetch_start)
        self._blocks.insert(position, block)
        return fetch_start, block

    def _fetch(self, start: int, end: int) -> bytes:
        """Fetch bytes ``[start, end)`` in one request.

        Raises:
            OSError: Status other than 206, or wrong length. The signed URL is left out.
        """
        self.requests += 1
        # Streamed: a 200 (Range header dropped) is refused before its whole body is read.
        # No raise_for_status(): its message holds the signed URL.
        with self._http.stream(
            "GET", self._url, headers={"Range": f"bytes={start}-{end - 1}"}, follow_redirects=True
        ) as response:
            if response.status_code != HTTP_PARTIAL_CONTENT:
                msg = f"Expected 206 for a range request, got {response.status_code}"
                raise OSError(msg)
            content = response.read()
        if len(content) != end - start:
            msg = f"Expected {end - start} bytes, got {len(content)}: wrong file size?"
            raise OSError(msg)
        L.debug("Range read %s-%s (%d bytes)", start, end - 1, len(content))
        return content


def read_contiguous_dataset(dataset: h5py.Dataset, remote: HttpRangeFile) -> np.ndarray:
    """Read a whole dataset of a file opened on ``remote``, fetching its bytes outside h5py.

    A contiguous, uncompressed dataset is one run of bytes: its offset and size give one
    exact ``Range`` request that does not hold h5py's lock. Chunked, compressed and
    variable-length-string datasets are read through h5py as usual.

    Returns:
        The dataset's values, as ``dataset[()]`` gives them.
    """
    offset = dataset.id.get_offset()
    if (
        offset is None
        or dataset.dtype.kind == "O"
        or dataset.id.get_storage_size() != dataset.nbytes
    ):
        return dataset[()]
    raw = remote.read_at(offset, dataset.nbytes)
    return np.frombuffer(raw, dtype=dataset.dtype).reshape(dataset.shape)
