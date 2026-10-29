from typing import ClassVar

from obi_one.scientific.blocks.timestamps.base import Timestamps


class SingleTimestamp(Timestamps):
    """A single timestamp at a specified time."""

    title: ClassVar[str] = "Single timestamp"

    def _resolve_timestamps(self) -> list[float]:
        return [self.start_time]  # ty:ignore[invalid-return-type]
