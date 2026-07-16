from typing import Any

from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.compartment_sets import (
    MaterializedCompartmentSet,
    build_compartment_set_for_neuron_set,
)
from obi_one.scientific.unions_and_references.morphology_locations import (
    MorphologyLocationsReference,
)


def materialize_locations_to_compartment_sets(
    *,
    single_config: Any,
    circuit: Circuit,
    node_population: str | None,
    population: str,
) -> dict[str, MaterializedCompartmentSet]:
    """Convert stimulus MorphologyLocations targets into internal SONATA compartment sets."""
    materialized: dict[str, MaterializedCompartmentSet] = {}

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
            name=comp_set_name,
            circuit=circuit,
            node_population=node_population,
            population=population,
            neuron_set=neuron_set_ref,
            locations_block=locations_block,
        )
        stimulus.set_materialized_compartment_set_target(comp_set_name)

        materialized[comp_set_name] = comp_set

    return materialized
