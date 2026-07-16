from __future__ import annotations

import logging
from operator import itemgetter
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    import morphio

    from obi_one.scientific.blocks.morphology_locations.base import MorphologyLocationsBlock
    from obi_one.scientific.library.circuit import Circuit
    from obi_one.scientific.unions.unions_combined_neuron_sets import (
        BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION,
    )

L = logging.getLogger(__name__)


class CompartmentLocation(BaseModel):
    node_id: int = Field(ge=0)
    section_id: int = Field(ge=0)
    offset: float = Field(ge=0.0, le=1.0)


class MaterializedCompartmentSet(BaseModel):
    """Internal SONATA compartment-set representation generated from MorphologyLocations."""

    name: str = Field(min_length=1)
    population: str = Field(min_length=1)
    compartment_entries: tuple[tuple[int, int, float], ...] = Field(default_factory=tuple)

    def to_sonata_dict(self) -> dict[str, Any]:
        """Return SONATA-compliant { name : {...} } structure."""
        triplets = [
            [int(node_id), int(section_id), float(offset)]
            for (node_id, section_id, offset) in self.compartment_entries
        ]

        triplets.sort(key=itemgetter(0, 1, 2))

        deduped: list[list[float | int]] = []
        last: list[float | int] | None = None
        for triplet in triplets:
            if triplet != last:
                deduped.append(triplet)
                last = triplet

        return {
            self.name: {
                "population": self.population,
                "compartment_set": deduped,
            }
        }

    @classmethod
    def from_locations(
        cls,
        *,
        name: str,
        population: str,
        locations: Iterable[CompartmentLocation],
    ) -> MaterializedCompartmentSet:
        triplets = [(loc.node_id, loc.section_id, loc.offset) for loc in locations]
        return cls(name=name, population=population, compartment_entries=tuple(triplets))


def build_compartment_set_from_locations_block(
    *,
    name: str,
    population: str,
    locations_block: MorphologyLocationsBlock,
    morphologies: Mapping[int, morphio.Morphology],
) -> MaterializedCompartmentSet:
    locations: list[CompartmentLocation] = []

    for node_id, morph in morphologies.items():
        df = locations_block.points_on(morph)

        if "section_id" not in df.columns:
            msg = (
                "MorphologyLocationsBlock must return a DataFrame with a 'section_id' column. "
                f"Got columns: {list(df.columns)}"
            )
            raise KeyError(msg)

        if "normalized_section_offset" in df.columns:
            offset_col = "normalized_section_offset"
        elif "offset" in df.columns:
            offset_col = "offset"
        else:
            msg = (
                "MorphologyLocationsBlock must return a DataFrame with either "
                "'normalized_section_offset' (preferred) or 'offset'. "
                f"Got columns: {list(df.columns)}"
            )
            raise KeyError(msg)

        for _, row in df.iterrows():
            locations.append(
                CompartmentLocation(
                    node_id=int(node_id),
                    section_id=int(row["section_id"]),
                    offset=float(row[offset_col]),
                )
            )

    return MaterializedCompartmentSet.from_locations(
        name=name,
        population=population,
        locations=locations,
    )


def build_compartment_set_for_neuron_set(
    *,
    name: str,
    circuit: Circuit,
    node_population: str | None,
    population: str,
    neuron_set: BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION,
    locations_block: MorphologyLocationsBlock,
) -> MaterializedCompartmentSet:
    """Create an internal SONATA compartment set from a neuron set and morphology locations."""
    neuron_set_block = neuron_set.block
    ids_by_population = neuron_set_block.get_neuron_ids(circuit)
    selected_population = node_population or population
    try:
        node_ids = ids_by_population[selected_population]
    except KeyError as exc:
        msg = (
            f"Neuron set does not contain population {selected_population!r}; "
            f"available populations: {sorted(ids_by_population)}"
        )
        raise ValueError(msg) from exc

    morphologies: dict[int, morphio.Morphology] = {}
    for node_id in node_ids:
        node_id_int = int(getattr(node_id, "id", node_id))
        try:
            morph = circuit.load_morphology(node_id_int, population=selected_population)
        except (FileNotFoundError, KeyError, ValueError) as exc:
            L.warning(
                "Unable to load morphology for node %s in population '%s': %s",
                node_id_int,
                selected_population,
                exc,
            )
            continue
        morphologies[node_id_int] = morph

    return build_compartment_set_from_locations_block(
        name=name,
        population=population,
        locations_block=locations_block,
        morphologies=morphologies,
    )
