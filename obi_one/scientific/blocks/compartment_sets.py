from typing import Any
from pydantic import BaseModel, Field
from obi_one.core.block import Block

class CompartmentLocation(BaseModel):
    node_id: int = Field(ge=0)
    section_id: int = Field(ge=0)
    offset: float = Field(ge=0.0, le=1.0)

from typing import Any
from pydantic import BaseModel, Field

from obi_one.core.block import Block


class CompartmentSet(Block):
    """SONATA-compatible compartment_set block."""

    population: str = Field(
        title="Population",
        description="Node population name for which the compartment entries apply.",
    )

    compartment_entries: tuple[tuple[int, int, float], ...] = Field(
        default_factory=tuple,
        title="Compartment Entries",
        description="Tuple of (node_id, section_id, offset) triplets.",
    )

    def to_sonata_dict(self) -> dict[str, Any]:
        """Return SONATA-compliant { block_name : {...} } structure."""

        triplets = [
            [int(node_id), int(section_id), float(offset)]
            for (node_id, section_id, offset) in self.compartment_entries
        ]

        triplets.sort(key=lambda t: (t[0], t[1], t[2]))

        deduped: list[list[float | int]] = []
        last: list[float | int] | None = None
        for t in triplets:
            if t != last:
                deduped.append(t)
                last = t

        return {
            self.block_name: {
                "population": self.population,
                "compartment_set": deduped,
            }
        }
