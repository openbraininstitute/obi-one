"""Blocks shared by the AIND ephys pipeline stages."""

from typing import Literal

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement

# The motion presets a launch job can run. The others need torch or the medicine package.
MotionPreset = Literal["nonrigid_fast_and_accurate", "nonrigid_accurate", "kilosort_like"]
MOTION_PRESET_OPTIONS = {
    "nonrigid_fast_and_accurate": (
        "Nonrigid, fast and accurate",
        "Grid convolution to localize peaks, decentralized estimation of the motion.",
    ),
    "nonrigid_accurate": (
        "Nonrigid, accurate",
        "Monopolar triangulation to localize peaks, decentralized estimation of the motion.",
    ),
    "kilosort_like": (
        "Kilosort-like",
        "Mimics Kilosort: grid convolution to localize peaks, iterative template estimation.",
    ),
}
PEAK_SIGN_OPTIONS = {
    "neg": ("Negative", "Detect downward peaks, the usual shape of an extracellular spike."),
    "pos": ("Positive", "Detect upward peaks."),
    "both": ("Both", "Detect peaks of either sign."),
}


def string_selection(option_details: dict[str, tuple[str, str]]) -> dict:
    """``json_schema_extra`` of an enhanced dropdown, from each option's title and description."""
    return {
        SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION_ENHANCED,
        SchemaKey.TITLE_BY_KEY: {key: title for key, (title, _) in option_details.items()},
        SchemaKey.DESCRIPTION_BY_KEY: {
            key: description for key, (_, description) in option_details.items()
        },
    }


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
