"""Reading part of a large remote file, without downloading it."""

import io
import os
from collections.abc import Buffer

import httpx

BLOCK_SIZE = 256 * 1024


class HttpRangeFile(io.RawIOBase):
    """A read-only file served by HTTP range requests, keeping every block it fetches.

    Made for short reads of little of a file, such as the metadata in ``h5py.File(file)``.
    """

    def __init__(self, url: str, http_client: httpx.Client) -> None:
        """Opens the file, which fetches its first block to learn its size."""
        super().__init__()
        self._url = url
        self._http_client = http_client
        self._blocks: dict[int, bytes] = {}
        self._position = 0
        self._size = 0
        first = self._fetch(0)
        # Later reads go straight to where a redirect led, as each trip through it takes time.
        self._url = str(first.url)
        self._blocks[0] = first.content
        self._size = int(first.headers["content-range"].rsplit("/", maxsplit=1)[-1])

    def _fetch(self, index: int) -> httpx.Response:
        start = index * BLOCK_SIZE
        response = self._http_client.get(
            self._url, headers={"Range": f"bytes={start}-{start + BLOCK_SIZE - 1}"}
        )
        response.raise_for_status()
        if response.status_code != httpx.codes.PARTIAL_CONTENT:
            msg = f"The server answered a range request with {response.status_code}, not 206."
            raise OSError(msg)
        return response

    def _block(self, index: int) -> bytes:
        if index not in self._blocks:
            self._blocks[index] = self._fetch(index).content
        return self._blocks[index]

    def readable(self) -> bool:  # ruff: ignore[no-self-use]
        return True

    def seekable(self) -> bool:  # ruff: ignore[no-self-use]
        return True

    def tell(self) -> int:
        return self._position

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        origin = {os.SEEK_SET: 0, os.SEEK_CUR: self._position, os.SEEK_END: self._size}[whence]
        self._position = origin + offset
        return self._position

    def readinto(self, buffer: Buffer) -> int:
        view = memoryview(buffer).cast("B")
        count = 0
        while count < len(view) and self._position < self._size:
            index, offset = divmod(self._position, BLOCK_SIZE)
            chunk = self._block(index)[offset : offset + len(view) - count]
            if not chunk:
                msg = f"The server's answer ends before byte {self._position} of {self._size}."
                raise OSError(msg)
            view[count : count + len(chunk)] = chunk
            count += len(chunk)
            self._position += len(chunk)
        return count
