from typing import Annotated

from pydantic import Field

from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_node_set,
)
from obi_one.scientific.unions.unions_compartment_sets import (
    CompartmentSetReference,
    resolve_compartment_set_ref_to_name,
)


class Targeting:
    """Mixin providing node- and compartment-level targeting fields.

    Intended to be mixed into stimulus classes that need to target either a
    `NeuronSet` (node_set) or a named SONATA `compartment_set`.
    """

    neuron_set: (
        Annotated[
            NeuronSetReference,
            Field(
                title="Neuron Set",
                description="Neuron set to which the stimulus is applied.",
                supports_virtual=False,
            ),
        ]
        | None
    ) = None

    compartment_set: CompartmentSetReference | str | None = Field(
        default=None,
        title="Compartment Set",
        description=(
            "Reference or name of the compartment set as defined in `compartment_sets.json`. "
            "If set, the stimulus will target explicit compartments instead of a node set."
        ),
    )

    def _target_entry(self) -> dict:
        """Return a dict with either `node_set` or `compartment_set` + optional `population`.

        The resolver functions accept either raw strings or BlockReferences so this mixin
        keeps backward compatibility with previously saved configurations.
        """
        if self.compartment_set:
            name = resolve_compartment_set_ref_to_name(self.compartment_set, default=None)
            if name is None:
                return {"node_set": resolve_neuron_set_ref_to_node_set(self.neuron_set, getattr(self, "_default_node_set", "All"))}

            entry = {"compartment_set": name}
            if self.compartment_population:
                entry["population"] = self.compartment_population
            return entry

        return {"node_set": resolve_neuron_set_ref_to_node_set(self.neuron_set, getattr(self, "_default_node_set", "All"))}
