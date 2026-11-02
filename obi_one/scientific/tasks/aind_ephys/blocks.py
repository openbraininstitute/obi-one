"""Blocks shared by the AIND ephys pipeline stages."""

from typing import Literal

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey


class JobKwargs(Block):
    """SpikeInterface job kwargs for a stage's chunked, parallel processing."""

    n_jobs: int = Field(
        default=-1,
        title="Jobs",
        description="Number of parallel jobs; -1 uses every core.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    chunk_duration: str = Field(
        default="1s",
        title="Chunk duration",
        description="Duration of each processing chunk, e.g. '1s' or '500ms'.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    progress_bar: bool = Field(
        default=False,
        title="Progress bar",
        description="Whether spikeinterface prints progress bars.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    mp_context: Literal["spawn", "fork", "forkserver"] | None = Field(
        default=None,
        title="Multiprocessing context",
        description="Start method for worker processes; None keeps the platform default.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    def to_dict(self) -> dict:
        kwargs = {
            "n_jobs": self.n_jobs,
            "chunk_duration": self.chunk_duration,
            "progress_bar": self.progress_bar,
        }
        if self.mp_context is not None:
            kwargs["mp_context"] = self.mp_context
        return kwargs
