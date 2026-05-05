from collections.abc import Callable
from typing import Any

import morphio

from obi_one.scientific.blocks.compartment_sets import build_compartment_set_for_neuron_set
from obi_one.scientific.library.circuit import Circuit


def materialize_locations_to_compartment_sets(
    *,
    form: Any,
    circuit: Circuit,
    node_population: str | None,
    population: str,
    morphology_loader: Callable[[Circuit, int, str | None], morphio.Morphology | None],
) -> None:
    """Convert stimulus.locations into generated CompartmentSet blocks."""
    if not hasattr(form, "stimuli"):
        return

    for stimulus in form.stimuli.values():
        locations_ref = getattr(stimulus, "locations", None)
        if locations_ref is None:
            continue

        neuron_set_ref = getattr(stimulus, "neuron_set", None)
        if neuron_set_ref is None:
            msg = f"Stimulus '{stimulus.block_name}' specifies locations but has no neuron_set."
            raise ValueError(msg)

        comp_set_name = f"{stimulus.block_name}__locations"

        comp_set = build_compartment_set_for_neuron_set(
            circuit=circuit,
            node_population=node_population,
            population=population,
            neuron_set=neuron_set_ref,
            locations_block=locations_ref.block,
            morphology_loader=morphology_loader,
        )
        comp_set.set_block_name(comp_set_name)
        form.add(comp_set, name=comp_set_name)

        stimulus.compartment_set = comp_set.ref
        stimulus.locations = None
