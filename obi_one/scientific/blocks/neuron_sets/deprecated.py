import abc
from typing import ClassVar

from obi_one.scientific.blocks.neuron_sets.base import NeuronSet, NeuronSetPopulationType
from obi_one.scientific.library.circuit import Circuit
from obi_one.core.schema import SchemaKey
from obi_one.scientific.library.entity_property_types import (
    CircuitUsability,
    MappedPropertiesGroup,
)


class DeprecatedNeuronSet(NeuronSet, abc.ABC):
    """A neuron set that is deprecated and should not be used.

    This neuron set is used to indicate that a particular neuron set is deprecated and
    should not be used in new simulations. It may still be present in existing simulations
    for backward compatibility, but it is recommended to use alternative neuron sets
    instead.
    """

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_DEPRECATED_BLOCKS,
            SchemaKey.FALSE_MESSAGE: "This neuron set is deprecated and should not be used.",
        },
    }

    @property
    def deprecation_error_message(self) -> str:
        """Returns a deprecation error message indicating that this neuron set is deprecated."""
        return (
            f"{self.__class__.__name__} is deprecated and should not be used. "
            "Please use an alternative neuron set instead."
        )

    def _resolve_ids(self, circuit: Circuit) -> list[int]:
        raise NotImplementedError(self.deprecation_error_message)

    def get_neuron_ids(self, circuit: Circuit) -> dict[str, list[int]]:
        raise NotImplementedError(self.deprecation_error_message)

    def _get_expression(self, circuit: Circuit) -> dict | list:
        raise NotImplementedError(self.deprecation_error_message)

    def get_node_set_definition(
        self, circuit: Circuit, *, force_resolve_ids: bool = False
    ) -> tuple[dict | list, dict]:
        raise NotImplementedError(self.deprecation_error_message)

    def get_populations(self, circuit: Circuit) -> list[str]:
        raise NotImplementedError(self.deprecation_error_message)

    def _get_expression(self, circuit: Circuit) -> dict | list:
        raise NotImplementedError(self.deprecation_error_message)


class ExcitatoryNeurons(DeprecatedNeuronSet):
    title: ClassVar[str] = "All Excitatory Neurons (Deprecated)"
    description: ClassVar[str] = "All neurons from all node populations."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = (
        NeuronSetPopulationType.BIOPHYSICAL
    )


class InhibitoryNeurons(DeprecatedNeuronSet):
    """All biophysical inhibitory neurons."""

    title: ClassVar[str] = "All Inhibitory Neurons (Deprecated)"

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = (
        NeuronSetPopulationType.BIOPHYSICAL
    )


class IDNeuronSet(DeprecatedNeuronSet):
    """A neuron set that selects neurons by their IDs.

    This neuron set is used to select neurons by their IDs, which can be useful for
    selecting specific neurons for analysis or manipulation.
    """

    title: ClassVar[str] = "ID Neuron Set (Deprecated)"

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = (
        NeuronSetPopulationType.BIOPHYSICAL
    )


class nbS1VPMInputs(DeprecatedNeuronSet):  # noqa: N801
    """Virtual neurons projecting from the VPM thalamic nucleus.

    Specifically, virtual neurons projecting from the VPM thalamic nucleus to biophysical
    cortical neurons in the nbS1 model.
    """

    title: ClassVar[str] = "Demo: nbS1 VPM Inputs (Deprecated)"

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = NeuronSetPopulationType.VIRTUAL


class nbS1POmInputs(DeprecatedNeuronSet):  # noqa: N801
    """Virtual neurons projecting from the POm thalamic nucleus.

    Specifically, virtual neurons projecting from the POm thalamic nucleus to biophysical
    cortical neurons in the nbS1 model.
    """

    title: ClassVar[str] = "Demo: nbS1 POm Inputs (Deprecated)"

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = NeuronSetPopulationType.VIRTUAL


class rCA1CA3Inputs(DeprecatedNeuronSet):  # noqa: N801
    """Virtual neurons projecting from CA3 to CA1.

    Specifically, virtual neurons projecting from the CA3 region to biophysical CA1 neurons
    in the rCA1 model.
    """

    title: ClassVar[str] = "Demo: rCA1 CA3 Inputs (Deprecated)"

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = NeuronSetPopulationType.VIRTUAL
