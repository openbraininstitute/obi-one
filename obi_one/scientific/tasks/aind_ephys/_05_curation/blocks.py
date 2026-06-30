"""Building blocks for the aind-ephys-curation capsule.

The fields below mirror the keys read from the capsule's ``params.json``
(https://github.com/AllenNeuralDynamics/aind-ephys-curation/blob/main/code/params.json).
"""

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement


class CurationJobKwargs(Block):
    """SpikeInterface job_kwargs for the curation capsule."""

    chunk_duration: str = Field(
        default="1s",
        title="Chunk duration",
        description="Chunk size as a string ('1s', '500ms', etc.).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    progress_bar: bool = Field(
        default=False,
        title="Progress bar",
        description="Whether to show a progress bar in spikeinterface jobs.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    def to_dict(self) -> dict:
        return {"chunk_duration": self.chunk_duration, "progress_bar": self.progress_bar}
