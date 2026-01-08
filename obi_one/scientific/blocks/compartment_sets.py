from __future__ import annotations

from operator import itemgetter
from typing import Any, Iterable, Mapping

import morphio
import pandas as pd
from pydantic import BaseModel, Field

from obi_one.core.block import Block
from obi_one.scientific.blocks.morphology_locations.base import MorphologyLocationsBlock


class CompartmentLocation(BaseModel):
    node_id: int = Field(ge=0)
    section_id: int = Field(ge=0)
    offset: float = Field(ge=0.0, le=1.0)


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

        triplets.sort(key=itemgetter(0, 1, 2))

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

    @classmethod
    def from_locations(
        cls,
        population: str,
        locations: Iterable[CompartmentLocation],
    ) -> CompartmentSet:
        """Convenience constructor from CompartmentLocation objects."""
        triplets = [
            (loc.node_id, loc.section_id, loc.offset)
            for loc in locations
        ]
        return cls(population=population, compartment_entries=tuple(triplets))



def build_compartment_set_from_locations_block(
    population: str,
    locations_block: MorphologyLocationsBlock,
    morphologies: Mapping[int, morphio.Morphology],
) -> CompartmentSet:
    """Create a CompartmentSet from a MorphologyLocationsBlock and morphologies.

    Parameters
    ----------
    population :
        SONATA population name (e.g. 'nodes').
    locations_block :
        Block that generates locations on a single morphology.
    morphologies :
        Mapping from node_id -> morphio.Morphology.

    Returns
    -------
    CompartmentSet
        SONATA-compatible compartment_set block.
    """
    locations: list[CompartmentLocation] = []

    for node_id, morph in morphologies.items():
        df: pd.DataFrame = locations_block.points_on(morph)
        print(df)

        # Expect at least 'section_id' and 'offset' columns.
        # If your spec uses other names, adjust here.
        for _, row in df.iterrows():
            locations.append(
                CompartmentLocation(
                    node_id=int(node_id),
                    section_id=int(row["section_id"]),
                    offset=float(row["offset"]),
                )
            )

    return CompartmentSet.from_locations(population=population, locations=locations)
