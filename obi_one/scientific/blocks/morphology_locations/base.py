import abc
from typing import Annotated, ClassVar, Literal, Self

import morphio
import pandas as pd
from pydantic import Field, NonNegativeInt, PositiveInt, model_validator

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.library.entity_property_types import (
    CircuitUsability,
    MappedPropertiesGroup,
    MorphologyMappedProperties,
)
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES,
    BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION,
)

SectionType = Literal[3, 4]
SectionTypes = tuple[SectionType, ...] | list[tuple[SectionType, ...]] | None
MAX_NUMBER_OF_MORPHOLOGY_LOCATIONS = 20_000


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
        description=(
            "Neuron set whose morphologies are used to generate locations. If omitted, "
            "locations are generated for the default biophysical neuron set."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES,
        },
    )

    random_seed: NonNegativeInt | list[NonNegativeInt] = Field(
        default=0,
        title="Random Seed",
        description="Seed used when randomly selecting morphology locations.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    number_of_locations: (
        Annotated[PositiveInt, Field(le=MAX_NUMBER_OF_MORPHOLOGY_LOCATIONS)]
        | list[Annotated[PositiveInt, Field(le=MAX_NUMBER_OF_MORPHOLOGY_LOCATIONS)]]
    ) = Field(
        default=20,
        title="Number of Locations",
        description=(
            "Total number of morphology locations to generate for each targeted neuron. "
            f"Maximum: {MAX_NUMBER_OF_MORPHOLOGY_LOCATIONS}."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )
    section_types: SectionTypes = Field(
        default=(3, 4),
        title="Section Types",
        description=(
            "Neurite section types where locations may be generated. Defaults to basal and "
            "apical dendrites."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.MORPHOLOGY_SECTION_TYPE_SELECTION,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.MORPHOLOGY,
            SchemaKey.PROPERTY: MorphologyMappedProperties.SECTION_TYPES,
        },
    )

    @abc.abstractmethod
    def _make_points(self, morphology: morphio.Morphology) -> pd.DataFrame:
        """Returns a generated list of points for the morphology."""

    @abc.abstractmethod
    def _check_parameter_values(self) -> None:
        """Do specific checks on the validity of parameters."""

    @model_validator(mode="after")
    def check_parameter_values(self) -> Self:
        # Only check whenever list are resolved to individual objects
        self._check_parameter_values()
        return self

    def points_on(self, morphology: morphio.Morphology) -> pd.DataFrame:
        self.enforce_no_multi_param()
        return self._make_points(morphology)
