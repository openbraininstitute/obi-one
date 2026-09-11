from __future__ import annotations

import logging
from operator import itemgetter
from typing import TYPE_CHECKING, Any, NoReturn

from pydantic import BaseModel, Field

from obi_one.core.exception import ConfigValidationError

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    import morphio

    from obi_one.scientific.blocks.morphology_locations.base import MorphologyLocationsBlock
    from obi_one.scientific.blocks.morphology_locations.per_neuron_explicit import (
        PerNeuronExplicitMorphologyLocations,
    )
    from obi_one.scientific.library.circuit import Circuit
    from obi_one.scientific.unions_and_references.combined_neuron_sets import (
        BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION,
    )

L = logging.getLogger(__name__)

MAX_MATERIALIZED_COMPARTMENT_SET_ENTRIES = 5_000


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


def build_compartment_set_from_selected_rows(
    *,
    name: str,
    population: str,
    locations_block: PerNeuronExplicitMorphologyLocations,
) -> MaterializedCompartmentSet:
    """Create a compartment set from points that already name their own neuron.

    No morphologies are loaded and no neuron set is expanded: the selected points are the rows.
    """
    return MaterializedCompartmentSet(
        name=name,
        population=population,
        compartment_entries=locations_block.compartment_rows(),
    )


def _validate_compartment_set_entry_count(*, name: str, entry_count: int) -> None:
    if entry_count > MAX_MATERIALIZED_COMPARTMENT_SET_ENTRIES:
        msg = (
            f"Compartment set '{name}' would contain {entry_count:,} entries, which exceeds "
            f"the maximum of {MAX_MATERIALIZED_COMPARTMENT_SET_ENTRIES:,}. Reduce the number "
            "of locations or target a smaller neuron set."
        )
        raise ConfigValidationError(msg)


def _raise_empty_compartment_set(
    *, name: str, population: str, targeted: int, unloadable: int
) -> NoReturn:
    """Explain why a referenced compartment set came out empty."""
    if unloadable == targeted:
        detail = (
            f"none of the {targeted:,} targeted neurons in population '{population}' had a "
            "readable morphology. Check that the circuit's morphology files are present and in a "
            "supported format."
        )
    elif unloadable:
        detail = (
            f"the morphology rule produced no locations on the {targeted - unloadable:,} of "
            f"{targeted:,} targeted neurons whose morphologies could be read."
        )
    else:
        detail = (
            f"the morphology rule produced no locations on any of the {targeted:,} targeted "
            "neurons. Check that the requested section types exist on these morphologies."
        )

    msg = f"Compartment set '{name}' is empty: {detail}"
    raise ConfigValidationError(msg)


def _iter_morphologies(
    *,
    circuit: Circuit,
    node_ids: Iterable[int],
    population: str,
    unloadable: list[int],
) -> Iterator[tuple[int, morphio.Morphology]]:
    """Yield one morphology at a time, so only the morphology in use is held in memory.

    Node ids whose morphology cannot be read are skipped and recorded in `unloadable`, so the
    caller can tell an empty result apart from a partially skipped one.
    """
    for node_id in node_ids:
        node_id_int = int(getattr(node_id, "id", node_id))
        try:
            morph = circuit.load_morphology(node_id_int, population=population)
        except (FileNotFoundError, KeyError, ValueError) as exc:
            L.warning(
                "Unable to load morphology for node %s in population '%s': %s",
                node_id_int,
                population,
                exc,
            )
            unloadable.append(node_id_int)
            continue

        yield node_id_int, morph


def build_compartment_set_from_locations_block(
    *,
    name: str,
    population: str,
    locations_block: MorphologyLocationsBlock,
    morphology_items: Iterable[tuple[int, morphio.Morphology]],
) -> MaterializedCompartmentSet:
    """Accumulate compartment rows from `(node_id, morphology)` pairs.

    Pairs are consumed lazily so callers can release each morphology once its rows are read,
    rather than holding every targeted morphology in memory at once.
    """
    locations: list[CompartmentLocation] = []

    for node_id, morph in morphology_items:
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

        _validate_compartment_set_entry_count(
            name=name,
            entry_count=len(locations) + len(df),
        )

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

    if len(node_ids) == 0:
        msg = (
            f"Compartment set '{name}' would be empty: its neuron set resolves to no neurons in "
            f"population '{selected_population}'. Target a neuron set that selects at least one "
            "neuron."
        )
        raise ConfigValidationError(msg)

    locations_per_morphology = locations_block.output_location_count()
    if locations_per_morphology is not None:
        _validate_compartment_set_entry_count(
            name=name,
            entry_count=len(node_ids) * locations_per_morphology,
        )

    unloadable: list[int] = []
    compartment_set = build_compartment_set_from_locations_block(
        name=name,
        population=population,
        locations_block=locations_block,
        morphology_items=_iter_morphologies(
            circuit=circuit,
            node_ids=node_ids,
            population=selected_population,
            unloadable=unloadable,
        ),
    )

    # A materialized compartment set is only built when a stimulus or recording references it, so
    # an empty one would silently target nothing at simulation time.
    if not compartment_set.compartment_entries:
        _raise_empty_compartment_set(
            name=name,
            population=selected_population,
            targeted=len(node_ids),
            unloadable=len(unloadable),
        )

    return compartment_set
