import numpy as np
from pandas import DataFrame
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.entity_property_types import (
    CircuitMappedProperties,
    MappedPropertiesGroup,
)
from obi_one.scientific.unions_and_references.reference_tags import ReferenceTag
from obi_one.scientific.unions_and_references.synaptic_models import (
    SynapticModelReference,
)


class SynapseModelAssigner(Block):
    random_seed: int | list[int] = Field(
        default=1,
        title="Random seed",
        description="Seed for drawing random values from physiological parameter distributions.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    edge_population_name: str = Field(
        min_length=1,
        title="Edge Population",
        description="Edge population of the SONATA circuit that is to be parameterized.",
        json_schema_extra={
            # Chemical rather than every edge population: these assigners carry
            # Tsodyks-Markram models, which describe chemical synaptic transmission, so
            # offering an electrical population here would offer a nonsensical assignment.
            SchemaKey.UI_ELEMENT: UIElement.ENTITY_PROPERTY_DROPDOWN,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitMappedProperties.CHEMICAL_EDGE_POPULATION,
        },
    )

    synaptic_model: SynapticModelReference | None = Field(
        default=None,
        title="Synaptic Model",
        description="Synaptic model to assign to the synapses between the source and target"
        " neuron sets.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [SynapticModelReference.__name__],
            SchemaKey.REFERENCE_TAG: ReferenceTag.SYNAPTIC_MODEL,
        },
    )

    def validate_for_circuit(self, circuit: Circuit) -> None:
        """Check this assigner can be applied to the circuit, before anything is written.

        Called by SynapseParameterizationTask before it copies the circuit, so that a
        configuration that cannot work says why. Without it the same mistakes surface
        from inside `_edge_indices` as a bare KeyError, after the copy and after the
        whole parameter table has been built.
        """
        edge_populations = circuit.sonata_circuit.edges.population_names
        if self.edge_population_name not in edge_populations:
            msg = (
                f"Edge population {self.edge_population_name!r} is not in this circuit. "
                f"Available edge populations: {sorted(edge_populations)}."
            )
            raise ValueError(msg)

        # `synaptic_model` is None only before `fill_none_references` has run - by the time a
        # SingleConfig reaches this task, every assigner's tagged reference has already been
        # substituted with its default (the family's own default model). So None here means
        # this assigner is being validated ahead of that fill, not that no model is wanted;
        # `create_parameters` below assumes a resolved model unconditionally, so failing loudly
        # here is better than the AttributeError it would otherwise raise on `None.block`.
        if self.synaptic_model is None:
            msg = (
                f"Assigner for edge population {self.edge_population_name!r} has no synaptic "
                "model resolved yet. Call fill_none_references() on the config (or set one "
                "explicitly) before validating it against a circuit."
            )
            raise ValueError(msg)

        # The assigned model, not a fixed list of types: different synapse model families
        # need entirely different parameter sets (Tsodyks-Markram's Use/Dep/Fac have no
        # counterpart on an "Exp2Syn_synapse" or "point_process" population, and neither
        # applies to an electrical population), so only the model itself knows which
        # SONATA edge population type(s) it is meaningful for. The UI dropdown already
        # narrows this for Tsodyks-Markram assigners specifically, but a config submitted
        # through the API can name any population, so the guarantee has to be enforced here.
        model = self.synaptic_model.block
        compatible_types = type(model).compatible_edge_population_types()
        edge_population_type = circuit.sonata_circuit.edges[self.edge_population_name].type
        if edge_population_type not in compatible_types:
            msg = (
                f"Edge population {self.edge_population_name!r} has type "
                f"{edge_population_type!r}, but {type(model).__name__} can only be "
                f"assigned to edge populations of type {sorted(compatible_types)}."
            )
            raise ValueError(msg)

    def _validate_neuron_set_spans(
        self,
        circuit: Circuit,
        neuron_set_reference: object | None,
        side: str,
        population: str,
    ) -> None:
        """Check a neuron set covers the population on one side of the edge population.

        `_edge_indices` indexes `get_neuron_ids(circuit)` by that population name, and
        that dict is keyed by exactly `get_populations(circuit)` for every neuron set
        type - combined ones included, since combining unions the keys and never drops
        one. So this predicts the KeyError rather than approximating it.
        """
        if neuron_set_reference is None:
            msg = (
                f"The {side} neuron set is required to assign a synaptic model to edge "
                f"population {self.edge_population_name!r}."
            )
            raise ValueError(msg)
        populations = neuron_set_reference.block.get_populations(circuit)  # ty:ignore[unresolved-attribute]
        if population not in populations:
            msg = (
                f"Edge population {self.edge_population_name!r} has {side} population "
                f"{population!r}, but the {side} neuron set spans {sorted(populations)}. "
                f"No synapse in that edge population starts or ends at these neurons."
            )
            raise ValueError(msg)

    def _edge_indices(self, circuit: Circuit) -> np.ndarray:
        msg = (
            "Concrete subclasses of SynapseModelAssigner MUST implement the ._edge_indices() "
            "method to return the edge indices to which the synaptic model should be assigned."
        )
        raise NotImplementedError(msg)

    def edge_indices(
        self, circuit: Circuit, min_edge_id: int | None = None, max_edge_id: int | None = None
    ) -> DataFrame:
        circ = circuit.sonata_circuit
        ep = circ.edges[self.edge_population_name]
        indices = self._edge_indices(circuit)
        if min_edge_id is not None:
            indices = indices[indices >= min_edge_id]
        if max_edge_id is not None:
            indices = indices[indices < max_edge_id]
        return ep.get(indices, properties=["@source_node", "@target_node"])

    def create_parameters(
        self, circuit: Circuit, min_edge_id: int | None = None, max_edge_id: int | None = None
    ) -> DataFrame:
        indices_df = self.edge_indices(circuit, min_edge_id=min_edge_id, max_edge_id=max_edge_id)
        param_model = self.synaptic_model.block  # ty:ignore[unresolved-attribute]
        # `random_seed` is what the user is offered as "the seed for drawing random values from
        # physiological parameter distributions", and it can be swept. It only means that if it
        # reaches the sampling: without it every distribution seeds itself from its own
        # `random_seed`, which defaults to 1, so every seed in a sweep produced the same circuit.
        new_params = param_model.sample(indices_df, rng=np.random.default_rng(self.random_seed))
        return new_params

    def assign_parameters(
        self,
        circuit: Circuit,
        params: DataFrame,
        min_edge_id: int | None = None,
        max_edge_id: int | None = None,
    ) -> None:
        new_params = self.create_parameters(
            circuit, min_edge_id=min_edge_id, max_edge_id=max_edge_id
        )
        params.update(new_params)
