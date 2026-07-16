import abc
from typing import ClassVar, Literal, Self

import morphio
import pandas  # noqa: ICN001
from pydantic import Field, model_validator

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.library.entity_property_types import (
    CircuitUsability,
    MappedPropertiesGroup,
    MorphologySourceMappedProperties,
)
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES,
    BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION,
)


class MorphologyLocationsBlock(Block, abc.ABC):
    """Base class representing parameterized locations on morphology skeletons."""

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_MORPHOLOGY_LOCATIONS,
            SchemaKey.FALSE_MESSAGE: (
                "Morphology-location targeting is not supported for this circuit."
            ),
        },
    }

    neuron_set: BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="Neuron Set",
        description="Neuron set whose morphologies the locations are generated on.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES,
        },
    )

    random_seed: int | list[int] = Field(
        default=0,
        title="Random Seed",
        description="Seed for the random generation of locations.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    number_of_locations: int | list[int] = Field(
        default=1,
        title="Number of Locations",
        description="Number of locations to generate on morphology.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )
    section_types: (
        tuple[Literal[2, 3, 4], ...]
        | list[tuple[Literal[2, 3, 4], ...]]
        | None
    ) = Field(
        default=(2, 3, 4),
        title="Section Types",
        description=(
            "Valid neurite section types to generate locations on: "
            "2: axon, 3: basal dendrite, 4: apical dendrite. "
            "Use a tuple for one selection, e.g. (3, 4), "
            "or a list of tuples for parameter scans."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.MORPHOLOGY_SECTION_TYPE_SELECTION,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.MORPHOLOGY_SOURCE,
            SchemaKey.PROPERTY: MorphologySourceMappedProperties.SECTION_TYPES,
        },
    )

    @abc.abstractmethod
    def _make_points(self, morphology: morphio.Morphology) -> pandas.DataFrame:
        """Returns a generated list of points for the morphology."""

    @abc.abstractmethod
    def _check_parameter_values(self) -> None:
        """Do specific checks on the validity of parameters."""

    @model_validator(mode="after")
    def check_parameter_values(self) -> Self:
        # Only check whenever list are resolved to individual objects
        self._check_parameter_values()
        return self

    def points_on(self, morphology: morphio.Morphology) -> pandas.DataFrame:
        self.enforce_no_multi_param()
        return self._make_points(morphology)
