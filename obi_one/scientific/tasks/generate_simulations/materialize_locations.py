from collections.abc import Callable
from typing import Any

import morphio

from obi_one.scientific.blocks.compartment_sets import (
    CompartmentSet,
    build_compartment_set_for_neuron_set,
)
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.unions.unions_compartment_sets import CompartmentSetReference
from obi_one.scientific.unions.unions_morphology_locations_ref import MorphologyLocationsReference


def materialize_locations_to_compartment_sets(
    *,
    single_config: Any,
    circuit: Circuit,
    node_population: str | None,
    population: str,
    morphology_loader: Callable[[Circuit, int, str | None], morphio.Morphology | None],
) -> dict[str, CompartmentSet]:
    """Convert stimulus MorphologyLocations targets into generated CompartmentSet blocks."""
    materialized: dict[str, CompartmentSet] = {}

    if not hasattr(single_config, "stimuli"):
        return materialized

    for stimulus in single_config.stimuli.values():
        target_ref = getattr(stimulus, "neuron_set", None)
        if not isinstance(target_ref, MorphologyLocationsReference):
            continue

        locations_block = target_ref.block

        neuron_set_ref = getattr(locations_block, "neuron_set", None)
        if neuron_set_ref is None:
            msg = (
                f"Locations block '{locations_block.block_name}' referenced by stimulus "
                f"'{stimulus.block_name}' has no neuron_set."
            )
            raise ValueError(msg)

        comp_set_name = f"{stimulus.block_name}__locations"

        comp_set = build_compartment_set_for_neuron_set(
            circuit=circuit,
            node_population=node_population,
            population=population,
            neuron_set=neuron_set_ref,
            locations_block=locations_block,
            morphology_loader=morphology_loader,
        )
        comp_set.set_block_name(comp_set_name)

        ref = CompartmentSetReference(
            block_dict_name="",
            block_name=comp_set_name,
        )
        ref.block = comp_set

        comp_set.set_ref(ref)

        stimulus.neuron_set = ref

        materialized[comp_set_name] = comp_set

    return materialized
