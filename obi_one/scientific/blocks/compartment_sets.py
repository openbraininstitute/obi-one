from __future__ import annotations

from operator import itemgetter
from typing import Any, Callable, Iterable, Mapping

import morphio
import pandas as pd
from pydantic import BaseModel, Field

from obi_one.core.block import Block
from obi_one.scientific.blocks.morphology_locations.base import MorphologyLocationsBlock
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.unions.unions_neuron_sets import NeuronSetReference


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
    locations: list[CompartmentLocation] = []

    for node_id, morph in morphologies.items():
        df: pd.DataFrame = locations_block.points_on(morph)

        # --- resolve column names ---
        if "section_id" not in df.columns:
            raise KeyError(
                "MorphologyLocationsBlock must return a DataFrame with a 'section_id' column. "
                f"Got columns: {list(df.columns)}"
            )

        if "normalized_section_offset" in df.columns:
            offset_col = "normalized_section_offset"
        elif "offset" in df.columns:
            offset_col = "offset"
        else:
            raise KeyError(
                "MorphologyLocationsBlock must return a DataFrame with either "
                "'normalized_section_offset' (preferred) or 'offset'. "
                f"Got columns: {list(df.columns)}"
            )

        for _, row in df.iterrows():
            locations.append(
                CompartmentLocation(
                    node_id=int(node_id),
                    section_id=int(row["section_id"]),
                    offset=float(row[offset_col]),
                )
            )

    return CompartmentSet.from_locations(population=population, locations=locations)

def build_compartment_set_for_neuron_set(
    *,
    circuit: Circuit,
    node_population: str | None,
    population: str,
    neuron_set: NeuronSetReference,
    locations_block: MorphologyLocationsBlock,
    morphology_loader: Callable[[Circuit, int, str | None], morphio.Morphology],
) -> CompartmentSet:
    """
    Public bridge used by high-level configs/examples:
      neuron_set + locations_block -> CompartmentSet

    Notes:
      - `population` is the SONATA population name for CompartmentSet (e.g. "biophysical").
      - `node_population` is the circuit population used to resolve node ids/morphologies (if needed).
    """
    node_ids = neuron_set.block.get_neuron_ids(circuit, node_population)

    morphologies: dict[int, morphio.Morphology] = {}
    for node_id in node_ids:
        morph = morphology_loader(circuit, int(node_id), node_population)
        if morph is None:
            if on_missing == "error":
                raise ValueError(f"Missing morphology for node_id={node_id}")
            continue
        morphologies[int(node_id)] = morph

    return build_compartment_set_from_locations_block(
        population=population,
        locations_block=locations_block,
        morphologies=morphologies,
    )
